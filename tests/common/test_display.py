# Display's refresh policy, power-off and sleep, on SimPanel on the unix port and on the unit's
# panel, counted through its SPI log. What only the simulated glass shows is in test_display_sim.
import asyncio
import gc
import sys
import time
import unittest

import reterminal_sticky
from panel_log import Recording, counts, leave_white
from sticky.display import BLACK, HEIGHT, WHITE, WIDTH, Display

BOARD = sys.platform == "esp32"
if not BOARD:
    from sticky_sim import SimPanel

run = asyncio.run
GREY = b"\xaa" * 96000  # every pixel level 2
# What a refresh takes, added to waits for the idle power-off after one.
REFRESH_MS = 600 if BOARD else 0


# Fixtures only: the test classes share them without running each other's tests.
class DisplayCase(unittest.TestCase):
    def setUp(self):
        gc.collect()
        if BOARD:
            try:
                self.panel = reterminal_sticky.panel()
            except NotImplementedError as e:
                self.skipTest(str(e))
            self.bus = self.panel.spi = Recording(self.panel.spi, self.panel._cmd)
        else:
            self.panel = SimPanel()
        self.display = Display(self.panel, burst=3)

    # Drops the display's idle task, which would otherwise keep this test's buffers alive.
    def tearDown(self):
        asyncio.new_event_loop()
        if BOARD:
            self.panel.sleep()
        self.panel = self.display = self.bus = None

    @classmethod
    def tearDownClass(cls):
        leave_white()

    def kinds(self):
        if BOARD:
            return counts(self.bus.log)
        p = self.panel
        return {
            "full": p.full,
            "partial": p.partial,
            "grey": p.grey,
            "clean": p.cleaned,
            "power_off": p.powered_off,
        }

    def counts(self):
        kinds = self.kinds()
        return kinds["full"], kinds["partial"]

    def powered_off(self):
        return self.kinds()["power_off"]

    def powered(self):
        return self.panel._powered if BOARD else self.panel.powered

    def asleep(self):
        return self.panel._asleep is True if BOARD else self.panel.asleep

    def draw(self, n):
        self.display.fill_rect(10 * n, 0, 10, 10, BLACK)

    def step(self, n, full=False):
        self.draw(n)
        run(self.display.show_async(full))

    # A refresh lasting ms: the unit's take about 480 ms whatever this says.
    def refresh_takes(self, ms):
        if not BOARD:
            self.panel.refresh_ms = ms

    # The next refresh outlasts a 10 ms timeout, so waits for it time out.
    def hang(self):
        if BOARD:
            self.panel.wait()
        else:
            self.panel.refresh_ms = 60_000
        self.panel.timeout_ms = 10

    # Waits work again, the hung refresh over.
    def recover(self):
        if BOARD:
            self.panel.timeout_ms = 10_000
            self.panel.wait()
        else:
            self.panel.refresh_ms = 0
            self.panel.init()

    async def pause(self, ms):
        await asyncio.sleep_ms(ms)

    # Cut short while waiting for the last refresh, which left the supply on: it still goes off.
    def cancel_while_busy(self, call):
        self.display.idle_ms = 50
        self.refresh_takes(100)

        async def main():
            self.display.fill_rect(500, 0, 10, 10, 0)
            await self.display.show_async()
            self.display.fill_rect(600, 0, 10, 10, 0)
            task = asyncio.create_task(call())
            await asyncio.sleep_ms(10)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            self.assertTrue(self.powered())
            await asyncio.sleep_ms(300 + REFRESH_MS)

        run(main())
        self.assertFalse(self.powered())
        self.assertEqual(self.powered_off(), 1)


