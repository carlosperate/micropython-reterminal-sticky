# Runs a programme's scenes: the BLE link from the deck, the player, and the panel's display.

import asyncio

from sticky.anim import Player


def run(scenes, parse, link=None, display=None):
    """Show scenes in step with the deck until reset. parse(state) returns (scene name, step).

    Without link or display, makes sticky.ble's Link and the board's panel; tests pass fakes.
    """
    if _escape():
        print("sticky.app: Up held at boot, not starting")
        return
    if link is None:
        from sticky.ble import Link

        link = Link()
    if display is None:
        import reterminal_sticky
        from sticky.display import Display

        display = Display(reterminal_sticky.panel())
    try:
        asyncio.run(_main(scenes, parse, link, display))
    finally:
        # A Ctrl-C escapes the scheduler and leaves the task it hit half-run, so nothing can await
        # the old tasks: drop them, then turn the high voltage off and release the link directly.
        asyncio.new_event_loop()
        try:
            asyncio.run(display.power_off())
        except Exception as e:
            print("sticky.app: power-off failed", repr(e))
        try:
            link.close()
        except Exception as e:
            print("sticky.app: closing the link failed", repr(e))


async def _main(scenes, parse, link, display):
    asyncio.create_task(link.run())
    await Player(display, scenes, parse).run(link)


# Up held at boot skips the programme, so a broken main.py can't lock out mpremote.
def _escape():
    try:
        from machine import Pin

        button = Pin.board.BTN_UP
    except (ImportError, AttributeError):
        return False
    button.init(Pin.IN, Pin.PULL_UP)
    return button() == 0
