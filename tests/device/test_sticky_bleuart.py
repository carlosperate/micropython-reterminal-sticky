# The BLE UART on the board's radio. Connecting needs a central: the Chrome checks in
# docs/bleuart.md cover echo, long writes, the REPL over BLE and reconnects.
import os
import unittest

import bluetooth
from sticky.bleuart import BLEUART, repl


class TestBLEUART(unittest.TestCase):
    def test_uart(self):
        uart = BLEUART()
        self.assertTrue(uart.name.startswith("sticky-") and len(uart.name) == 11, uart.name)
        self.assertFalse(uart.connected)
        self.assertEqual(uart.write(b"nobody listening\n"), 0)
        self.assertIsNone(uart.read())
        uart.close()
        # close() leaves the radio to the programme.
        self.assertTrue(bluetooth.BLE().active())

    def test_repl_attaches(self):
        uart = repl()
        try:
            self.assertFalse(uart.connected)
            print("printed with the BLE UART attached")
        finally:
            os.dupterm(None)
            uart.close()
            bluetooth.BLE().active(False)
