# The BLE UART on the board's radio. Connecting needs a central: the Chrome checks in
# docs/bleuart.md cover echo, long writes, the REPL over BLE and reconnects.
import os
import select
import unittest

import bluetooth
from sticky.bleuart import BLEUART, repl


class TestBLEUART(unittest.TestCase):
    def assert_empty(self, uart):
        self.assertEqual(uart.any(), 0)
        self.assertIsNone(uart.read())
        self.assertIsNone(uart.readline())
        self.assertIsNone(uart.readinto(bytearray(8)))
        poll = select.poll()
        poll.register(uart, select.POLLIN)
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
        self.assertFalse(uart.connected)
        self.assertEqual(uart.write(b"nobody listening\n"), 0)
        self.assertIsNone(uart.read())
        uart.close()
        # close() leaves the radio to the programme.
        self.assertTrue(bluetooth.BLE().active())

    # NimBLE refuses advertising data over 31 bytes, which a 27-byte name makes.
    def test_name_limit(self):
        with self.assertRaises(ValueError):
            BLEUART("x" * 27)
        with BLEUART("x" * 26) as uart:
            self.assertEqual(uart.name, "x" * 26)
        with BLEUART() as uart:
            self.assertTrue(uart.name.startswith("sticky-"))

    def test_repl_attaches(self):
        uart = repl()
        try:
            self.assertFalse(uart.connected)
            print("printed with the BLE UART attached")
        finally:
            os.dupterm(None)
            uart.close()
            bluetooth.BLE().active(False)
