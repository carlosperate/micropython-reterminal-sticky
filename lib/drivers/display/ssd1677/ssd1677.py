# SSD1677 e-paper controller. The glass's size and settings come from the caller, as each glass
# wants its own. A full refresh is show()'s waveform with every pixel marked as changed;
# show_grey() and clean() use the controller's own waveforms.

import time

import micropython
from micropython import const

# An ESP32 SPI transaction holds at most 4092 bytes (machine_hw_spi.c): slices are whole rows
# under it, so each goes out in one.
_TRANSACTION = const(4092)

_DRIVER_OUTPUT = const(0x01)
_BOOSTER = const(0x0C)
_DEEP_SLEEP = const(0x10)
_DATA_ENTRY = const(0x11)
_SW_RESET = const(0x12)
_TEMP_SENSOR = const(0x18)
_TEMP_WRITE = const(0x1A)
_ACTIVATE = const(0x20)
_UPDATE_1 = const(0x21)
_UPDATE_2 = const(0x22)
_RAM_NEW = const(0x24)
_RAM_OLD = const(0x26)
_BORDER = const(0x3C)
_X_WINDOW = const(0x44)
_Y_WINDOW = const(0x45)
_FILL_OLD = const(0x46)
_FILL_NEW = const(0x47)
_X_COUNTER = const(0x4E)
_Y_COUNTER = const(0x4F)


@micropython.viper
def _invert(dst: ptr8, src: ptr8, start: int, n: int):
    for i in range(n):
        dst[i] = src[start + i] ^ 0xFF


@micropython.viper
def _fill(dst: ptr8, value: int, start: int, n: int):
    for i in range(n):
        dst[i] = value


# A GS2_HMSB byte's four pixels as one plane's nibble. GS2_HMSB keeps the leftmost pixel in its
# lowest two bits; MONO_HLSB, in bit 7; the nibble, in bit 3.
def _grey_table(levels, plane):
    bits = [level[plane] for level in levels]
    table = bytearray(256)
    for b in range(256):
        for k in range(4):
            table[b] |= bits[(b >> 2 * k) & 3] << (3 - k)
    return table


# A window's first and last address: a direction counting down starts at the end.
def _span(up, size):
    first, last = (0, size - 1) if up else (size - 1, 0)
    return bytes((first & 0xFF, first >> 8, last & 0xFF, last >> 8))


@micropython.viper
def _grey_plane(dst: ptr8, src: ptr8, start: int, n: int, table: ptr8):
    for i in range(n):
        j = 2 * (start + i)
        dst[i] = (table[src[j]] << 4) | table[src[j + 1]]


