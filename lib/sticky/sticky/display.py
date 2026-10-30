# The frame buffer scenes draw into, and when to clear ghosting: a partial refresh drives only the
# pixels that differ from the glass, and after `burst` partials in a row the next one is full.

import asyncio

import framebuf
from micropython import const

WIDTH = const(800)
HEIGHT = const(480)


class Display(framebuf.FrameBuffer):
    """Draw with FrameBuffer's methods, 1 for white, then await show(). panel is initialised."""

    def __init__(self, panel, burst=10):
        self.panel = panel
        self.burst = burst
        self.partials = 0
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
        await self.wait()
        # Until the panel has the frame: Ctrl-C mid-transfer leaves the glass uncertain.
        self._known = False
        self.panel.show(self.buffer, None if full else self._glass)
        self._glass[:] = self.buffer
        self._known = True
        self.partials = 0 if full else self.partials + 1

    async def wait(self):
        """Wait for the refresh to end. A timeout leaves the glass uncertain: the next is full."""
        try:
            await self.panel.wait_async()
        except OSError:
            self._known = False
            raise

    async def sleep(self):
        """Power the panel down after the refresh; the image stays. The next show() is full."""
        # Powered down even if the wait fails: 0x22 FC leaves the analog supply on.
        try:
            await self.wait()
        finally:
            self._known = False
            self.panel.sleep()
