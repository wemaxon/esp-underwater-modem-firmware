"""Device session: owns one connection on a worker thread.

Public methods are thread-safe and only queue commands. Results are published
through `statuses` and `frames` (latest value wins) and the bounded log queue.
"""

from dataclasses import dataclass, replace
from enum import Enum
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread
from time import monotonic

from .model import ToneBurst
from .tf_protocol import (
    CANCELLED, CAPTURE, GET_DEVICE_INFO, LOG, OK, RESULT_NAMES, STOP, TIMEOUT, TRANSMIT,
    Packet, ProtocolError, decode_capture, decode_info, decode_log, encode_tone,
)


class ConnectionState(Enum):
    CONNECTING = "Connecting"
    CONNECTED = "Connected"
    DISCONNECTING = "Disconnecting"
    DISCONNECTED = "Disconnected"


class AcquisitionState(Enum):
    STOPPED = "Stopped"
    STARTING = "Starting"
    CAPTURING = "Capturing"
    STOPPING = "Stopping"
    COMPLETE = "Complete"


@dataclass(frozen=True)
class SessionStatus:
    connection: ConnectionState = ConnectionState.DISCONNECTED
    acquisition: AcquisitionState = AcquisitionState.STOPPED
    captures_received: int = 0
    device_name: str = ""
    error: str = ""
    transmitting: bool = False
    transmit_message: str = "Idle"


@dataclass(frozen=True)
class StartCapture:
    continuous: bool


@dataclass(frozen=True)
class StopCapture:
    pass


@dataclass(frozen=True)
class Transmit:
    tone: ToneBurst


class Latest:
    """Single-slot mailbox: a new value replaces an untaken one."""

    def __init__(self):
        self.lock = Lock()
        self.value = None

    def put(self, value):
        with self.lock:
            self.value = value

    def take(self):
        with self.lock:
            value, self.value = self.value, None
            return value


class Requests:
    """Outstanding host requests, at most one per message type."""

    ID_LIMIT = 0x8000       # host frame IDs; the device uses 0x8000-0xFFFF

    def __init__(self, timeout):
        self.timeout = timeout
        self.pending = {}
        self.last_id = 0

    def __contains__(self, message_type):
        return message_type in self.pending

    def __bool__(self):
        return bool(self.pending)

    def open(self, message_type, payload=b""):
        self.last_id = (self.last_id + 1) % self.ID_LIMIT
        self.pending[message_type] = (self.last_id, monotonic() + self.timeout)
        return Packet(message_type, self.last_id, payload)

    def close(self, packet):
        expected = self.pending.pop(packet.message_type, None)
        if expected is None or packet.frame_id != expected[0]:
            raise ProtocolError("Unexpected response type or frame ID")

    def expired(self):
        now = monotonic()
        return any(now >= deadline for _, deadline in self.pending.values())


