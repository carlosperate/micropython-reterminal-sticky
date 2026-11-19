# One set of tests for what Display relies on: on the unix port against SimPanel and the SSD1677
# driver on fakes, so the simulator can't drift from the driver; on the unit against the real one.
import asyncio
import sys
import unittest

import framebuf
import reterminal_sticky
import ssd1677
from panel_log import KINDS, Recording, counts, leave_white

BOARD = sys.platform == "esp32"


# A card that reads as a test on the glass.
def card(label, y):
    buf = bytearray(48000)
    fb = framebuf.FrameBuffer(buf, 800, 480, framebuf.MONO_HLSB)
    fb.fill(1)
    fb.rect(0, 0, 800, 480, 0)
    fb.text("panel contract " + label, 16, y, 0)
    return bytes(buf)


# Neither is the other's inverse, so the driver's planes tell a partial from a full refresh.
A = card("A", 16)
B = card("B", 32)
GREY = b"\xff" * 96000
GLASS = reterminal_sticky._GLASS


class Contract:
    """The tests; a subclass builds the panel and reads what it did.

    make(timeout_ms), counts() as {kind: n}, powered(panel), asleep(panel), and
    refresh_runs(panel, forever), after which a refresh holds BUSY for ever or briefly.
    """

    def assertCounts(self, **expected):
        want = dict.fromkeys(KINDS, 0)
        want.update(expected)
        self.assertEqual(self.counts(), want)

    def test_size(self):
        panel = self.make()
        self.assertEqual((panel.width, panel.height), (800, 480))
        for call in (
            lambda: panel.show(bytes(100)),
            lambda: panel.show(A, bytes(100)),
            lambda: panel.show_grey(A),
        ):
            with self.assertRaises(ValueError):
                call()
        self.assertCounts()

    def test_not_busy_when_built(self):
        panel = self.make(timeout_ms=10)
        self.assertFalse(panel.busy())
        panel.wait()

    # Nobody knows what the glass shows yet, so old is ignored.
    def test_first_show_is_full(self):
        panel = self.make()
        panel.show(B, A)
        self.assertCounts(full=1)

    def test_partial(self):
        panel = self.make()
        panel.show(A)
        panel.show(B, A)
        self.assertCounts(full=1, partial=1)

    # A partial can't clear greys or a clean, so the next refresh is full whatever old is.
    def test_full_after_grey_and_clean(self):
        for kind, call in (("grey", lambda p: p.show_grey(GREY)), ("clean", lambda p: p.clean())):
            panel = self.make()
            panel.show(A)
            call(panel)
            panel.show(B, A)
            panel.show(A, B)
            self.assertCounts(full=2, partial=1, **{kind: 1})

    # Only a supply a refresh turned on is turned off: a second power-off held BUSY on a unit.
    def test_power_off(self):
        panel = self.make()
        panel.power_off()
        self.assertCounts()
        panel.show(A)
        self.assertTrue(self.powered(panel))
        panel.power_off()
        panel.power_off()
        self.assertFalse(self.powered(panel))
        self.assertCounts(full=1, power_off=1)

    # Their waveforms turn the supply off themselves.
    def test_grey_and_clean_leave_supply_off(self):
        for kind, call in (("grey", lambda p: p.show_grey(GREY)), ("clean", lambda p: p.clean())):
            panel = self.make()
            panel.show(A)
            call(panel)
            self.assertFalse(self.powered(panel))
            panel.power_off()
            self.assertCounts(full=1, **{kind: 1})

    # Asleep, BUSY means nothing; show() wakes the panel and sends both planes again.
    def test_sleep(self):
        panel = self.make()
        panel.show(A)
        panel.sleep()
        panel.sleep()
        self.assertTrue(self.asleep(panel))
        self.assertFalse(panel.busy())
        panel.wait(0)
        self.assertCounts(full=1, power_off=1)
        panel.show(B, A)
        self.assertFalse(self.asleep(panel))
        self.assertCounts(full=1, partial=1, power_off=1)

    def test_wait(self):
        panel = self.make(timeout_ms=1000)
        self.refresh_runs(panel, forever=False)
        panel.show(A)
        self.assertTrue(panel.busy())
        asyncio.run(panel.wait_async())
        self.assertFalse(panel.busy())

    # A refresh outlasting the timeout times every wait out, but power-off and sleep go ahead.
    def test_timeout(self):
        panel = self.make(timeout_ms=20)
        self.refresh_runs(panel, forever=True)
        panel.show(A)
        for wait in (lambda: panel.wait(0), panel.wait, lambda: asyncio.run(panel.wait_async())):
            with self.assertRaises(OSError):
                wait()
        panel.sleep()
        self.assertTrue(self.asleep(panel))
        self.assertCounts(full=1, power_off=1)


class DriverCase(Contract):
    """Counts what the driver sent through its Recording, self.bus."""

    def counts(self):
        return counts(self.bus.log)

    def powered(self, panel):
        return panel._powered

    def asleep(self, panel):
        return panel._asleep is True


if BOARD:

    class TestDriver(DriverCase, unittest.TestCase):
        panel = None

        def make(self, timeout_ms=10_000):
            if self.panel:
                self.panel.sleep()
            try:
                self.panel = reterminal_sticky.panel()
            except NotImplementedError as e:
                self.skipTest(str(e))
            self.panel.timeout_ms = timeout_ms
            self.bus = self.panel.spi = Recording(self.panel.spi, self.panel._cmd)
            return self.panel

        # A real refresh holds BUSY for about 480 ms, past the tests' 20 ms timeout.
        def refresh_runs(self, panel, forever):
            pass

        def tearDown(self):
            if self.panel:
                self.panel.sleep()
                self.panel = None

        @classmethod
        def tearDownClass(cls):
            leave_white()

else:
    sys.path.append("tests/unix")
    from fakes import SPI, Pin, script
    from sticky_sim import SimPanel

    class TestSimPanel(Contract, unittest.TestCase):
        def make(self, timeout_ms=10_000):
            self.panel = SimPanel(timeout_ms=timeout_ms)
            return self.panel

        def counts(self):
            p = self.panel
            return dict(zip(KINDS, (p.full, p.partial, p.grey, p.cleaned, p.powered_off)))

        def powered(self, panel):
            return panel.powered

        def asleep(self, panel):
            return panel.asleep

        def refresh_runs(self, panel, forever):
            panel.refresh_ms = 10**6 if forever else 30

    class TestDriver(DriverCase, unittest.TestCase):
        def make(self, timeout_ms=10_000):
            cs, dc, rst, self.busy = Pin(), Pin(), Pin(), Pin()
            self.after_activate = None
            panel = ssd1677.SSD1677(
                SPI(cs, dc), cs, dc, rst, self.busy, timeout_ms=timeout_ms, **GLASS
            )
            self.bus = panel.spi = Recording(panel.spi, panel._cmd, self.activated)
            return panel

        # BUSY as refresh_runs() said, from the 0x20 that starts each update.
        def activated(self, cmd):
            if self.after_activate and cmd == 0x20:
                self.busy.input = script(self.after_activate)

        def refresh_runs(self, panel, forever):
            self.after_activate = [1] if forever else [1, 1, 1, 0]


if __name__ == "__main__":
    unittest.main()
