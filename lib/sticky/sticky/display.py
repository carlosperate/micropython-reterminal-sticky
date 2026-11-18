# The frame buffer programmes draw into, when to clear ghosting (after `burst` partials in a row
# the next refresh is full), and when to turn off the high voltage a refresh leaves on.
# asyncio is imported by the _async calls only, so the plain ones never load it.

import framebuf
from micropython import const

# The Sticky's, for buffers sized before a display exists; a Display takes its panel's.
WIDTH = const(800)
HEIGHT = const(480)
# The panel's own: 1 is white.
BLACK = const(0)
WHITE = const(1)


class Display(framebuf.FrameBuffer):
    """Draw with FrameBuffer's methods, then show(). text() draws in BLACK unless told otherwise.

    show(), show_grey() and sleep() wait for the panel and leave its high voltage off. Under
    asyncio, show_async() and show_grey_async() return while the refresh runs instead, and
    wait_async() and sleep_async() wait without blocking other tasks.
    """

    def __init__(self, panel, burst=10, idle_ms=1000):
        self.panel = panel
        self.width = panel.width
        self.height = panel.height
        self.burst = burst
        self.idle_ms = idle_ms
        self.partials = 0
        self._idle = None
        self.buffer = bytearray(self.width * self.height // 8)
        self._glass = bytearray(len(self.buffer))
        self._known = False  # whether _glass is what the glass shows
        super().__init__(self.buffer, self.width, self.height, framebuf.MONO_HLSB)
        self.fill(WHITE)

    def text(self, s, x, y, c=BLACK):
        super().text(s, x, y, c)

    def show(self, full=False):
        """Refresh to the frame, wait for it, and turn the high voltage off.

        Partial unless full is set, nothing is known of the glass, or `burst` partials came
        before. An unchanged frame isn't sent. It returns as the power-down starts (about
        140 ms); the next call waits that out.
        """
        self._stop_idle()
        try:
            self._wait()
            if self._changed(full):
                self._send(full)
                self._wait()
        finally:
            # Also after an _async refresh, which leaves it on for the idle task.
            self.panel.power_off()

    def show_grey(self, frame, clean=False):
        """As show_grey_async(), but waits for each refresh, then turns the high voltage off."""
        self._stop_idle()
        try:
            self._check_grey(frame)
            # The driver waits out a running refresh before each of these.
            self._known = False
            if clean:
                for white in (False, True):
                    self.panel.clean(white)
            self.panel.show_grey(frame)
            self._wait()
        finally:
            self.panel.power_off()

    def sleep(self):
        """Power the panel down once the refresh ends; the image stays. The next show() is full.

        After a partial, it first redraws the glass with a full refresh.
        """
        self._stop_idle()
        # Powered down even if the wait fails: 0x22 FC leaves the analog supply on.
        try:
            self._wait()
            if self._redraw_full():
                self._wait()
        finally:
            self._known = False
            self.panel.sleep()

    async def show_async(self, full=False):
        """Start a refresh once the last one ends, and return without waiting for it.

        The panel has the frame by then, so drawing the next one can start at once. The idle
        power-off needs the event loop to keep running: once asyncio.run() returns, close().
        """
        import asyncio

        if not self._changed(full):
            # Still a yield, so a scene looping on a still frame lets the link run.
            await asyncio.sleep_ms(0)
            return
        self._stop_idle()
        try:
            await self.wait_async()
            self._send(full)
        finally:
            # Even cut short or timed out: the last refresh may have left the supply on.
            self._idle = asyncio.create_task(self._power_off_when_idle())

    async def show_grey_async(self, frame, clean=False):
        """Refresh to a four-grey frame once the last refresh ends, and return without waiting.

        frame is the caller's GS2_HMSB buffer at the display's size (width * height // 4 bytes,
        0 black to 3 white), read only until this returns. Drawing on the display itself stays
        black and white. The glass then holds greys, so the next show() is full.

        clean first flashes the glass black, then white, with the controller's own waveform
        (about 3.6 s): a picture held for long otherwise shows through the greys more.
        """
        import asyncio

        self._check_grey(frame)
        self._stop_idle()
        try:
            await self.wait_async()
            # Before the panel's RAM changes, and left so: no partial may follow the greys.
            self._known = False
            if clean:
                for white in (False, True):
                    self.panel.clean(white)
                    await self.wait_async()
            self.panel.show_grey(frame)
        finally:
            # The grey waveform turns the supply off itself, but one cut short before it may
            # leave the last refresh's on. Turning off a supply that's off does nothing.
            self._idle = asyncio.create_task(self._power_off_when_idle())

    async def sleep_async(self):
        """As sleep(), letting other tasks run while the refreshes end."""
        self._stop_idle()
        try:
            await self.wait_async()
            if self._redraw_full():
                await self.wait_async()
        finally:
            self._known = False
            self.panel.sleep()

    async def wait_async(self):
        """Wait for the refresh to end. A timeout leaves the glass uncertain: the next is full."""
        try:
            await self.panel.wait_async()
        except OSError:
            self._known = False
            raise

    def close(self):
        """Turn the high voltage off without the event loop: for `with` and clean-up.

        After a partial, it first redraws the glass with a full refresh, waiting for both. Draw
        and show again afterwards as usual; the next refresh turns it back on.
        """
        try:
            if self._redraw_full():
                self._wait()
        except OSError:
            pass  # a hung panel still gets its power-off
        finally:
            self.panel.power_off()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _changed(self, full):
        return full or not self._known or self.buffer != self._glass

    # Until the panel has the frame: Ctrl-C mid-transfer leaves the glass uncertain.
    def _send(self, full, frame=None):
        frame = self.buffer if frame is None else frame
        full = full or not self._known or self.partials >= self.burst
        self._known = False
        self.panel.show(frame, None if full else self._glass)
        self._glass[:] = frame
        self._known = True
        self.partials = 0 if full else self.partials + 1

    # A picture left after partials shows grain and older pictures through it, which a full
    # refresh clears, so one put away is redrawn with one. Starts it, or returns False.
    def _redraw_full(self):
        if not (self._known and self.partials):
            return False
        self._send(True, self._glass)
        return True

    def _check_grey(self, frame):
        if len(frame) != self.width * self.height // 4:
            raise ValueError("frame size")

    def _wait(self):
        try:
            self.panel.wait()
        except OSError:
            self._known = False
            raise

    def _stop_idle(self):
        if self._idle:
            self._idle.cancel()

    # A panel left at high voltage for long is damaged; a burst keeps it on between frames.
    async def _power_off_when_idle(self):
        import asyncio

        await asyncio.sleep_ms(self.idle_ms)
        try:
            await self.wait_async()
        except OSError:
            pass  # the driver's own waits are capped, so it still turns the high voltage off
        self.panel.power_off()