class SSD1677:
    """Frames are MONO_HLSB, width * height // 8 bytes, with 1 for white. Grey frames are
    GS2_HMSB, twice that, 0 black to 3 white.

    The glass's settings: data_entry is sent with 0x11 (bits 0 and 1 only). refresh, clean and
    power_off are (border, update) pairs, sent with 0x3C and 0x22, for show(), clean() and
    power_off(). booster is 0x0C's data. grey is (border, update, temperature, levels) for
    show_grey(): temperature is sent with 0x1A, and levels gives each grey level's bits in RAM
    0x24 and 0x26. gate_scan is 0x01's last byte and temp_sensor 0x18's.
    """

    def __init__(
        self,
        spi,
        cs,
        dc,
        rst,
        busy,
        width,
        height,
        *,
        data_entry,
        refresh,
        clean,
        power_off,
        booster,
        grey=None,
        gate_scan=0x02,
        temp_sensor=0x80,
        timeout_ms=10_000,
    ):
        if width <= 0 or height <= 0 or width % 8:
            raise ValueError("size")
        # Bit 2 addresses along Y first; frames go row by row.
        if data_entry & ~3:
            raise ValueError("data_entry")
        # Each refresh must turn the clock and analog supply on, or it runs unpowered.
        for setting in (refresh, clean, grey or refresh):
            if setting[1] & 0xC0 != 0xC0:
                raise ValueError("update")
        if not power_off[1] & 0x02:
            raise ValueError("power_off")
        self.width = width
        self.height = height
        self._plane_size = width * height // 8
        # A row wider than a transaction still goes out whole: the port splits it.
        rows = max(1, _TRANSACTION // (width // 8))
        self._data_entry = data_entry
        self._refresh = refresh
        self._clean = clean
        self._power_off = power_off
        self._grey = grey
        self._tables = None
        gates = height - 1
        self._driver_output = bytes((gates & 0xFF, gates >> 8, gate_scan))
        self._booster = booster
        self._temp_sensor = temp_sensor
        self._x = _span(data_entry & 1, width)
        self._y = _span(data_entry & 2, height)
        self._home_x = self._x[:2]
        self._home_y = self._y[:2]
        self.spi = spi
        self.cs = cs
        self.dc = dc
        self.rst = rst
        self._busy = busy
        self.timeout_ms = timeout_ms
        cs.init(cs.OUT, value=1)
        dc.init(dc.OUT, value=0)
        rst.init(rst.OUT, value=1)
        busy.init(busy.IN, None)
        self._cmd = bytearray(1)
        self._arg = bytearray(1)
        self._buf = bytearray(min(rows * width // 8, self._plane_size))
        self._asleep = False
        self._powered = False
        # The glass may not match the planes (unknown at first, greys, or a transfer cut short), so
        # the next show() drives every pixel. init() leaves it alone; only a show() that gets as
        # far as starting its refresh clears it.
        self._stale = True
        # Until an init() completes (never run, or cut short with reset maybe still held), the
        # next refresh runs one.
        self._init_pending = True

    def init(self):
        """Reset the controller and fill both planes white.

        The first refresh runs it if nothing has. Call it to set the panel up early, or to reset
        a hung one.
        """
        self._init_pending = True
        self._reset()
        self._command(_SW_RESET)
        # BUSY may not rise in time for the first sample.
        time.sleep_ms(10)
        self.wait()
        self._command_byte(_TEMP_SENSOR, self._temp_sensor)
        self._command(_BOOSTER, self._booster)
        self._command(_DRIVER_OUTPUT, self._driver_output)
        self._command_byte(_BORDER, self._power_off[0])
        self._command_byte(_DATA_ENTRY, self._data_entry)
        self._command(_X_WINDOW, self._x)
        self._command(_Y_WINDOW, self._y)
        self._home()
        self._command(_FILL_OLD, b"\xf7")
        self.wait()
        self._command(_FILL_NEW, b"\xf7")
        self.wait()
        self._init_pending = False

    # The reset turns the analog supply off; cut short, it may or may not have.
    def _reset(self):
        self._powered = None
        self.rst(0)
        time.sleep_ms(10)
        self.rst(1)
        time.sleep_ms(10)
        self._asleep = False
        self._powered = False

    # In deep sleep BUSY stays high, though nothing is running.
    def busy(self):
        return not self._asleep and self._busy() == 1

    def wait(self, timeout_ms=None):
        start = time.ticks_ms()
        while self.busy():
            self._check(start, timeout_ms)
            time.sleep_ms(1)

    async def wait_async(self, timeout_ms=None):
        import asyncio

        start = time.ticks_ms()
        while self.busy():
            self._check(start, timeout_ms)
            await asyncio.sleep_ms(10)

    def show(self, frame, old=None):
        """Start a refresh to frame and return without waiting for it.

        old is what the glass shows now, and only pixels that differ from it change. Without it
        every pixel is driven: a full refresh. The driver's first refresh is full whatever old is,
        as is one after show_grey(), clean() or a show() cut short. Unless an init() has completed
        since the driver was built or last slept, show() runs one first.
        """
        size = self._plane_size
        if len(frame) != size or old is not None and len(old) != size:
            raise ValueError("frame size")
        if self._asleep or self._init_pending:
            self.init()
        self.wait()
        if self._stale:
            old = None
        self._stale = True
        self._plane(_RAM_NEW, frame)
        if old is None:
            self._converted_plane(_RAM_OLD, _invert, frame)
        else:
            self._plane(_RAM_OLD, old)
        self._command(_UPDATE_1, b"\x00")
        border, update = self._refresh
        self._command_byte(_BORDER, border)
        self._activate(update)
        self._stale = False

    def show_grey(self, frame):
        """Start a four-grey refresh to frame and return without waiting for it.

        frame is read only during the call. The controller is reset first. A partial can't clear
        greys, so the next show() is full whatever old it's given. Without grey settings it
        raises NotImplementedError.
        """
        if self._grey is None:
            raise NotImplementedError("no grey settings")
        if len(frame) != 2 * self._plane_size:
            raise ValueError("frame size")
        border, update, temperature, levels = self._grey
        # Built at the first grey refresh, so a programme without greys never holds them.
        if self._tables is None:
            self._tables = (_grey_table(levels, 0), _grey_table(levels, 1))
        high, low = self._tables
        self._restart()
        self._command_byte(_BORDER, border)
        self._converted_plane(_RAM_NEW, _grey_plane, frame, high)
        self._converted_plane(_RAM_OLD, _grey_plane, frame, low)
        self._command(_UPDATE_1, b"\x00")
        # The forced temperature picks the OTP's grey waveform.
        self._command(_TEMP_WRITE, temperature)
        self._activate(update)

    def clean(self, white=True):
        """Start a full refresh to all white (or black) with the controller's own waveform, and
        return without waiting for it.

        It flashes, but drives the glass harder than show(): black then white before show_grey()
        weakens what a long-held picture leaves showing through greys. The next show() is full.
        """
        self._restart()
        border, update = self._clean
        self._command_byte(_BORDER, border)
        fill = 0xFF if white else 0x00
        self._converted_plane(_RAM_NEW, _fill, fill)
        self._converted_plane(_RAM_OLD, _fill, fill)
        self._command(_UPDATE_1, b"\x00")
        self._activate(update)

    # An update with bit 1 leaves the supply off; the constructor checks every other turns it on.
    def _activate(self, update):
        self._command_byte(_UPDATE_2, update)
        after = not update & 0x02
        # Unknown while 0x20 goes out, unless it ends as it started.
        if self._powered is not after:
            self._powered = None
        self._command(_ACTIVATE)
        self._powered = after
        time.sleep_ms(2)

    # Another waveform needs the controller reset first, as Seeed's driver does between modes: on
    # a unit, a second grey refresh without one swapped the two middle greys.
    def _restart(self):
        # Before the reset, which would cut a running refresh short. None runs after an init()
        # cut short, when BUSY may mean nothing.
        if not self._init_pending:
            self.wait()
        self._stale = True
        self.init()

    def power_off(self):
        """Turn the analog supply off after the refresh.

        Returns without waiting for the power-down (about 140 ms), as show() does for a refresh.
        """
        # A second power-off with the supply already off leaves BUSY high until a reset.
        if self._powered is False:
            return
        self._wait_capped()
        # Unknown after a cut show() or reset: a reset turns it off either way. init() can wait.
        if self._powered is None:
            self._init_pending = True
            self._reset()
            return
        border, update = self._power_off
        self._command_byte(_BORDER, border)
        self._activate(update)

    def sleep(self):
        """Power down and sleep, losing both planes. The next show() wakes it, and should be full."""
        if self._asleep:
            return
        self.power_off()
        self._wait_capped()
        # Set first: if cut short, the next show() resets an awake panel, which is harmless.
        self._asleep = True
        self._command(_DEEP_SLEEP, b"\x03")

    # draftling caps these waits at 3 s, after one hung for its full 30 s: sleep goes ahead.
    def _wait_capped(self):
        try:
            self.wait(3000)
        except OSError:
            pass

    def _check(self, start, timeout_ms):
        if timeout_ms is None:
            timeout_ms = self.timeout_ms
        if time.ticks_diff(time.ticks_ms(), start) >= timeout_ms:
            raise OSError("SSD1677 busy timeout")

    def _begin(self, cmd):
        self.cs(0)
        self.dc(0)
        self._cmd[0] = cmd
        self.spi.write(self._cmd)
        self.dc(1)

    # CS goes high even on Ctrl-C mid-transfer, or the panel would hear the SD card's traffic.
    def _command(self, cmd, data=None):
        try:
            self._begin(cmd)
            if data:
                self.spi.write(data)
        finally:
            self.cs(1)

    def _command_byte(self, cmd, value):
        self._arg[0] = value
        self._command(cmd, self._arg)

    def _home(self):
        self._command(_X_COUNTER, self._home_x)
        self._command(_Y_COUNTER, self._home_y)

    def _plane(self, cmd, frame):
        self._home()
        self._command(cmd, frame)

    # A plane worked out a slice at a time, so no second frame-sized buffer is needed.
    def _converted_plane(self, cmd, convert, src, *args):
        self._home()
        buf = self._buf
        size = self._plane_size
        step = len(buf)
        try:
            self._begin(cmd)
            for start in range(0, size, step):
                n = min(step, size - start)
                convert(buf, src, start, n, *args)
                self.spi.write(buf if n == step else memoryview(buf)[:n])
        finally:
            self.cs(1)
