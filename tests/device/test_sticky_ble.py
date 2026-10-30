# Link on the board's own radio. Connecting needs a central: the deck's Chrome checks
# (deck-app/chrome/) cover writes, notifications and reconnects.
import asyncio
import unittest

import bluetooth
from sticky.ble import MAX_LEN, Link


class TestLink(unittest.TestCase):
    def test_link(self):
        link = Link()
        self.assertTrue(link.name.startswith("sticky-") and len(link.name) == 11, link.name)
        # notify() stores the value even with no deck connected, for a read after a reconnect.
        link.notify(b"hello")
        self.assertEqual(link._events.read(), b"hello")
        with self.assertRaises(ValueError):
            link.notify(b"x" * (MAX_LEN + 1))

        async def advertise_then_cancel():
            task = asyncio.create_task(link.run())
            await asyncio.sleep_ms(1000)
            self.assertFalse(link.connected)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                return True

        # aioble swallows a cancelled advertise; run() must still end on cancel.
        self.assertTrue(asyncio.run(advertise_then_cancel()))
        link.close()
        self.assertFalse(bluetooth.BLE().active())