class TestDisplay(DisplayCase):
    def test_starts_white(self):
        self.assertEqual(self.display.buffer, b"\xff" * 48000)

    # WIDTH and HEIGHT, for buffers made before a display, are the Sticky's glass.
    def test_size_from_panel(self):
        glass = reterminal_sticky._GLASS
        self.assertEqual((WIDTH, HEIGHT), (glass["width"], glass["height"]))
        self.assertEqual((self.display.width, self.display.height), (WIDTH, HEIGHT))

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
        run(self.display.show_async())
        self.assertEqual(self.counts(), (1, 0))
        run(self.display.show_async(True))
        self.assertEqual(self.counts(), (2, 0))

    def test_unchanged_frame_yields(self):
        self.step(0)
        ran = []

        async def other():
            ran.append(1)

        async def main():
            asyncio.create_task(other())
            await self.display.show_async()
            self.assertEqual(ran, [1])

        run(main())

    # Reaching the burst limit alone doesn't flash a still frame.
    def test_unchanged_after_burst_skipped(self):
        for n in range(4):
            self.step(n)
        run(self.display.show_async())
        self.assertEqual(self.counts(), (1, 3))

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

    def test_wait_timeout_makes_next_full(self):
        self.step(0)
        self.hang()
        self.step(1)
        with self.assertRaises(OSError):
            run(self.display.wait_async())
        self.recover()
        run(self.display.show_async())
        self.assertEqual(self.counts(), (2, 1))

    def test_sleep_after_timeout_powers_down(self):
        self.step(0)
        self.hang()
        self.step(1)
        with self.assertRaises(OSError):
            run(self.display.sleep_async())
        self.assertTrue(self.asleep())
        self.recover()
        self.step(2)
        self.assertEqual(self.counts(), (2, 1))

    def test_idle_power_off(self):
        self.display.idle_ms = 30
        self.step(0)
        run(self.pause(60 + REFRESH_MS))
        self.assertEqual(self.powered_off(), 1)

    # A refresh within the idle time keeps the supply on for the burst.
    def test_no_power_off_mid_burst(self):
        self.display.idle_ms = 100
        for n in range(3):
            self.step(n)
            run(self.pause(20))
        self.assertEqual(self.powered_off(), 0)
        run(self.pause(150 + REFRESH_MS))
        self.assertEqual(self.powered_off(), 1)

    # Without the event loop, so it works in a finally or a with block after a Ctrl-C.
    def test_close_and_with(self):
        self.step(0)
        self.display.close()
        self.assertEqual(self.powered_off(), 1)
        with Display(self.panel) as display:
            display.fill(0)
            run(display.show_async())
        self.assertEqual(self.powered_off(), 2)

    # The driver's waits are capped, so the idle power-off goes ahead after a timeout.
    def test_power_off_after_timeout(self):
        self.step(0)
        self.hang()
        self.step(1)
        self.display.idle_ms = 0
        run(self.display._power_off_when_idle())
        self.assertEqual(self.powered_off(), 1)

    # Nothing reached the panel, so the glass is still known.
    def test_cancelled_show_keeps_glass(self):
        self.step(0)
        self.refresh_takes(100)
        self.step(1)

        async def cancel():
            self.display.fill_rect(500, 0, 10, 10, 0)
            task = asyncio.create_task(self.display.show_async())
            await asyncio.sleep_ms(10)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        run(cancel())
        self.assertEqual(self.counts(), (1, 1))
        self.refresh_takes(0)
        run(self.display.show_async())
        self.assertEqual(self.counts(), (1, 2))

    def test_cancelled_show_still_powers_off(self):
        self.cancel_while_busy(self.display.show_async)

    def test_interrupted_sleep_makes_next_full(self):
        self.step(0)
        sleep = self.panel.sleep

        def interrupted():
            sleep()
            raise KeyboardInterrupt

        self.panel.sleep = interrupted
        with self.assertRaises(KeyboardInterrupt):
            run(self.display.sleep_async())
        self.panel.sleep = sleep
        self.step(1)
        self.assertFalse(self.asleep())
        self.assertEqual(self.counts(), (2, 0))

    def test_wait_and_sleep_while_asleep(self):
        self.step(0)
        run(self.display.sleep_async())
        run(self.display.wait_async())
        run(self.display.sleep_async())

    # asyncio.run() returns with the main task, so the idle power-off never runs: close() does it.
    def test_run_leaves_supply_on(self):
        self.display.idle_ms = 30
        self.step(0)
        time.sleep_ms(60)
        self.assertTrue(self.powered())
        self.display.close()
        self.assertFalse(self.powered())

    def test_sleep_after_partial(self):
        self.step(0)
        self.step(1)
        run(self.display.sleep_async())
        self.assertEqual(self.counts(), (2, 1))
        self.assertTrue(self.asleep())

    def test_sleep(self):
        self.step(0)
        run(self.display.sleep_async())
        self.assertTrue(self.asleep())
        # Nothing drawn since, but the panel lost its planes: full, after waking it.
        run(self.display.show_async())
        self.assertFalse(self.asleep())
        self.assertEqual(self.counts(), (2, 0))


