# The player and run() on the real panel, fed states by a fake link: BLE needs a central, which
# the deck's Chrome checks provide (deck-app/chrome/).
import asyncio
import unittest

import reterminal_sticky
from sticky.anim import Keyframes, Player, Scene
from sticky.app import run
from sticky.display import Display


class Link:
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


class Count(Scene):
    name = "count"

    def draw(self, display, step, pose):
        display.fill(1)
        display.text("anim test: count %d" % step, 16, 16, 0)
        display.fill_rect(100 + 40 * step, 200, 30, 30, 0)


class Blink(Scene):
    name = "blink"
    frames = Keyframes([(1, 100), (0, 100)], loop=True)

    def keyframes(self, step):
        return self.frames

    def draw(self, display, step, pose):
        display.fill(1)
        display.text("anim test: blink", 16, 16, 0)
        if pose:
            display.fill_rect(300, 140, 200, 200, 0)


def parse(state):
    name, _, step = state.decode().partition(" ")
    return name, int(step or 0)


class TestPlayer(unittest.TestCase):
    def panel(self):
        try:
            return reterminal_sticky.panel()
        except NotImplementedError as e:
            self.skipTest(str(e))

    def test_session(self):
        panel = self.panel()
        display = Display(panel, idle_ms=300)
        link = Link()
        player = Player(display, [Count(), Blink()], parse)
        seen = []

        async def main():
            task = asyncio.create_task(player.run(link))
            for state, wait_ms in ((b"count 1", 1200), (b"count 2", 1200), (b"blink 0", 2500)):
                link.send(state)
                await asyncio.sleep_ms(wait_ms)
                seen.append(display.partials)
            # The animation runs: the burst of partials grows while it blinks.
            self.assertTrue(display.partials >= 2, display.partials)
            link.send(b"count 3")
            await asyncio.sleep_ms(2000)
            seen.append(display.partials)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            # A still picture lets the idle power-off turn the high voltage off.
            self.assertFalse(panel._powered)
            await display.sleep()

        asyncio.run(main())
        # Full for a new scene (0 partials since), partial for a new step.
        self.assertEqual((seen[0], seen[1], seen[3]), (0, 1, 0))

    # Standing in for a Ctrl-C: run() must leave the high voltage off and the link closed.
    def test_run_interrupted(self):
        panel = self.panel()
        display = Display(panel)
        link = Link()

        async def deck():
            link.send(b"count 4")
            await asyncio.sleep_ms(1500)
            raise KeyboardInterrupt

        link.run = deck
        with self.assertRaises(KeyboardInterrupt):
            run([Count()], parse, link=link, display=display)
        self.assertFalse(panel._powered)
        self.assertTrue(link.closed)
        panel.sleep()
