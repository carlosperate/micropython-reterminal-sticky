# The Sticky's side of the deck link in docs/ble.md: a GATT service whose `state` value the deck
# writes and the programme reads, latest wins, and whose `events` value the programme notifies.

import asyncio

import aioble
import bluetooth
from micropython import const

_SERVICE = bluetooth.UUID("f294a174-55e9-45c2-95ea-45d9c602d866")
_STATE = bluetooth.UUID("f294a175-55e9-45c2-95ea-45d9c602d866")
_EVENTS = bluetooth.UUID("f294a176-55e9-45c2-95ea-45d9c602d866")
MAX_LEN = const(20)
# Over MAX_LEN, so the stack can't silently cut an over-long write to a valid length.
_BUFFER = const(64)
_INTERVAL_US = const(100_000)


class Link:
    """Advertise as name (sticky-XXXX from the MAC by default) and take one deck at a time.

    Registering its service replaces the whole GATT table, so a programme has no other services.
    """

    def __init__(self, name=None):
        if name is None:
            mac = aioble.config("mac")[1]
            name = "sticky-%02x%02x" % (mac[-2], mac[-1])
        self.name = name
        aioble.config(gap_name=name)
        service = aioble.Service(_SERVICE)
        self._state = aioble.BufferedCharacteristic(service, _STATE, write=True, max_len=_BUFFER)
        self._events = aioble.Characteristic(service, _EVENTS, read=True, notify=True)
        aioble.register_services(service)
        self.state = b""
        self._connection = None

    @property
    def connected(self):
        return self._connection is not None and self._connection.is_connected()

    async def run(self):
        """Advertise, serve a deck until it drops, and again. Run it as a task; cancel to stop."""
        while True:
            try:
                self._connection = await aioble.advertise(
                    _INTERVAL_US, name=self.name, services=[_SERVICE]
                )
                # aioble swallows a cancellation of its advertising and returns None.
                if self._connection is None:
                    raise asyncio.CancelledError
                # Leaving the block disconnects, so a cancelled link frees the deck.
                async with self._connection:
                    await self._connection.disconnected()
            except Exception as e:
                # Advertise again: a dead link would leave the programme waiting forever.
                aioble.log_error("link", e)
                await asyncio.sleep_ms(1000)
            finally:
                self._connection = None

    async def changed(self):
        """Wait for a new state and return it, also in `state`. Writes while busy coalesce."""
        while True:
            await self._state.written()
            # The newest write: later ones overwrite the value before this reads it.
            value = self._state.read()
            if len(value) <= MAX_LEN:
                self.state = value
                return value

    def notify(self, data):
        """Store data in `events` and notify the deck if one is connected."""
        if len(data) > MAX_LEN:
            raise ValueError("event over %d bytes" % MAX_LEN)
        self._events.write(data, send_update=True)