# The plain calls, with no event loop: each leaves the supply off as it returns.
class TestPlain(DisplayCase):
    def test_show(self):
        self.draw(0)
        self.display.show()
        self.assertEqual(self.counts(), (1, 0))
        self.assertFalse(self.powered())
        self.assertEqual(self.powered_off(), 1)

    def test_burst(self):
        seen = []
        for n in range(9):
            self.draw(n)
            self.display.show()
            seen.append(self.counts())
        self.assertEqual(
            seen, [(1, 0), (1, 1), (1, 2), (1, 3), (2, 3), (2, 4), (2, 5), (2, 6), (3, 6)]
        )
        self.assertEqual(self.powered_off(), 9)

    # Not refreshed, but an _async refresh's supply still goes off.
    def test_unchanged_frame(self):
        run(self.display.show_async())
        self.assertTrue(self.powered())
        self.display.show()
        self.assertEqual(self.counts(), (1, 0))
        self.assertFalse(self.powered())
        self.assertEqual(self.powered_off(), 1)
        self.display.show()
        self.assertEqual(self.powered_off(), 1)

    def test_wait_timeout(self):
        self.display.show()
        self.hang()
        self.draw(1)
        with self.assertRaises(OSError):
            self.display.show()
        self.assertFalse(self.powered())
        self.recover()
        self.display.show()
        self.assertEqual(self.counts(), (2, 1))  # the timed-out partial, then full

    # A Ctrl-C once the refresh has started.
    def test_interrupted(self):
        self.display.show()
        show = self.panel.show

        def interrupted(frame, old=None):
            show(frame, old)
            raise KeyboardInterrupt

        self.panel.show = interrupted
        self.draw(1)
        with self.assertRaises(KeyboardInterrupt):
            self.display.show()
        self.assertFalse(self.powered())
        self.panel.show = show
        self.draw(2)
        self.display.show()
        self.assertEqual(self.counts(), (2, 1))

    def test_show_grey(self):
        self.display.show()
        for clean in (False, True):
            self.display.show_grey(GREY, clean)
            self.assertFalse(self.powered())
        kinds = self.kinds()
        self.assertEqual((kinds["grey"], kinds["clean"]), (2, 2))
        self.display.show()
        self.assertEqual(self.counts(), (2, 0))

    # Refused, it still turns off the supply an _async refresh left on, and the glass stays known.
    def test_show_grey_wrong_size(self):
        run(self.display.show_async())
        self.assertTrue(self.powered())
        with self.assertRaises(ValueError):
            self.display.show_grey(bytes(48000))
        self.assertFalse(self.powered())
        self.assertEqual(self.kinds()["grey"], 0)
        self.draw(1)
        self.display.show()
        self.assertEqual(self.counts(), (1, 1))

    def test_sleep(self):
        self.display.show()
        self.display.sleep()
        self.assertTrue(self.asleep())
        self.display.show()
        self.assertEqual(self.counts(), (2, 0))

    # The glass isn't left on a partial: it's redrawn with a full refresh first.
    def test_sleep_after_partial(self):
        self.display.show()
        self.draw(1)
        self.display.show()
        self.draw(2)  # drawn but not shown: not what's redrawn
        self.display.sleep()
        self.assertEqual(self.counts(), (2, 1))
        self.assertTrue(self.asleep())

    def test_close_after_partial(self):
        self.display.show()
        self.draw(1)
        self.display.show()
        self.display.close()
        self.assertEqual(self.counts(), (2, 1))
        self.assertFalse(self.powered())
        self.display.close()
        self.assertEqual(self.counts(), (2, 1))

    # The grey waveform is a full one, so there's nothing to redraw.
    def test_close_after_grey(self):
        self.display.show()
        self.draw(1)
        self.display.show()
        self.display.show_grey(GREY)
        self.display.close()
        self.assertEqual(self.counts(), (1, 1))

    def test_close_with_hung_panel(self):
        self.display.show()
        self.draw(1)
        self.hang()
        with self.assertRaises(OSError):
            self.display.show()
        self.display.close()
        self.assertFalse(self.powered())

    # 1 is white, so text() draws in black unless told otherwise.
    def test_text(self):
        self.assertEqual((BLACK, WHITE), (0, 1))
        self.display.text("x", 0, 0)
        self.assertNotEqual(self.display.buffer, b"\xff" * 48000)
        self.display.fill(BLACK)
        self.display.text("x", 0, 0, WHITE)
        self.assertNotEqual(self.display.buffer, bytes(48000))


