# Leaves a test card on the glass: "TOP LEFT" reads normally in the corner it names, and the
# counter reads 2 with no trace of the 1 under it.
import time
import unittest

import framebuf
import reterminal_sticky
import ssd1677


def big_text(fb, text, x, y, scale):
    small = framebuf.FrameBuffer(bytearray(8 * len(text)), 8 * len(text), 8, framebuf.MONO_HLSB)
    small.fill(1)
    small.text(text, 0, 0, 0)
    for gy in range(8):
        for gx in range(8 * len(text)):
            if not small.pixel(gx, gy):
                fb.fill_rect(x + gx * scale, y + gy * scale, scale, scale, 0)


def card(count):
    buf = bytearray(ssd1677.WIDTH * ssd1677.HEIGHT // 8)
    fb = framebuf.FrameBuffer(buf, ssd1677.WIDTH, ssd1677.HEIGHT, framebuf.MONO_HLSB)
    fb.fill(1)
    fb.rect(0, 0, ssd1677.WIDTH, ssd1677.HEIGHT, 0)
    fb.fill_rect(0, 0, 40, 40, 0)
    big_text(fb, "TOP LEFT", 56, 8, 4)
    big_text(fb, str(count), 336, 176, 16)
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
        first, second = card(1), card(2)
        self.assertTrue(self.refresh(panel, first) < 10_000)
        self.assertTrue(self.refresh(panel, second, first) < 10_000)
        # 0x22 FC leaves the analog supply on; the card stays on the glass.
        panel.sleep()
