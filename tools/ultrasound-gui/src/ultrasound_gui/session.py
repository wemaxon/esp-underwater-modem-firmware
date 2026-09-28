from dataclasses import dataclass, replace
from enum import Enum
from queue import Empty, Queue
from threading import Event, Lock, Thread
from time import monotonic

from .model import ToneBurst
from .protocol import CAPTURE, CANCELLED, GET_DEVICE_INFO, OK, RESULT_NAMES, STOP, TIMEOUT, TRANSMIT, Packet, ProtocolError, decode_capture, decode_info, encode_tone


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


class Latest:
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


class Session:
    def __init__(self, device_factory, timeout=3.0):
        self.device_factory, self.timeout = device_factory, timeout
        self.statuses, self.frames = Latest(), Latest()
        self.commands, self.close_requested, self.done = Queue(), Event(), Event()
        self.thread = Thread(target=self._run, name="modem-session")
        self.status = SessionStatus(ConnectionState.CONNECTING)
        self.pending = {}
        self.request_id = 0
        self.repeat = False
        self.stopping = False

    def open(self):
        self.thread.start()

    def start_acquisition(self, repeat=False):
        self.commands.put(bool(repeat))

    def stop_acquisition(self):
        self.commands.put(None)

    def transmit(self, tone: ToneBurst):
        self.commands.put(tone)

    def close(self):
        self.close_requested.set()

    def _status(self, **changes):
        self.status = replace(self.status, **changes)
        self.statuses.put(self.status)

    def _send(self, message_type, payload=b""):
        self.request_id = (self.request_id + 1) % 0x8000
        self.pending[message_type] = (self.request_id, monotonic() + self.timeout)
        self.device.send(Packet(message_type, self.request_id, payload))

    def _stop(self):
        self.repeat = False
        if not self.stopping:
            self.stopping = True
            self._status(acquisition=AcquisitionState.STOPPING)
            self._send(STOP)

    def _receive(self, packet):
        if self.status.connection == ConnectionState.CONNECTING and packet.message_type == CAPTURE:
            return
        expected = self.pending.pop(packet.message_type, None)
        if expected is None or packet.frame_id != expected[0]:
            raise ProtocolError("Unexpected response type or frame ID")
        if packet.message_type == GET_DEVICE_INFO:
            self.info = decode_info(packet.payload)
            self._status(connection=ConnectionState.CONNECTED, device_name=self.info.name)
        elif packet.message_type == TRANSMIT:
            if len(packet.payload) != 1 or packet.payload[0] >= len(RESULT_NAMES):
                raise ProtocolError("Invalid transmit response")
            result = packet.payload[0]
            self._status(transmitting=False, transmit_message="Complete" if result == OK else RESULT_NAMES[result])
        elif packet.message_type == STOP:
            if packet.payload != bytes([OK]) or CAPTURE in self.pending:
                raise ProtocolError("Invalid STOP response")
            self.stopping = False
            self._status(acquisition=AcquisitionState.STOPPED)
            if self.status.connection == ConnectionState.CONNECTING:
                self._send(GET_DEVICE_INFO)
        elif packet.message_type == CAPTURE:
            if len(packet.payload) == 1:
                result = packet.payload[0]
                if result == CANCELLED and self.stopping:
                    return
                if result == TIMEOUT and self.repeat and not self.stopping:
                    self._send(CAPTURE)
                    return
                self.repeat = False
                error = RESULT_NAMES[result] if 0 < result < len(RESULT_NAMES) else "Invalid capture result"
                self._status(acquisition=AcquisitionState.STOPPED, error=error)
            else:
                capture = decode_capture(packet.payload, self.info)
                self.frames.put(capture)
                self._status(captures_received=self.status.captures_received + 1)
                if self.repeat and not self.stopping and not self.close_requested.is_set():
                    self._send(CAPTURE)
                elif not self.stopping:
                    self._status(acquisition=AcquisitionState.COMPLETE)

    def _run(self):
        self.statuses.put(self.status)
        device, error = None, ""
        try:
            device = self.device = self.device_factory()
            self._send(STOP)
            while True:
                if self.close_requested.is_set() and self.status.connection == ConnectionState.CONNECTED:
                    if not self.pending:
                        break
                    if CAPTURE in self.pending:
                        self._stop()
                try:
                    repeat = self.commands.get_nowait()
                except Empty:
                    pass
                else:
                    if isinstance(repeat, ToneBurst):
                        if self.status.connection == ConnectionState.CONNECTED and TRANSMIT not in self.pending and not self.close_requested.is_set():
                            self._status(transmitting=True, transmit_message="Transmitting")
                            self._send(TRANSMIT, encode_tone(repeat))
                    elif repeat is None:
                        self.repeat = False
                        if CAPTURE in self.pending:
                            self._stop()
                        elif STOP not in self.pending:
                            self._status(acquisition=AcquisitionState.STOPPED)
                    elif CAPTURE not in self.pending and STOP not in self.pending and self.status.connection == ConnectionState.CONNECTED and not self.close_requested.is_set():
                        self.repeat = repeat
                        self._status(acquisition=AcquisitionState.CAPTURING, error="")
                        self._send(CAPTURE)
                for packet in device.read():
                    self._receive(packet)
                if any(monotonic() >= deadline for _, deadline in self.pending.values()):
                    raise TimeoutError("Device response timed out")
        except Exception as exc:
            error = str(exc)
        finally:
            if device is not None:
                device.close()
            self._status(connection=ConnectionState.DISCONNECTED, acquisition=AcquisitionState.STOPPED, transmitting=False, transmit_message="Connection closed" if self.status.transmitting else self.status.transmit_message, error=error or self.status.error)
            self.done.set()