class TestDisplayGrey(DisplayCase):
    def counts(self):
        kinds = self.kinds()
        return kinds["full"], kinds["partial"], kinds["grey"]

    def test_full_after_grey(self):
        self.step(0)
        run(self.display.show_grey_async(GREY))
        self.step(1)
        self.assertEqual(self.counts(), (2, 0, 1))
        self.step(2)
        self.assertEqual(self.counts(), (2, 1, 1))

    # Even an unchanged buffer is shown again: the glass holds the greys.
    def test_unchanged_buffer_after_grey(self):
        self.step(0)
        run(self.display.show_grey_async(GREY))
        run(self.display.show_async())
        self.assertEqual(self.counts(), (2, 0, 1))

    # Black, then white, with the controller's waveform, each waited for, then the greys.
    def test_clean_first(self):
        calls = []
        clean, show_grey = self.panel.clean, self.panel.show_grey
        self.panel.clean = lambda white=True: (calls.append(("clean", white)), clean(white))
        self.panel.show_grey = lambda frame: (
            calls.append(("grey", self.panel.busy())),
            show_grey(frame),
        )
        self.refresh_takes(30)
        self.step(0)
        run(self.display.show_grey_async(GREY, clean=True))
        self.assertEqual(calls, [("clean", False), ("clean", True), ("grey", False)])
        run(self.display.show_grey_async(GREY))
        self.assertEqual(self.kinds()["clean"], 2)  # not unless asked

    def test_frame_size(self):
        self.step(0)
        with self.assertRaises(ValueError):
            run(self.display.show_grey_async(bytearray(48000)))
        self.assertEqual(self.kinds()["grey"], 0)
        self.step(1)
        self.assertEqual(self.counts(), (1, 1, 0))

    def test_cut_short_leaves_next_full(self):
        self.step(0)

        def interrupted(frame):
            raise KeyboardInterrupt

        self.panel.show_grey = interrupted
        with self.assertRaises(KeyboardInterrupt):
            run(self.display.show_grey_async(GREY))
        self.step(1)
        self.assertEqual(self.counts(), (2, 0, 0))

    def test_waits_for_refresh(self):
        self.refresh_takes(50)
        self.step(0)
        self.assertTrue(self.panel.busy())
        run(self.display.show_grey_async(GREY))
        self.assertEqual(self.kinds()["grey"], 1)

    # Cut short before the grey refresh starts.
    def test_cancelled_grey_still_powers_off(self):
        self.cancel_while_busy(lambda: self.display.show_grey_async(GREY))
        self.assertEqual(self.kinds()["grey"], 0)

    # The grey waveform turns the high voltage off; the idle power-off isn't needed.
    def test_no_power_on_after_grey(self):
        self.step(0)
        run(self.display.show_grey_async(GREY))
        self.assertFalse(self.powered())


if __name__ == "__main__":
    unittest.main()
