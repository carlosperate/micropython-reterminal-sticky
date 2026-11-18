# Counts 1 to 4 on the glass with a burst of 2 (full, partial, partial, full), sleeps, and wakes
# to add "woke" under the count; then checks the idle power-off turns the high voltage off. The
# plain test leaves "plain show()", "full" and "partial" in black, drawn with no colour given.
import asyncio
import time
import unittest

import reterminal_sticky
from sticky.display import Display


class TestDisplay(unittest.TestCase):
    def test_burst(self):
        try:
            panel = reterminal_sticky.panel()
        except NotImplementedError as e:
            self.skipTest(str(e))
        display = Display(panel, burst=2)
        self.assertEqual((display.width, display.height), (800, 480))
        asyncio.run(self.count(display))

    async def count(self, display):
        # 0x22 FC leaves the analog supply on until sleep(), so it runs even on a failure.
        try:
            partials = []
            for n in range(1, 5):
                display.fill(1)
                display.rect(0, 0, display.width, display.height, 0)
                display.fill_rect(360 + 20 * n, 200, 16, 16 * n, 0)
                display.text("refresh %d" % n, 16, 16, 0)
                start = time.ticks_ms()
                await display.show_async()
                # It returns once the panel has the frame, not after the refresh.
                self.assertTrue(display.panel.busy())
                print("show %d: %d ms" % (n, time.ticks_diff(time.ticks_ms(), start)))
                partials.append(display.partials)
            self.assertEqual(partials, [0, 1, 2, 0])
            await display.sleep_async()
            display.text("woke", 16, 32, 0)
            start = time.ticks_ms()
            await display.show_async()
            print("show after sleep: %d ms" % time.ticks_diff(time.ticks_ms(), start))
            self.assertEqual(display.partials, 0)
        finally:
            await display.sleep_async()

    def test_idle_power_off(self):
        try:
            panel = reterminal_sticky.panel()
        except NotImplementedError as e:
            self.skipTest(str(e))
        display = Display(panel, idle_ms=300)

        async def main():
            display.text("idle power-off", 16, 16, 0)
            await display.show_async()
            self.assertTrue(panel._powered)
            # The refresh (about 0.56 s) plus idle_ms plus the power-down.
            await asyncio.sleep_ms(1500)
            self.assertFalse(panel._powered)
            self.assertFalse(panel.busy())
            await display.sleep_async()

        asyncio.run(main())

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
