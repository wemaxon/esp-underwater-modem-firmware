"""Device session: owns one connection on a worker thread.

Public methods are thread-safe and only queue commands. Results are published
through `statuses` (latest value wins), the stream data queue and the bounded
log queue.
"""

from dataclasses import dataclass, replace
from enum import Enum
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread
from time import monotonic

from .afe import AfeConfig
from .model import ToneBurst
from .tf_protocol import (
    DEVICE_FRAME_ID, EVENTS, GET_AFE_CONFIG, GET_DEVICE_INFO, LOG, OK, OUT3_EDGES, RESULT_NAMES, SET_AFE_CONFIG,
    STREAM_END, STREAM_START, STREAM_STOP, TRANSMIT, VOUT_SAMPLES, Packet, ProtocolError, decode_afe, decode_edges,
    decode_info, decode_log, decode_result, decode_vout, encode_tone,
)


class ConnectionState(Enum):
    CONNECTING = "Connecting"
    CONNECTED = "Connected"
    DISCONNECTING = "Disconnecting"
    DISCONNECTED = "Disconnected"


class AcquisitionState(Enum):
    STOPPED = "Stopped"
    STARTING = "Starting"
    STREAMING = "Streaming"
    STOPPING = "Stopping"


@dataclass(frozen=True)
class SessionStatus:
    connection: ConnectionState = ConnectionState.DISCONNECTED
    acquisition: AcquisitionState = AcquisitionState.STOPPED
    device_name: str = ""
    error: str = ""
    transmitting: bool = False
    transmit_message: str = "Idle"
    afe: AfeConfig | None = None    # the device's receive front-end configuration, once read


@dataclass(frozen=True)
class StartStream:
    pass


@dataclass(frozen=True)
class StopStream:
    pass


@dataclass(frozen=True)
class Transmit:
    tone: ToneBurst


@dataclass(frozen=True)
class ApplyAfe:
    config: AfeConfig


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


def _drain(queue, limit=None):
    items = []
    while limit is None or len(items) < limit:
        try:
            items.append(queue.get_nowait())
        except Empty:
            break
    return items


