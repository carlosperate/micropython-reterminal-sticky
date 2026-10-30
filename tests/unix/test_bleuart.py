import asyncio
import sys
import unittest

import fakes

ble = fakes.BLE()
sys.modules["bluetooth"] = fakes.bluetooth_module(ble)
from sticky import bleuart  # noqa: E402


class TestBLEUART(unittest.TestCase):
    def setUp(self):
        ble.__init__()
        self.uart = bleuart.BLEUART(rxbuf=32)

    def test_advertises_with_name_from_mac(self):
        self.assertEqual(self.uart.name, "sticky-69f2")
        self.assertEqual(ble.config_set["gap_name"], "sticky-69f2")
        self.assertTrue(ble.advertising)

    def test_write_without_central(self):
        self.assertEqual(self.uart.write(b"hello"), 0)
        self.assertEqual(ble.notified, [])

    def test_write_chunks_to_mtu(self):
        ble.connect()
        self.assertEqual(self.uart.write(b"x" * 50), 50)
        self.assertEqual([len(c) for c in ble.notified], [20, 20, 10])
        ble.notified.clear()
        ble.exchange_mtu(103)
        self.uart.write("y" * 150)
        self.assertEqual([len(c) for c in ble.notified], [100, 50])

    def test_full_stack_retried_then_dropped(self):
        ble.connect()
        ble.fail_notify = 2
        self.assertEqual(self.uart.write(b"abc"), 3)
        ble.fail_notify = 100
        self.assertEqual(self.uart.write(b"x" * 30), 0)
        self.assertEqual(self.uart.dropped, 30)

    # A stale handle fails as an OSError, caught; a disconnect also ends the retries.
    def test_disconnect_during_retries(self):
        ble.connect()
        notify = ble.gatts_notify

        def full_then_gone(conn, handle, data):
            ble.disconnect()
            raise OSError(12)

        ble.gatts_notify = full_then_gone
        try:
            self.assertEqual(self.uart.write(b"x" * 30), 0)
        finally:
            ble.gatts_notify = notify
        self.assertEqual(self.uart.dropped, 30)

    def test_receive(self):
        ble.connect()
        ble.write(b"hel")
        ble.write(b"lo\nwo")
        self.assertEqual(self.uart.any(), 8)
        self.assertEqual(self.uart.read(3), b"hel")
        buf = bytearray(10)
        self.assertEqual(self.uart.readinto(buf), 5)
        self.assertEqual(bytes(buf[:5]), b"lo\nwo")
        self.assertIsNone(self.uart.read())

    # A poll that says readable when nothing is spins an asyncio reader until the next write.
    def test_poll_after_reading_everything(self):
        poll, rd = 3, 1  # MP_STREAM_POLL, MP_STREAM_POLL_RD
        self.assertEqual(self.uart.ioctl(poll, rd), 0)
        ble.connect()
        ble.write(b"hi")
        self.assertEqual(self.uart.ioctl(poll, rd), rd)
        self.uart.read()
        self.assertEqual(self.uart.ioctl(poll, rd), 0)

    # A loss is a gap: what was waiting goes, and readers can tell from gaps. No framing here.
    def test_overflow_is_a_gap(self):
        ble.connect()
        gaps = self.uart.gaps
        ble.write(b"one\ntw")
        ble.write(b"o" * 40)
        self.assertEqual((self.uart.overflows, self.uart.gaps), (1, gaps + 1))
        self.assertIsNone(self.uart.read())
        ble.write(b"three\n")
        self.assertEqual(self.uart.read(), b"three\n")

    def test_largest_valid_write_kept(self):
        uart = bleuart.BLEUART(rxbuf=1024)
        ble.connect()
        ble.write(b"x" * 512)
        self.assertEqual((uart.overflows, uart.any()), (0, 512))

    def test_cut_write_is_a_gap(self):
        uart = bleuart.BLEUART(rxbuf=2048)
        ble.connect()
        ble.write(b"x" * 1024)
        self.assertEqual(uart.overflows, 1)
        self.assertIsNone(uart.read())

    def test_connect_resets(self):
        ble.connect()
        gaps = self.uart.gaps
        ble.write(b"stale")
        ble.exchange_mtu(103)
        ble.disconnect()
        self.assertTrue(ble.advertising)
        ble.connect()
        self.assertEqual(self.uart.gaps, gaps + 1)
        self.assertIsNone(self.uart.read())
        ble.notified.clear()
        self.uart.write(b"x" * 30)
        self.assertEqual(len(ble.notified), 2)

    # os.dupterm() reads a byte at a time.
    def test_byte_at_a_time(self):
        ble.connect()
        ble.write(b"abc")
        buf = bytearray(1)
        got = b""
        while self.uart.readinto(buf):
            got += buf
        self.assertEqual(got, b"abc")
        ble.write(b"de\nf")
        self.assertEqual(self.uart.readline(), b"de\n")
        self.assertEqual(self.uart.read(), b"f")

    def test_with_closes(self):
        with bleuart.BLEUART() as uart:
            ble.connect(conn=5)
        self.assertEqual(ble.disconnected, [5])
        self.assertFalse(uart.connected)

    def test_close(self):
        ble.connect(conn=9)
        self.uart.close()
        self.assertEqual(ble.disconnected, [9])
        self.assertFalse(self.uart.connected)
        ble.disconnect(conn=9)
        self.assertFalse(ble.advertising)

    def test_stream_reader_lines(self):
        ble.connect()

        async def main():
            reader = asyncio.StreamReader(self.uart)
            ble.write(b"a 1\nb ")
            first = await reader.readline()
            ble.write(b"2\n")
            return first, await reader.readline()

        self.assertEqual(asyncio.run(main()), (b"a 1\n", b"b 2\n"))


class TestREPL(unittest.TestCase):
    def test_repl_mirrors_output(self):
        import os

        if not hasattr(os, "dupterm"):
            self.skipTest("no os.dupterm on this port")
        ble.__init__()
        bleuart.repl()
        try:
            ble.connect()
            print("over ble")
        finally:
            os.dupterm(None)
        self.assertIn(b"over ble", b"".join(ble.notified))
