# The Nordic UART Service over BLE as a stream: a byte pipe that apps (nRF Connect, Bluefruit
# Connect, ViperIDE) and Web Bluetooth pages already speak. Driven from the BLE IRQ, so it needs
# no event loop and works at the bare REPL, as os.dupterm()'s terminal (repl()).

import io
import os
import time

import bluetooth
from micropython import const

_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE = const(3)
_IRQ_MTU_EXCHANGED = const(21)

_FLAG_WRITE_NO_RESPONSE = const(0x0004)
_FLAG_WRITE = const(0x0008)
_FLAG_NOTIFY = const(0x0010)

_MP_STREAM_POLL = const(3)
_MP_STREAM_POLL_RD = const(0x0001)
_MP_STREAM_POLL_WR = const(0x0004)

_ADV_TYPE_FLAGS = const(0x01)
_ADV_TYPE_NAME = const(0x09)
_ADV_TYPE_UUID128 = const(0x07)

# Twice the largest attribute value: the IRQ empties it on every write, so it only fills when the
# stack has cut data, which it does silently.
_GATT_BUF = const(1024)
_INTERVAL_US = const(100_000)
_RETRIES = const(5)

UART_UUID = bluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
_TX = (bluetooth.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E"), _FLAG_NOTIFY)
_RX = (
    bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E"),
    _FLAG_WRITE | _FLAG_WRITE_NO_RESPONSE,
)
SERVICE = (UART_UUID, (_TX, _RX))


def _field(kind, value):
    return bytes((len(value) + 1, kind)) + value


class BLEUART(io.IOBase):
    """Advertise as name (sticky-XXXX from the MAC by default) and serve one central at a time.

    Registers the GATT table and owns the BLE IRQ, so it doesn't mix with aioble.
    """

    def __init__(self, name=None, rxbuf=1024):
        self._ble = bluetooth.BLE()
        self._ble.active(True)
        if name is None:
            mac = self._ble.config("mac")[1]
            name = "sticky-%02x%02x" % (mac[-2], mac[-1])
        self.name = name
        self._ble.config(gap_name=name)
        ((self._tx, self._rx),) = self._ble.gatts_register_services((SERVICE,))
        self._ble.gatts_set_buffer(self._rx, _GATT_BUF, True)
        self._size = rxbuf
        self.overflows = 0
        self.gaps = 0
        self.dropped = 0
        self._conn = None
        self._closed = False
        # Read from an index: os.dupterm() reads a byte at a time, and slicing would copy the
        # rest of the buffer for each one.
        self._buf = bytearray()
        self._start = 0
        self._mtu = 23
        self._ble.irq(self._irq)
        self._advertise()

    @property
    def connected(self):
        return self._conn is not None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def any(self):
        return len(self._buf) - self._start

    def read(self, n=-1):
        """The bytes waiting, at most n; None if there are none. Doesn't wait."""
        avail = self.any()
        if not avail:
            return None
        if n < 0 or n > avail:
            n = avail
        data = bytes(self._buf[self._start : self._start + n])
        self._start += n
        return data

    def readline(self):
        """Up to and including the first newline, or all that's waiting; None if nothing is."""
        i = bytes(self._buf[self._start :]).find(b"\n")
        return self.read(-1 if i < 0 else i + 1)

    def readinto(self, buf):
        n = min(len(buf), self.any())
        if not n:
            return None
        buf[:n] = self._buf[self._start : self._start + n]
        self._start += n
        return n

    def write(self, buf):
        """Notify buf to the central in MTU-sized chunks; returns the bytes sent, 0 with none."""
        if isinstance(buf, str):
            buf = buf.encode()
        conn = self._conn
        if conn is None:
            return 0
        step = max(20, self._mtu - 3)
        view = memoryview(buf)
        for i in range(0, len(buf), step):
            if not self._notify(conn, view[i : i + step]):
                # Never raise: os.dupterm() detaches a terminal that does.
                self.dropped += len(buf) - i
                return i
        return len(buf)

    def ioctl(self, op, arg):
        if op != _MP_STREAM_POLL:
            return 0
        ready = _MP_STREAM_POLL_WR if arg & _MP_STREAM_POLL_WR else 0
        if arg & _MP_STREAM_POLL_RD and self._buf:
            ready |= _MP_STREAM_POLL_RD
        return ready

    def close(self):
        """Stop advertising and drop the central. The radio stays on: that's the app's to stop."""
        self._closed = True
        self._ble.gap_advertise(None)
        if self._conn is not None:
            self._ble.gap_disconnect(self._conn)
        self._conn = None

    def _advertise(self):
        adv = _field(_ADV_TYPE_FLAGS, b"\x06") + _field(_ADV_TYPE_NAME, self.name.encode())
        resp = _field(_ADV_TYPE_UUID128, bytes(UART_UUID))
        self._ble.gap_advertise(_INTERVAL_US, adv_data=adv, resp_data=resp)

    # A break in the stream: what was waiting goes, and gaps tells readers to drop what they hold.
    def _gap(self):
        self._buf = bytearray()
        self._start = 0
        self.gaps += 1

    def _notify(self, conn, chunk):
        for _ in range(_RETRIES):
            # A disconnect during the retries ends them.
            if self._conn != conn:
                return False
            try:
                self._ble.gatts_notify(conn, self._tx, chunk)
                return True
            except OSError:
                # The stack is out of buffers for the moment.
                time.sleep_ms(5)
        return False

    def _received(self, data):
        if len(data) >= _GATT_BUF or len(data) > self._size - self.any():
            self.overflows += 1
            self._gap()
            return
        if self._start:
            self._buf = self._buf[self._start :]
            self._start = 0
        self._buf += data

    def _irq(self, event, data):
        if event == _IRQ_CENTRAL_CONNECT:
            self._conn = data[0]
            self._mtu = 23
            self._gap()
        elif event == _IRQ_CENTRAL_DISCONNECT:
            self._conn = None
            if not self._closed:
                self._advertise()
        elif event == _IRQ_GATTS_WRITE and data[1] == self._rx:
            # In append mode a read also clears the value (docs/library/bluetooth.rst).
            self._received(self._ble.gatts_read(self._rx))
            if hasattr(os, "dupterm_notify"):
                os.dupterm_notify(None)
        elif event == _IRQ_MTU_EXCHANGED:
            self._mtu = data[1]


def repl(name=None):
    """A BLEUART as a second REPL terminal, from boot.py. Not for a programme using it for data."""
    uart = BLEUART(name)
    os.dupterm(uart)
    return uart
