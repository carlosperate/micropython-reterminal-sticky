# Counts 1 to 4 on the glass with a burst of 2 (full, partial, partial, full), sleeps, and wakes
# to add "woke" under the count; then checks the idle power-off turns the high voltage off.
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
        asyncio.run(self.count(display))

    async def count(self, display):
        # 0x22 FC leaves the analog supply on until sleep(), so it runs even on a failure.
        try:
            partials = []
            for n in range(1, 5):
                display.fill(1)
                display.rect(0, 0, 800, 480, 0)
                display.fill_rect(360 + 20 * n, 200, 16, 16 * n, 0)
                display.text("refresh %d" % n, 16, 16, 0)
                start = time.ticks_ms()
                await display.show()
                # It returns once the panel has the frame, not after the refresh.
                self.assertTrue(display.panel.busy())
                print("show %d: %d ms" % (n, time.ticks_diff(time.ticks_ms(), start)))
                partials.append(display.partials)
            self.assertEqual(partials, [0, 1, 2, 0])
            await display.sleep()
            display.text("woke", 16, 32, 0)
            start = time.ticks_ms()
            await display.show()
            print("show after sleep: %d ms" % time.ticks_diff(time.ticks_ms(), start))
            self.assertEqual(display.partials, 0)
        finally:
            await display.sleep()

    def test_idle_power_off(self):
        try:
            panel = reterminal_sticky.panel()
        except NotImplementedError as e:
            self.skipTest(str(e))
        display = Display(panel, idle_ms=300)

        async def main():
            display.text("idle power-off", 16, 16, 0)
            await display.show()
            self.assertTrue(panel._powered)
            # The refresh (about 0.56 s) plus idle_ms plus the power-down.
            await asyncio.sleep_ms(1500)
            self.assertFalse(panel._powered)
            self.assertFalse(panel.busy())
            await display.sleep()

        asyncio.run(main())
