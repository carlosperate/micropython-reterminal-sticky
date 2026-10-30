import asyncio
import unittest

from sticky.anim import Keyframes, Player, Scene
from sticky.app import run
from sticky.display import Display
from sticky_sim import SimPanel


class Link:
    """The two members the player uses, fed by the test."""

    def __init__(self):
        self.state = b""
        self._flag = asyncio.ThreadSafeFlag()

    def send(self, state):
        self.state = state
        self._flag.set()

    async def changed(self):
        await self._flag.wait()
        return self.state

    async def run(self):
        pass

    def close(self):
        self.closed = True


class Still(Scene):
    name = "still"

    def __init__(self):
        self.drawn = []

    def draw(self, display, step, pose):
        self.drawn.append((step, pose))
        display.fill(1)
        display.fill_rect(10 * step, 0, 10, 10, 0)


class Blink(Scene):
    name = "blink"

    def __init__(self, loop=True):
        self.drawn = []
        self.frames = Keyframes([("open", 30), ("shut", 30)], loop=loop)

    def draw(self, display, step, pose):
        self.drawn.append(pose)
        display.fill(1)
        display.fill_rect(0, 0, 100, 100 if pose == "open" else 10, 0)

    def keyframes(self, step):
        return self.frames


class Broken(Scene):
    name = "broken"

    def draw(self, display, step, pose):
        raise IndexError("no such step")


class FailsLater(Blink):
    name = "fails"

    def draw(self, display, step, pose):
        if pose == "shut":
            raise ValueError("bad pose")
        super().draw(display, step, pose)


class Empty(Blink):
    name = "empty"

    def keyframes(self, step):
        return Keyframes([], loop=True)


def parse(state):
    name, _, step = state.decode().partition(" ")
    return name, int(step or 0)


class TestPlayer(unittest.TestCase):
    def setUp(self):
        self.panel = SimPanel()
        self.display = Display(self.panel, idle_ms=50)
        self.link = Link()
        self.still = Still()
        self.blink = Blink()
        scenes = [self.still, self.blink, Broken(), Empty(), FailsLater()]
        self.player = Player(self.display, scenes, parse, settle_ms=20)

    # Drops the display's idle task, which would otherwise keep this test's buffers alive.
    def tearDown(self):
        asyncio.new_event_loop()

    # Sends each (state, wait_ms) in turn with the player running, then stops it.
    def session(self, *steps):
        async def main():
            task = asyncio.create_task(self.player.run(self.link))
            for state, wait_ms in steps:
                self.link.send(state)
                await asyncio.sleep_ms(wait_ms)
            task.cancel()
            # Cancelling run() stops its animation too, through its finally.
            try:
                await task
            except asyncio.CancelledError:
                pass

        asyncio.run(main())

    def counts(self):
        return self.panel.full, self.panel.partial

    def test_still_scene_then_step(self):
        self.session((b"still 1", 60), (b"still 2", 60))
        self.assertEqual(self.still.drawn, [(1, None), (2, None)])
        # The first scene is a full refresh; a new step in it is a partial.
        self.assertEqual(self.counts(), (1, 1))
        self.assertEqual(self.panel.glass, self.display.buffer)

    def test_scene_change_is_full(self):
        self.session((b"still 1", 60), (b"blink 0", 50), (b"still 1", 60))
        self.assertEqual(self.panel.full, 3)

    def test_burst_settles_to_last(self):
        self.session((b"still 1", 1), (b"still 2", 1), (b"still 3", 100))
        self.assertEqual(self.still.drawn, [(3, None)])

    def test_unknown_or_bad_state_ignored(self):
        self.session((b"still 1", 60), (b"nope 1", 60), (b"still x", 60))
        self.assertEqual(self.still.drawn, [(1, None)])
        self.assertEqual(self.counts(), (1, 0))

    def test_keyframes_loop_until_new_state(self):
        self.session((b"blink 0", 400), (b"still 1", 100))
        poses = self.blink.drawn
        self.assertTrue(len(poses) >= 4, poses)
        self.assertEqual(poses[:4], ["open", "shut", "open", "shut"])
        self.assertEqual(self.still.drawn, [(1, None)])
        # The new state stopped the animation: the glass shows the still scene.
        self.assertEqual(self.panel.glass, self.display.buffer)

    def test_keyframes_once(self):
        self.blink.frames.loop = False
        self.session((b"blink 0", 400))
        self.assertEqual(self.blink.drawn, ["open", "shut"])

    def test_still_frame_powers_off(self):
        self.session((b"still 1", 100))
        self.assertEqual(self.panel.powered_off, 1)

    # Holds shorter than the display's idle time keep the supply on; a longer one turns it off.
    def test_long_hold_powers_off(self):
        self.blink.frames = Keyframes([("open", 200), ("shut", 30)])
        self.session((b"blink 0", 400))
        self.assertEqual(self.blink.drawn, ["open", "shut"])
        self.assertEqual(self.panel.powered_off, 2)

    def test_failing_scene_keeps_player(self):
        self.session((b"still 1", 100), (b"broken 0", 100), (b"still 2", 100))
        self.assertEqual(self.still.drawn, [(1, None), (2, None)])

    # The first pose turned the high voltage on; the failure mustn't leave it on.
    def test_failing_keyframe_powers_off(self):
        self.session((b"fails 0", 200))
        self.assertEqual(self.panel.powered_off, 1)

    def test_empty_keyframes_drawn_once(self):
        self.session((b"empty 0", 100), (b"still 1", 100))
        self.assertEqual(self.player.scenes["empty"].drawn, [None])
        self.assertEqual(self.still.drawn, [(1, None)])


class TestRun(unittest.TestCase):
    def test_run_with_fakes(self):
        link = Link()
        panel = SimPanel()
        still = Still()

        async def deck():
            link.send(b"still 2")
            await asyncio.sleep_ms(400)
            raise KeyboardInterrupt  # ends run(), which otherwise runs until reset

        link.run = deck
        with self.assertRaises(KeyboardInterrupt):
            run([still], parse, link=link, display=Display(panel))
        self.assertEqual(still.drawn, [(2, None)])
        # The Ctrl-C path released the link and turned the panel's supply off.
        self.assertTrue(link.closed)
        self.assertEqual(panel.powered_off, 1)

    # Interrupted mid-animation, the player's own task stops too, and run() can start again.
    def test_run_twice(self):
        panel = SimPanel()
        blink = Blink()

        for _ in range(2):
            link = Link()

            async def deck(link=link):
                link.send(b"blink 0")
                await asyncio.sleep_ms(400)
                raise KeyboardInterrupt

            link.run = deck
            with self.assertRaises(KeyboardInterrupt):
                run([blink], parse, link=link, display=Display(panel))
            drawn = len(blink.drawn)

            # Nothing left over keeps animating once run() has returned.
            async def pause():
                await asyncio.sleep_ms(200)

            asyncio.run(pause())
            self.assertEqual(len(blink.drawn), drawn)
        self.assertTrue(drawn >= 4)
