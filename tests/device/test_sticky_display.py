# What only the real panel shows of Display: close() during a grey refresh, the plain call's
# timings and power-down, and a hand-built driver. The policy's tests run on both, in
# tests/common/test_display.py. The plain test leaves "plain show()", "full" and "partial" in
# black, drawn with no colour given, and the hand-built one "hand-built driver".
import asyncio
import time
import unittest

import reterminal_sticky
import ssd1677
from machine import Pin
from sticky.display import Display


class TestDisplay(unittest.TestCase):
    # A grey frame between two black-and-white ones: the one after it is full.
    def test_grey(self):
        try:
            panel = reterminal_sticky.panel()
        except NotImplementedError as e:
            self.skipTest(str(e))
        display = Display(panel)

        async def main():
            try:
                display.text("before grey", 16, 16, 0)
                await display.show_async()
                grey = bytearray(display.width * display.height // 4)
                grey[: len(grey) // 2] = b"\x55" * (len(grey) // 2)  # top half level 1
                grey[len(grey) // 2 :] = b"\xaa" * (len(grey) // 2)  # bottom half level 2
                await display.show_grey_async(grey)
                # The grey waveform turns the supply off itself: close() neither waits nor cuts it.
                start = time.ticks_ms()
                display.close()
                self.assertTrue(time.ticks_diff(time.ticks_ms(), start) < 50)
                self.assertTrue(panel.busy())
                await display.wait_async()
                display.text("after grey", 16, 32, 0)
                await display.show_async()
                self.assertEqual(display.partials, 0)
                display.text("partial", 16, 48, 0)
                await display.show_async()
                self.assertEqual(display.partials, 1)
            finally:
                await display.sleep_async()

        asyncio.run(main())

    # Each plain call waits for its refresh and turns the high voltage off before it returns.
    def test_plain(self):
        try:
            display = reterminal_sticky.display()
        except NotImplementedError as e:
            self.skipTest(str(e))
        try:
            display.text("plain show()", 16, 16)
            for y, kind in ((32, "full"), (48, "partial")):
                display.text(kind, 16, y)
                start = time.ticks_ms()
                display.show()
                took = time.ticks_diff(time.ticks_ms(), start)
                self.assertFalse(display.panel._powered)
                # The power-down runs on after it returns.
                start = time.ticks_ms()
                display.panel.wait(1000)
                down = time.ticks_diff(time.ticks_ms(), start)
                print("plain show, %s: %d ms, then %d ms of power-down" % (kind, took, down))
            self.assertEqual(display.partials, 1)
            # Redrawn with a full refresh: grain and older pictures show through a partial.
            start = time.ticks_ms()
            display.sleep()
            print("sleep after a partial: %d ms" % time.ticks_diff(time.ticks_ms(), start))
            self.assertEqual(display.partials, 0)
        finally:
            display.sleep()

    # Onto a controller left asleep, where BUSY stays high: the first wait mustn't time out.
    def test_hand_built(self):
        try:
            reterminal_sticky.panel().sleep()
        except NotImplementedError as e:
            self.skipTest(str(e))
        b = Pin.board
        pins = (b.EPD_CS, b.EPD_DC, b.EPD_RST, b.EPD_BUSY)
        panel = ssd1677.SSD1677(reterminal_sticky.spi(), *pins, **reterminal_sticky._GLASS)
        display = Display(panel)
        try:
            display.text("hand-built driver", 16, 16)
            start = time.ticks_ms()
            display.show()
            print("hand-built show: %d ms" % time.ticks_diff(time.ticks_ms(), start))
            self.assertFalse(panel._powered)
        finally:
            display.sleep()
