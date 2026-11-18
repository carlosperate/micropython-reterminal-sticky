# Leaves a test card on the glass: "TOP LEFT" reads normally in the corner it names, and the
# counter reads 2 with no trace of the 1 under it. test_grey shows four grey bands in between:
# black to white across the top, white to black below.
import time
import unittest

import framebuf
import reterminal_sticky
import ssd1677
from machine import Pin


def big_text(fb, text, x, y, scale):
    small = framebuf.FrameBuffer(bytearray(8 * len(text)), 8 * len(text), 8, framebuf.MONO_HLSB)
    small.fill(1)
    small.text(text, 0, 0, 0)
    for gy in range(8):
        for gx in range(8 * len(text)):
            if not small.pixel(gx, gy):
                fb.fill_rect(x + gx * scale, y + gy * scale, scale, scale, 0)


def card(panel, count):
    w, h = panel.width, panel.height
    buf = bytearray(w * h // 8)
    fb = framebuf.FrameBuffer(buf, w, h, framebuf.MONO_HLSB)
    fb.fill(1)
    fb.rect(0, 0, w, h, 0)
    fb.fill_rect(0, 0, 40, 40, 0)
    big_text(fb, "TOP LEFT", 56, 8, 4)
    big_text(fb, str(count), 336, 176, 16)
    return buf


def grey_card(panel):
    buf = bytearray(panel.width * panel.height // 4)
    fb = framebuf.FrameBuffer(buf, panel.width, panel.height, framebuf.GS2_HMSB)
    for level in range(4):
        fb.fill_rect(200 * level, 0, 200, 240, level)
        fb.fill_rect(600 - 200 * level, 240, 200, 240, level)
    return buf


class TestSSD1677(unittest.TestCase):
    def refresh(self, panel, *frames):
        start = time.ticks_ms()
        panel.show(*frames)
        self.assertTrue(panel.busy(), "BUSY didn't rise")
        panel.wait()
        return time.ticks_diff(time.ticks_ms(), start)

    def test_card(self):
        try:
            panel = reterminal_sticky.panel()
        except NotImplementedError as e:
            self.skipTest(str(e))
        self.assertEqual((panel.width, panel.height), (800, 480))
        first, second = card(panel, 1), card(panel, 2)
        self.assertTrue(self.refresh(panel, first) < 10_000)
        self.assertTrue(self.refresh(panel, second, first) < 10_000)
        # 0x22 FC leaves the analog supply on; the card stays on the glass.
        panel.sleep()

    def test_power_off(self):
        try:
            panel = reterminal_sticky.panel()
        except NotImplementedError as e:
            self.skipTest(str(e))
        first, second = card(panel, 3), card(panel, 4)
        # Marked on once the refresh starts, so a power-off straight after it runs.
        panel.show(first)
        self.assertTrue(panel._powered)
        panel.power_off()
        self.assertTrue(panel.busy(), "BUSY didn't rise for the power-down")
        panel.wait()
        # A second power-off with the supply off once left BUSY high until a reset.
        panel.power_off()
        self.assertFalse(panel.busy())
        # The planes survive a power-off, so a partial still works.
        self.assertTrue(self.refresh(panel, second, first) < 10_000)
        panel.sleep()

    # A show() cut at 0x20 leaves the supply unknown, so power_off() resets. A power-off with the
    # supply off holds BUSY high, and one after that reset does: the reset turned it off.
    def test_reset_turns_supply_off(self):
        try:
            panel = reterminal_sticky.panel()
        except NotImplementedError as e:
            self.skipTest(str(e))
        try:
            self.refresh(panel, card(panel, 5))
            panel._powered = None
            panel.power_off()
            panel._powered = True
            panel.power_off()
            with self.assertRaises(OSError):
                panel.wait(1000)
            panel.init()
            self.assertTrue(self.refresh(panel, card(panel, 6)) < 10_000)
        finally:
            panel.sleep()

    # Built by hand onto a controller left asleep: unless its first refresh resets the controller,
    # BUSY, high in deep sleep, times the refresh out.
    def test_first_refresh_initialises(self):
        try:
            reterminal_sticky.panel().sleep()
        except NotImplementedError as e:
            self.skipTest(str(e))
        b = Pin.board
        bus = reterminal_sticky.spi()
        pins = (b.EPD_CS, b.EPD_DC, b.EPD_RST, b.EPD_BUSY)
        panel = ssd1677.SSD1677(bus, *pins, **reterminal_sticky._GLASS)
        try:
            self.assertTrue(self.refresh(panel, card(panel, 2)) < 10_000)
        finally:
            panel.sleep()

    # Into grey straight after a partial, twice, then back: each grey refresh resets the
    # controller, which a second one needed on a unit, and leaves the supply off.
    def test_grey(self):
        try:
            panel = reterminal_sticky.panel()
        except NotImplementedError as e:
            self.skipTest(str(e))
        grey = grey_card(panel)
        for n in (5, 7):
            self.refresh(panel, card(panel, n))
            panel.show(card(panel, n + 1), card(panel, n))
            start = time.ticks_ms()
            panel.show_grey(grey)
            self.assertTrue(panel.busy(), "BUSY didn't rise")
            panel.wait()
            print("grey refresh: %d ms" % time.ticks_diff(time.ticks_ms(), start))
            # A power-off with the supply already off would leave BUSY high.
            panel.power_off()
            self.assertFalse(panel.busy())
        # Full, as the planes don't hold the greys, then a partial.
        self.assertTrue(self.refresh(panel, card(panel, 1), card(panel, 9)) < 10_000)
        self.assertTrue(self.refresh(panel, card(panel, 2), card(panel, 1)) < 10_000)
        panel.sleep()

    # The controller's own full waveform, to black then white: it turns the supply off itself,
    # and black and white refreshes carry on after it.
    def test_clean(self):
        try:
            panel = reterminal_sticky.panel()
        except NotImplementedError as e:
            self.skipTest(str(e))
        self.refresh(panel, card(panel, 3))
        for white in (False, True):
            start = time.ticks_ms()
            panel.clean(white)
            self.assertTrue(panel.busy(), "BUSY didn't rise")
            panel.wait()
            print(
                "clean to %s: %d ms"
                % ("white" if white else "black", time.ticks_diff(time.ticks_ms(), start))
            )
            panel.power_off()
            self.assertFalse(panel.busy())
        self.assertTrue(self.refresh(panel, card(panel, 1), card(panel, 9)) < 10_000)
        self.assertTrue(self.refresh(panel, card(panel, 2), card(panel, 1)) < 10_000)
        panel.sleep()
