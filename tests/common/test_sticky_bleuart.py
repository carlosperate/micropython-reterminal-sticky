# The BLE UART with no central: on the unit's radio, and on the unix port's fake bluetooth.
# Connecting needs a central: the unix tests play one, and on the unit the Chrome checks in
# docs/bleuart.md cover echo, long writes, the REPL over BLE and reconnects.
import os
import select
import sys
import unittest

BOARD = sys.platform == "esp32"
if not BOARD:
    sys.path.append("tests/unix")
    import fakes

    # test_bleuart.py may have put one in first, which sticky.bleuart then holds.
    if "bluetooth" not in sys.modules:
        sys.modules["bluetooth"] = fakes.bluetooth_module(fakes.BLE())

import bluetooth  # noqa: E402
from sticky.bleuart import BLEUART, repl  # noqa: E402


class TestBLEUART(unittest.TestCase):
    def setUp(self):
        if not BOARD:
            bluetooth.BLE().__init__()

    # Nothing to read, and with no central nothing can be written either.
    def assert_empty(self, uart):
        self.assertEqual(uart.any(), 0)
        self.assertIsNone(uart.read())
        self.assertIsNone(uart.readline())
        self.assertIsNone(uart.readinto(bytearray(8)))
        poll = select.poll()
        poll.register(uart, select.POLLIN | select.POLLOUT)
        self.assertEqual(poll.poll(0), [])

    def test_nothing_received(self):
        with BLEUART() as uart:
            self.assert_empty(uart)
        self.assert_empty(uart)
        with BLEUART() as uart:
            self.assert_empty(uart)

    def test_uart(self):
        uart = BLEUART()
        self.assertTrue(uart.name.startswith("sticky-") and len(uart.name) == 11, uart.name)
        self.assertFalse(uart.is_connected())
        self.assertEqual(uart.write(b"nobody listening\n"), 0)
        self.assert_empty(uart)
        uart.close()
        # close() leaves the radio to the programme.
        self.assertTrue(bluetooth.BLE().active())

    # NimBLE refuses advertising data over 31 bytes, which a 27-byte name makes. In bytes: "é"
    # takes two.
    def test_name_limit(self):
        for name in ("x" * 27, "é" * 14):
            with self.assertRaises(ValueError):
                BLEUART(name)
        for name in ("x" * 26, "é" * 13):
            with BLEUART(name) as uart:
                self.assertEqual(uart.name, name)
        with BLEUART() as uart:
            self.assertTrue(uart.name.startswith("sticky-"))

    def test_repl_attaches(self):
        if not hasattr(os, "dupterm"):
            self.skipTest("no os.dupterm on this port")
        uart = repl()
        try:
            self.assertFalse(uart.is_connected())
            print("printed with the BLE UART attached")
        finally:
            os.dupterm(None)
            uart.close()
            bluetooth.BLE().active(False)


if __name__ == "__main__":
    unittest.main()
