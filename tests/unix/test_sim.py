import os
import unittest

from sticky_sim import SimPanel

WHITE = b"\xff" * 48000
BLACK = bytes(48000)


class TestSimPanel(unittest.TestCase):
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

    # As the driver: not busy while asleep, and show() wakes it.
    def test_asleep(self):
        panel = SimPanel()
        panel.sleep()
        self.assertFalse(panel.busy())
        panel.wait(0)
        panel.show(WHITE)
        self.assertFalse(panel.asleep)

    def test_timeout(self):
        panel = SimPanel(refresh_ms=1000, timeout_ms=10)
        panel.show(WHITE)
        with self.assertRaises(OSError):
            panel.wait(0)
        with self.assertRaises(OSError):
            panel.wait()
        # As the driver: sleep goes ahead.
        panel.sleep()
        self.assertTrue(panel.asleep)

    def test_frame_size(self):
        with self.assertRaises(ValueError):
            SimPanel().show(bytes(100))

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
