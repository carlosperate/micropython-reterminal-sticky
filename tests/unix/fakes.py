# Stand-ins for machine's classes, so code that takes pins and buses runs on the unix port.


class Pin:
    IN = 1
    OUT = 2
    PULL_UP = 1

    def __init__(self, level=0):
        self.mode = None
        self.pull = None
        self.level = level
        self.input = None  # what an outside device drives when the pin is an input
        self.on_change = None

    def init(self, mode=None, pull=-1, *, value=None):
        if value is not None:
            self(value)
        if mode is not None:
            self.mode = mode
        if pull != -1:
            self.pull = pull

    def __call__(self, value=None):
        if value is None:
            if self.mode == self.IN and self.input:
                return self.input()
            return self.level
        old, self.level = self.level, int(bool(value))
        if self.on_change and old != self.level:
            self.on_change(self.level)

    value = __call__


def script(levels):
    """An input that reads levels in turn, then holds the last one."""
    reads = []

    def read():
        reads.append(None)
        return levels[min(len(reads), len(levels)) - 1]

    return read


class SPI:
    """Logs (command, data) per DC-low byte, as a 4-wire SPI panel sees it."""

    def __init__(self, cs, dc):
        self.cs = cs
        self.dc = dc
        self.log = []

    def write(self, buf):
        if self.cs.level:
            raise AssertionError("write with CS high")
        if self.dc.level:
            self.log[-1][1].extend(buf)
        else:
            self.log.extend((b, bytearray()) for b in buf)

    def commands(self):
        return [cmd for cmd, _ in self.log]


class Panel:
    """A controller on bit-banged pins: answers REV (0x70) with reply, plays busy after a reset."""

    def __init__(self, reply=b"", busy=(0,)):
        self.pins = tuple(Pin() for _ in range(7))
        self.en, self.cs, self.dc, self.rst, self.sck, self.sda, self.busy = self.pins
        self.reply = reply
        self.script = busy
        self.commands = []
        self.resets = 0
        self.powered_at_reset = []
        self._bits = []
        self._out = []
        self._reads = 0
        self.rst.on_change = self._reset
        self.sck.on_change = self._clock
        self.sda.input = self._sda
        self.busy.input = self._busy

    def _reset(self, level):
        if level:
            self.resets += 1
            self.powered_at_reset.append(self.en.level)
            self._reads = 0

    # Mode 0: both sides sample on the rising edge.
    def _clock(self, level):
        if not level or self.cs.level:
            return
        if not self.dc.level and self.sda.mode == Pin.OUT:
            self._bits.append(self.sda.level)
            if len(self._bits) == 8:
                command = 0
                for bit in self._bits:
                    command = command << 1 | bit
                self.commands.append(command)
                self._bits = []
                if command == 0x70:
                    self._out = [b >> i & 1 for b in self.reply for i in range(7, -1, -1)]
        elif self.dc.level and self.sda.mode == Pin.IN and self._out:
            self._out.pop(0)

    def _sda(self):
        if self._out:
            return self._out[0]
        return 1 if self.sda.pull == Pin.PULL_UP else 0

    # The script's last level holds.
    def _busy(self):
        level = self.script[min(self._reads, len(self.script) - 1)]
        self._reads += 1
        return level


class BLE:
    """bluetooth.BLE's surface that sticky.bleuart uses; the test plays the central."""

    TX = 1
    RX = 2

    def __init__(self):
        self.handler = None
        self.advertising = False
        self.notified = []
        self.disconnected = []
        self.fail_notify = 0
        self.config_set = {}
        self._values = {}

    def active(self, on=None):
        return True

    def config(self, *args, **kwargs):
        self.config_set.update(kwargs)
        if args == ("mac",):
            return (0, b"\x00\x11\x22\x33\x69\xf2")

    def gatts_register_services(self, services):
        return ((self.TX, self.RX),)

    def gatts_set_buffer(self, handle, size, append):
        pass

    # In append mode a read clears the value, as on the board.
    def gatts_read(self, handle):
        return self._values.pop(handle, b"")

    def gatts_notify(self, conn, handle, data):
        if self.fail_notify:
            self.fail_notify -= 1
            raise OSError(12)
        self.notified.append(bytes(data))

    def gap_advertise(self, interval_us, adv_data=None, resp_data=None):
        self.advertising = interval_us is not None

    def gap_disconnect(self, conn):
        self.disconnected.append(conn)

    def irq(self, handler):
        self.handler = handler

    # The central's side.
    def connect(self, conn=7):
        self.advertising = False
        self.handler(1, (conn, 0, b""))

    def disconnect(self, conn=7):
        self.handler(2, (conn, 0, b""))

    def write(self, data, conn=7):
        self._values[self.RX] = data
        self.handler(3, (conn, self.RX))

    def exchange_mtu(self, mtu, conn=7):
        self.handler(21, (conn, mtu))


def bluetooth_module(ble):
    """A stand-in for the bluetooth module, to put in sys.modules before importing bleuart."""

    class Module:
        @staticmethod
        def BLE():
            return ble

        @staticmethod
        def UUID(text):
            return bytes(int(text.replace("-", "")[i : i + 2], 16) for i in range(0, 32, 2))

    return Module
