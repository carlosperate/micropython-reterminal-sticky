import gc
import sys
import unittest

import machine
import network


class TestFirmware(unittest.TestCase):
    # On another image every device test fails, and this one says why.
    def test_board(self):
        self.assertEqual(sys.implementation._machine, "Seeed reTerminal Sticky with ESP32-S3")
        self.assertEqual(sys.implementation.version[:3], (1, 29, 0))

    def test_cpu_frequency(self):
        self.assertEqual(machine.freq(), 240_000_000)

    # The heap lives in the 8 MiB of octal PSRAM; the chip's own RAM is 512 KiB in all.
    def test_heap_in_psram(self):
        gc.collect()
        self.assertGreaterEqual(gc.mem_free() + gc.mem_alloc(), 7 * 1024 * 1024)

    def test_hostname(self):
        self.assertEqual(network.hostname(), "mpy-sticky")

    # Its default pins would claim the panel's bus; the card goes through a driver on SPI(1).
    def test_no_machine_sdcard(self):
        self.assertFalse(hasattr(machine, "SDCard"))