class Requests:
    """Outstanding host requests, at most one per message type."""

    ID_LIMIT = DEVICE_FRAME_ID      # host frame IDs stay below the device's

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
        self.statuses = Latest()
        self.blocks = Queue()               # VoutBlock and EdgeBlock, in arrival order
        self.logs = Queue(maxsize=256)
        self.commands, self.close_requested, self.done = Queue(), Event(), Event()
        self.thread = Thread(target=self._run, name="device-session")
        self.status = SessionStatus(ConnectionState.CONNECTING)
        self.requests = Requests(timeout)
        self.device = None
        self.info = None
        self.responses = {
            GET_DEVICE_INFO: self._on_device_info,
            STREAM_START: self._on_stream_started,
            STREAM_STOP: self._on_stream_stopped,
            TRANSMIT: self._on_transmitted,
            GET_AFE_CONFIG: self._on_afe_config,
            SET_AFE_CONFIG: self._on_afe_config,
        }
        self.events = {
            LOG: self._on_log,
            VOUT_SAMPLES: self._on_vout,
            OUT3_EDGES: self._on_edges,
            STREAM_END: self._on_stream_end,
        }

    # Public API, callable from any thread

    def open(self):
        self.thread.start()

    def start_stream(self):
        self.commands.put(StartStream())

    def stop_stream(self):
        self.commands.put(StopStream())

    def transmit(self, tone: ToneBurst):
        self.commands.put(Transmit(tone))

    def apply_afe(self, config: AfeConfig):
        self.commands.put(ApplyAfe(config))

    def close(self):
        self.close_requested.set()

    def take_blocks(self):
        return _drain(self.blocks)

    def take_logs(self):
        return _drain(self.logs, self.logs.maxsize)

    # Worker thread

    @property
    def connected(self):
        return self.status.connection == ConnectionState.CONNECTED

    @property
    def closing(self):
        return self.close_requested.is_set()

    @property
    def streaming(self):
        return self.status.acquisition in (AcquisitionState.STARTING, AcquisitionState.STREAMING)

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
            self._send(STREAM_STOP)     # end a stream a previous session left running
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
        if self.streaming:
            self._stop_stream()
        return not self.requests

    def _process_commands(self):
        for command in _drain(self.commands):
            if isinstance(command, StartStream):
                self._start_stream()
            elif isinstance(command, StopStream):
                self._stop_stream()
            elif isinstance(command, Transmit):
                self._start_transmit(command.tone)
            elif isinstance(command, ApplyAfe):
                self._apply_afe(command.config)

    def _start_stream(self):
        if self.connected and not self.closing and self.status.acquisition == AcquisitionState.STOPPED:
            self._status(acquisition=AcquisitionState.STARTING, error="")
            self._send(STREAM_START)

    def _stop_stream(self):
        if self.streaming and STREAM_STOP not in self.requests:
            self._status(acquisition=AcquisitionState.STOPPING)
            self._send(STREAM_STOP)

    def _start_transmit(self, tone):
        if self.connected and not self.closing and TRANSMIT not in self.requests:
            self._status(transmitting=True, transmit_message="Transmitting")
            self._send(TRANSMIT, encode_tone(tone))

    def _apply_afe(self, config):
        if self.connected and not self.closing and SET_AFE_CONFIG not in self.requests:
            self._send(SET_AFE_CONFIG, bytes(config))

    def _receive(self, packet):
        if packet.message_type in EVENTS:
            if not packet.frame_id & DEVICE_FRAME_ID:
                raise ProtocolError("Device event without a device frame ID")
            self.events[packet.message_type](packet)
        elif packet.message_type in self.responses:
            self.requests.close(packet)
            self.responses[packet.message_type](packet)
        else:
            raise ProtocolError(f"Unknown message type {packet.message_type}")

    def _on_device_info(self, packet):
        self.info = decode_info(packet.payload)
        self._status(connection=ConnectionState.CONNECTED, device_name=self.info.name)
        self._send(GET_AFE_CONFIG)

    def _on_stream_started(self, packet):
        result = decode_result(packet.payload)
        if result == OK:
            if self.status.acquisition == AcquisitionState.STARTING:
                self._status(acquisition=AcquisitionState.STREAMING)
        else:
            self._status(acquisition=AcquisitionState.STOPPED, error=RESULT_NAMES[result])

    def _on_stream_stopped(self, packet):
        result = decode_result(packet.payload)
        self._status(acquisition=AcquisitionState.STOPPED)
        if result != OK:
            self._status(error=RESULT_NAMES[result])
        if self.status.connection == ConnectionState.CONNECTING and not self.closing:
            self._send(GET_DEVICE_INFO)

    def _on_transmitted(self, packet):
        result = decode_result(packet.payload)
        self._status(transmitting=False, transmit_message="Complete" if result == OK else RESULT_NAMES[result])

    def _on_afe_config(self, packet):
        result, config = decode_afe(packet.payload)
        if result == OK:
            self._status(afe=config)
        else:
            self._status(error=f"Receiver configuration failed: {RESULT_NAMES[result]}")

    def _on_log(self, packet):
        try:
            self.logs.put_nowait(decode_log(packet.payload))
        except Full:
            pass

    # Stream data is only accepted once the device is known; data of a
    # previous session's stream may still arrive while connecting.

    def _on_vout(self, packet):
        if self.info is not None:
            self.blocks.put(decode_vout(packet.payload, self.info))

    def _on_edges(self, packet):
        if self.info is not None:
            self.blocks.put(decode_edges(packet.payload, self.info))

    def _on_stream_end(self, packet):
        result = decode_result(packet.payload)
        if self.info is not None:
            self._status(acquisition=AcquisitionState.STOPPED, error=f"Stream ended: {RESULT_NAMES[result]}")
