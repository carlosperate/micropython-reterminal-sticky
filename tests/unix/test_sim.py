import os
import unittest

from sticky_sim import SimPanel

WHITE = b"\xff" * 48000
BLACK = bytes(48000)


class TestSimPanel(unittest.TestCase):
    def test_size(self):
        panel = SimPanel()
        self.assertEqual((panel.width, panel.height), (800, 480))
        panel = SimPanel(width=400, height=300)
        self.assertEqual((panel.width, panel.height), (400, 300))
        panel.show(bytes(15000))
        self.assertEqual(panel.glass, bytes(15000))
        for call in (lambda: panel.show(BLACK), lambda: panel.show_grey(bytes(96000))):
            with self.assertRaises(ValueError):
                call()
        # As the driver: rows are whole bytes, and neither side is empty.
        for width, height in ((404, 480), (0, 480), (800, 0)):
            with self.assertRaises(ValueError):
                SimPanel(width=width, height=height)

    def test_full(self):
        panel = SimPanel()
        panel.show(BLACK)
        self.assertEqual(panel.glass, BLACK)
        self.assertEqual((panel.full, panel.partial), (1, 0))

    # Pixels where old matches new aren't driven, even if the glass differs.
    def test_partial_trusts_old(self):
        panel = SimPanel()
        panel.show(BLACK)
        panel.show(WHITE, WHITE)
        self.assertEqual(panel.glass, BLACK)
        panel.show(WHITE, BLACK)
        self.assertEqual(panel.glass, WHITE)
        self.assertEqual((panel.full, panel.partial), (1, 2))

    def test_pbm(self):
        path = "/tmp/sticky-test-sim"
        try:
            os.mkdir(path)
        except OSError:
            pass
        frame = bytearray(WHITE)
        frame[0] = 0x7F  # the top-left pixel black
        panel = SimPanel(path)
        panel.show(frame)
        panel.show(WHITE, frame)
        names = sorted(n for n in os.listdir(path) if n.endswith(".pbm"))
        self.assertEqual(names, ["00001.pbm", "00002.pbm"])
        with open(path + "/00001.pbm", "rb") as f:
            data = f.read()
        self.assertEqual(data[:11], b"P4\n800 480\n")
        self.assertEqual(data[11:], b"\x80" + bytes(47999))
        for name in names:
            os.remove(path + "/" + name)
        os.rmdir(path)


def grey(levels):
    """A GS2_HMSB frame from levels(x, y), through framebuf."""
    import framebuf

    buf = bytearray(96000)
    fb = framebuf.FrameBuffer(buf, 800, 480, framebuf.GS2_HMSB)
    for y in range(480):
        for x in range(800):
            fb.pixel(x, y, levels(x, y))
    return buf


class TestSimGrey(unittest.TestCase):
    # Levels 0 and 1 are dark on the black-and-white glass, 2 and 3 light.
    def test_grey(self):
        frame = grey(lambda x, y: x & 3)
        panel = SimPanel()
        panel.show(WHITE)
        panel.show_grey(frame)
        self.assertEqual(panel.glass, b"\x33" * 48000)
        self.assertEqual(panel.greys, frame)
        # The full refresh after it drives every pixel, whatever old says.
        panel.show(WHITE, WHITE)
        self.assertEqual(panel.glass, WHITE)
        self.assertIsNone(panel.greys)

    def test_clean(self):
        panel = SimPanel()
        panel.show(BLACK)
        panel.clean()
        self.assertEqual(panel.glass, WHITE)
        panel.clean(False)
        self.assertEqual(panel.glass, BLACK)

    def test_pgm(self):
        path = "/tmp/sticky-test-sim-grey"
        try:
            os.mkdir(path)
        except OSError:
            pass
        panel = SimPanel(path)
        panel.show_grey(grey(lambda x, y: x & 3))
        with open(path + "/00001.pgm", "rb") as f:
            data = f.read()
        os.remove(path + "/00001.pgm")
        os.rmdir(path)
        self.assertEqual(data[:15], b"P5\n800 480\n255\n")
        self.assertEqual(data[15:23], b"\x00\x55\xaa\xff\x00\x55\xaa\xff")
        self.assertEqual(len(data), 15 + 800 * 480)
