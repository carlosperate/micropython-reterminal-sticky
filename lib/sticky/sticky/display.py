# The frame buffer scenes draw into, when to clear ghosting (after `burst` partials in a row the
# next refresh is full), and when to turn off the high voltage a refresh leaves on.

import asyncio

import framebuf
from micropython import const

WIDTH = const(800)
HEIGHT = const(480)


class Display(framebuf.FrameBuffer):
    """Draw with FrameBuffer's methods, 1 for white, then await show(). panel is initialised."""

    def __init__(self, panel, burst=10, idle_ms=1000):
        self.panel = panel
        self.burst = burst
        self.idle_ms = idle_ms
        self.partials = 0
        self._idle = None
        self.buffer = bytearray(WIDTH * HEIGHT // 8)
        self._glass = bytearray(len(self.buffer))
        self._known = False  # whether _glass is what the glass shows
        super().__init__(self.buffer, WIDTH, HEIGHT, framebuf.MONO_HLSB)
        self.fill(1)

    async def show(self, full=False):
        """Start a refresh once the last one ends, and return without waiting for it.

        The panel has the frame by then, so drawing the next one can start at once.
        """
        if not full and self._known and self.buffer == self._glass:
            # Still a yield, so a scene looping on a still frame lets the link run.
            await asyncio.sleep_ms(0)
            return
        full = full or not self._known or self.partials >= self.burst
        if self._idle:
            self._idle.cancel()
        await self.wait()
        # Until the panel has the frame: Ctrl-C mid-transfer leaves the glass uncertain.
        self._known = False
        self.panel.show(self.buffer, None if full else self._glass)
        self._glass[:] = self.buffer
        self._known = True
        self.partials = 0 if full else self.partials + 1
        self._idle = asyncio.create_task(self._power_off_when_idle())

    # A panel left at high voltage for long is damaged; a burst keeps it on between frames.
    async def _power_off_when_idle(self):
        await asyncio.sleep_ms(self.idle_ms)
        try:
            await self.power_off()
        except OSError:
            pass

    async def wait(self):
        """Wait for the refresh to end. A timeout leaves the glass uncertain: the next is full."""
        try:
            await self.panel.wait_async()
        except OSError:
            self._known = False
            raise

    async def power_off(self):
        """Turn the panel's analog supply off once the refresh ends. The glass stays known."""
        try:
            await self.wait()
        except OSError:
            # The driver's own waits are capped, so it still turns the high voltage off.
            self.panel.power_off()
            raise
        self.panel.power_off()

    def close(self):
        """Turn the high voltage off now, without the event loop: for `with` and clean-up.

        Draw and show again afterwards as usual; the next refresh turns it back on.
        """
        self.panel.power_off()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    async def sleep(self):
        """Power the panel down after the refresh; the image stays. The next show() is full."""
        if self._idle:
            self._idle.cancel()
        # Powered down even if the wait fails: 0x22 FC leaves the analog supply on.
        try:
            await self.wait()
        finally:
            self._known = False
            self.panel.sleep()