class Session:
    def __init__(self, device_factory, timeout=3.0):
        self.device_factory = device_factory
        self.statuses, self.frames = Latest(), Latest()
        self.logs = Queue(maxsize=256)
        self.commands, self.close_requested, self.done = Queue(), Event(), Event()
        self.thread = Thread(target=self._run, name="device-session")
        self.status = SessionStatus(ConnectionState.CONNECTING)
        self.requests = Requests(timeout)
        self.device = None
        self.info = None
        self.continuous = False
        self.handlers = {
            LOG: self._on_log,
            GET_DEVICE_INFO: self._on_device_info,
            STOP: self._on_stop,
            CAPTURE: self._on_capture,
            TRANSMIT: self._on_transmit,
        }

    # Public API, callable from any thread

    def open(self):
        self.thread.start()

    def start_acquisition(self, continuous=False):
        self.commands.put(StartCapture(bool(continuous)))

    def stop_acquisition(self):
        self.commands.put(StopCapture())

    def transmit(self, tone: ToneBurst):
        self.commands.put(Transmit(tone))

    def close(self):
        self.close_requested.set()

    def take_logs(self):
        entries = []
        for _ in range(self.logs.maxsize):
            try:
                entries.append(self.logs.get_nowait())
            except Empty:
                break
        return entries

    # Worker thread

    @property
    def connected(self):
        return self.status.connection == ConnectionState.CONNECTED

    @property
    def closing(self):
        return self.close_requested.is_set()

    def _status(self, **changes):
        self.status = replace(self.status, **changes)
        self.statuses.put(self.status)

    def _send(self, message_type, payload=b""):
        self.device.send(self.requests.open(message_type, payload))

    def _run(self):
        self.statuses.put(self.status)
        error = ""
        try:
            self.device = self.device_factory()
            self._send(STOP)        # cancel whatever a previous session left running
            while not self._finished():
                self._process_commands()
                for packet in self.device.read():
                    self._receive(packet)
                if self.requests.expired():
                    raise TimeoutError("Device response timed out")
        except Exception as exc:
            error = str(exc)
        finally:
            if self.device is not None:
                self.device.close()
            transmit_message = "Connection closed" if self.status.transmitting else self.status.transmit_message
            self._status(connection=ConnectionState.DISCONNECTED, acquisition=AcquisitionState.STOPPED,
                         transmitting=False, transmit_message=transmit_message, error=error or self.status.error)
            self.done.set()

    def _finished(self):
        if not self.closing:
            return False
        if CAPTURE in self.requests:
            self._stop_capture()
        return not self.requests

    def _process_commands(self):
        while True:
            try:
                command = self.commands.get_nowait()
            except Empty:
                return
            if isinstance(command, StartCapture):
                self._start_capture(command.continuous)
            elif isinstance(command, StopCapture):
                self._request_stop()
            elif isinstance(command, Transmit):
                self._start_transmit(command.tone)

    def _start_capture(self, continuous):
        if not self.connected or self.closing or CAPTURE in self.requests or STOP in self.requests:
            return
        self.continuous = continuous
        self._status(acquisition=AcquisitionState.CAPTURING, error="")
        self._send(CAPTURE)

    def _request_stop(self):
        self.continuous = False
        if CAPTURE in self.requests:
            self._stop_capture()
        elif STOP not in self.requests:
            self._status(acquisition=AcquisitionState.STOPPED)

    def _stop_capture(self):
        self.continuous = False
        if STOP not in self.requests:
            self._status(acquisition=AcquisitionState.STOPPING)
            self._send(STOP)

    def _start_transmit(self, tone):
        if not self.connected or self.closing or TRANSMIT in self.requests:
            return
        self._status(transmitting=True, transmit_message="Transmitting")
        self._send(TRANSMIT, encode_tone(tone))

    def _receive(self, packet):
        handler = self.handlers.get(packet.message_type)
        if handler is None:
            raise ProtocolError(f"Unknown message type {packet.message_type}")
        if packet.message_type == LOG:
            handler(packet)
            return
        if packet.message_type == CAPTURE and self.status.connection == ConnectionState.CONNECTING:
            return      # the cancelled capture of a previous session
        self.requests.close(packet)
        handler(packet)

    def _on_log(self, packet):
        if not packet.frame_id & 0x8000:
            raise ProtocolError("Invalid device log frame ID")
        try:
            self.logs.put_nowait(decode_log(packet.payload))
        except Full:
            pass

    def _on_device_info(self, packet):
        self.info = decode_info(packet.payload)
        self._status(connection=ConnectionState.CONNECTED, device_name=self.info.name)

    def _on_stop(self, packet):
        if packet.payload != bytes([OK]) or CAPTURE in self.requests:
            raise ProtocolError("Invalid STOP response")
        self._status(acquisition=AcquisitionState.STOPPED)
        if self.status.connection == ConnectionState.CONNECTING and not self.closing:
            self._send(GET_DEVICE_INFO)

    def _on_capture(self, packet):
        if len(packet.payload) == 1:
            self._on_capture_failed(packet.payload[0])
            return
        self.frames.put(decode_capture(packet.payload, self.info))
        self._status(captures_received=self.status.captures_received + 1)
        if self.continuous and not self.closing:
            self._send(CAPTURE)
        elif STOP not in self.requests:
            self._status(acquisition=AcquisitionState.COMPLETE)

    def _on_capture_failed(self, result):
        if result == CANCELLED and STOP in self.requests:
            return
        if result == TIMEOUT and self.continuous:
            self._send(CAPTURE)
            return
        self.continuous = False
        error = RESULT_NAMES[result] if 0 < result < len(RESULT_NAMES) else "Invalid capture result"
        self._status(acquisition=AcquisitionState.STOPPED, error=error)

    def _on_transmit(self, packet):
        if len(packet.payload) != 1 or packet.payload[0] >= len(RESULT_NAMES):
            raise ProtocolError("Invalid transmit response")
        result = packet.payload[0]
        self._status(transmitting=False, transmit_message="Complete" if result == OK else RESULT_NAMES[result])
