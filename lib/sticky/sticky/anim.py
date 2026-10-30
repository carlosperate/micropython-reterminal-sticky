# Scenes, keyframes and the player that turns the deck's latest state into frames on the glass.
# A scene draws its whole frame: the partial refresh only drives the pixels that changed.

import asyncio

SETTLE_MS = 200


class Scene:
    """Subclass with a name and draw(); override keyframes() to animate."""

    name = None

    def draw(self, display, step, pose):
        raise NotImplementedError

    def keyframes(self, step):
        """The Keyframes to play for step, or None for a still frame."""
        return None


class Keyframes:
    """(pose, hold_ms) pairs. A hold counts from the refresh's start, so a short one is a refresh."""

    def __init__(self, poses, loop=False):
        self.poses = poses
        self.loop = loop


class Player:
    """Shows the scene parse(state) names for each new state of link (changed() and state)."""

    def __init__(self, display, scenes, parse, settle_ms=SETTLE_MS):
        self.display = display
        self.scenes = {scene.name: scene for scene in scenes}
        self.parse = parse
        self.settle_ms = settle_ms
        self.scene = None
        self._task = None

    async def run(self, link):
        try:
            while True:
                await link.changed()
                state = await self._settled(link)
                try:
                    name, step = self.parse(state)
                    scene = self.scenes[name]
                except Exception as e:
                    # The glass keeps its picture: a typo in the deck mustn't blank the Sticky.
                    print("sticky.anim: ignored", state, repr(e))
                    continue
                await self._stop()
                self._task = asyncio.create_task(self._play(scene, step))
        finally:
            await self._stop()

    # A burst of clicks or a jump costs one refresh, of the last state.
    async def _settled(self, link):
        while True:
            try:
                await asyncio.wait_for_ms(link.changed(), self.settle_ms)
            except asyncio.TimeoutError:
                # The link's own value: a write wait_for raced with has already updated it.
                return link.state

    async def _stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    # A failing scene logs and leaves the glass: one bad frame mustn't end the programme. The
    # display turns the high voltage off once the frames stop, whatever the reason.
    async def _play(self, scene, step):
        try:
            # A new scene gets a full refresh: it clears ghosting where the picture changes anyway.
            full = scene.name != self.scene
            frames = scene.keyframes(step)
            if not frames or not frames.poses:
                await self._frame(scene, step, None, full)
                return
            while True:
                for pose, hold_ms in frames.poses:
                    await self._frame(scene, step, pose, full)
                    full = False
                    await asyncio.sleep_ms(hold_ms)
                if not frames.loop:
                    return
        except Exception as e:
            print("sticky.anim: scene failed", scene.name, step, repr(e))

    async def _frame(self, scene, step, pose, full):
        scene.draw(self.display, step, pose)
        await self.display.show(full)
        # Only once shown: a scene change cancelled before this still gets its full refresh.
        self.scene = scene.name
