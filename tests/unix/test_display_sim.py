# What only SimPanel's glass shows of Display: the pictures it ends up holding, and other glasses'
# sizes. The rest of Display's tests run on the unit too, in tests/common/test_display.py.
import asyncio
import time
import unittest

from sticky.display import BLACK, Display
from sticky_sim import SimPanel

run = asyncio.run
GREY = b"\xaa" * 96000  # every pixel level 2


class TestGlass(unittest.TestCase):
    def setUp(self):
        self.panel = SimPanel()
        self.display = Display(self.panel, burst=3)

    def tearDown(self):
        asyncio.new_event_loop()

    def draw(self, n):
        self.display.fill_rect(10 * n, 0, 10, 10, BLACK)

    def test_other_size(self):
        display = Display(SimPanel(width=400, height=300))
        self.assertEqual((display.width, display.height), (400, 300))
        self.assertEqual(len(display.buffer), 15000)
        display.fill_rect(392, 296, 8, 4, 0)
        run(display.show_async())
        self.assertEqual(display.panel.glass[-1], 0)
        with self.assertRaises(ValueError):
            run(display.show_grey_async(bytes(96000)))

    # The sim drives only pixels that differ from old, so a wrong old would show on its glass.
    def test_glass_follows_frames(self):
        d = self.display
        for n in range(12):
            d.fill(n % 3 != 0)
            d.text("frame %d" % n, 8 * n, 4 * n, n & 1)
            d.rect(n, n, 200, 100, 0)
            run(d.show_async())
            self.assertEqual(self.panel.glass, d.buffer)

    def test_draws_while_busy(self):
        self.panel.refresh_ms = 50
        d = self.display
        d.fill(0)
        run(d.show_async())
        self.assertTrue(self.panel.busy())
        first = bytes(d.buffer)
        d.fill(1)
        self.assertEqual(self.panel.glass, first)
        start = time.ticks_ms()
        run(d.show_async())
        self.assertTrue(time.ticks_diff(time.ticks_ms(), start) >= 40)
        self.assertEqual(self.panel.glass, d.buffer)

    def test_plain_show(self):
        self.draw(0)
        self.display.show()
        self.assertEqual(self.panel.glass, self.display.buffer)

    # What the glass showed is what's redrawn, not what was drawn since.
    def test_sleep_after_partial_redraws_what_was_shown(self):
        self.display.show()
        self.draw(1)
        self.display.show()
        shown = bytes(self.display.buffer)
        self.draw(2)
        self.display.sleep()
        self.assertEqual(self.panel.glass, shown)

    def test_greys_held(self):
        self.draw(0)
        run(self.display.show_async())
        run(self.display.show_grey_async(GREY, clean=True))
        self.assertEqual(self.panel.greys, GREY)
        self.draw(1)
        run(self.display.show_async())
        self.assertIsNone(self.panel.greys)


if __name__ == "__main__":
    unittest.main()
