import asyncio
import time
import unittest

from sticky.display import Display
from sticky_sim import SimPanel


run = asyncio.run


class TestDisplay(unittest.TestCase):
    def setUp(self):
        self.panel = SimPanel()
        self.display = Display(self.panel, burst=3)

    # Drops the display's idle task, which would otherwise keep this test's buffers alive.
    def tearDown(self):
        asyncio.new_event_loop()

    def step(self, n, full=False):
        self.display.fill_rect(10 * n, 0, 10, 10, 0)
        run(self.display.show(full))

    def counts(self):
        return self.panel.full, self.panel.partial

    def test_starts_white(self):
        self.assertEqual(self.display.buffer, b"\xff" * 48000)

    def test_burst(self):
        seen = []
        for n in range(9):
            self.step(n)
            seen.append(self.counts())
        # The first refresh is full; then three partials, then full again.
        self.assertEqual(
            seen, [(1, 0), (1, 1), (1, 2), (1, 3), (2, 3), (2, 4), (2, 5), (2, 6), (3, 6)]
        )

    def test_full_resets_burst(self):
        self.step(0)
        self.step(1)
        self.step(2, full=True)
        self.assertEqual(self.display.partials, 0)
        for n in range(3, 6):
            self.step(n)
        self.assertEqual(self.counts(), (2, 4))

    def test_unchanged_frame_skipped(self):
        self.step(0)
        run(self.display.show())
        self.assertEqual(self.counts(), (1, 0))
        run(self.display.show(True))
        self.assertEqual(self.counts(), (2, 0))

    def test_unchanged_frame_yields(self):
        self.step(0)
        ran = []

        async def other():
            ran.append(1)

        async def main():
            asyncio.create_task(other())
            await self.display.show()
            self.assertEqual(ran, [1])

        run(main())

    # Reaching the burst limit alone doesn't flash a still frame.
    def test_unchanged_after_burst_skipped(self):
        for n in range(4):
            self.step(n)
        run(self.display.show())
        self.assertEqual(self.counts(), (1, 3))

    # The sim drives only pixels that differ from old, so a wrong old would show on its glass.
    def test_glass_follows_frames(self):
        d = self.display
        for n in range(12):
            d.fill(n % 3 != 0)
            d.text("frame %d" % n, 8 * n, 4 * n, n & 1)
            d.rect(n, n, 200, 100, 0)
            run(d.show())
            self.assertEqual(self.panel.glass, d.buffer)

    def test_draws_while_busy(self):
        self.panel.refresh_ms = 50
        d = self.display
        d.fill(0)
        run(d.show())
        self.assertTrue(self.panel.busy())
        first = bytes(d.buffer)
        d.fill(1)
        self.assertEqual(self.panel.glass, first)
        start = time.ticks_ms()
        run(d.show())
        self.assertTrue(time.ticks_diff(time.ticks_ms(), start) >= 40)
        self.assertEqual(self.panel.glass, d.buffer)

    def test_failed_refresh_makes_next_full(self):
        self.step(0)

        def fail(frame, old=None):
            raise OSError("busy timeout")

        show, self.panel.show = self.panel.show, fail
        with self.assertRaises(OSError):
            self.step(1)
        self.panel.show = show
        self.step(2)
        self.assertEqual(self.counts(), (2, 0))

    # A refresh that times out leaves the panel busy; init() is the reset that recovers it.
    def hang(self):
        self.panel.refresh_ms = 60_000
        self.step(1)
        self.panel.timeout_ms = 10

    def test_wait_timeout_makes_next_full(self):
        self.step(0)
        self.hang()
        with self.assertRaises(OSError):
            run(self.display.wait())
        self.panel.init()
        run(self.display.show())
        self.assertEqual(self.counts(), (2, 1))

    def test_sleep_after_timeout_powers_down(self):
        self.step(0)
        self.hang()
        with self.assertRaises(OSError):
            run(self.display.sleep())
        self.assertTrue(self.panel.asleep)
        self.step(2)
        self.assertEqual(self.counts(), (2, 1))

    def test_idle_power_off(self):
        self.display.idle_ms = 30
        self.step(0)
        run(self.pause(60))
        self.assertEqual(self.panel.powered_off, 1)

    # A refresh within the idle time keeps the supply on for the burst.
    def test_no_power_off_mid_burst(self):
        self.display.idle_ms = 100
        for n in range(3):
            self.step(n)
            run(self.pause(20))
        self.assertEqual(self.panel.powered_off, 0)
        run(self.pause(150))
        self.assertEqual(self.panel.powered_off, 1)

    async def pause(self, ms):
        await asyncio.sleep_ms(ms)

    # Without the event loop, so it works in a finally or a with block after a Ctrl-C.
    def test_close_and_with(self):
        self.step(0)
        self.display.close()
        self.assertEqual(self.panel.powered_off, 1)
        with Display(self.panel) as display:
            display.fill(0)
            run(display.show())
        self.assertEqual(self.panel.powered_off, 2)

    def test_power_off_after_timeout(self):
        self.step(0)
        self.hang()
        with self.assertRaises(OSError):
            run(self.display.power_off())
        self.assertEqual(self.panel.powered_off, 1)

    # Nothing reached the panel, so the glass is still known.
    def test_cancelled_show_keeps_glass(self):
        self.step(0)
        self.panel.refresh_ms = 100
        self.step(1)

        async def cancel():
            self.display.fill_rect(500, 0, 10, 10, 0)
            task = asyncio.create_task(self.display.show())
            await asyncio.sleep_ms(10)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        run(cancel())
        self.assertEqual(self.counts(), (1, 1))
        self.panel.refresh_ms = 0
        run(self.display.show())
        self.assertEqual(self.counts(), (1, 2))

    def test_interrupted_sleep_makes_next_full(self):
        self.step(0)
        sleep = self.panel.sleep

        def interrupted():
            sleep()
            raise KeyboardInterrupt

        self.panel.sleep = interrupted
        with self.assertRaises(KeyboardInterrupt):
            run(self.display.sleep())
        self.step(1)
        self.assertFalse(self.panel.asleep)
        self.assertEqual(self.counts(), (2, 0))

    def test_wait_and_sleep_while_asleep(self):
        self.step(0)
        run(self.display.sleep())
        run(self.display.wait())
        run(self.display.sleep())

    def test_sleep(self):
        self.step(0)
        run(self.display.sleep())
        self.assertTrue(self.panel.asleep)
        # Nothing drawn since, but the panel lost its planes: full, after waking it.
        run(self.display.show())
        self.assertFalse(self.panel.asleep)
        self.assertEqual(self.counts(), (2, 0))
