# Shows which of the side buttons are pressed. They're active low.
import asyncio

import reterminal_sticky
from machine import Pin
from sticky.display import Display

BUTTONS = (
    ("AI Voice", Pin.board.BTN_POWER),
    ("Page Up", Pin.board.BTN_UP),
    ("Page Down", Pin.board.BTN_DOWN),
)


async def main(display):
    for _, pin in BUTTONS:
        pin.init(Pin.IN, Pin.PULL_UP)
    last = None
    while True:
        pressed = [name for name, pin in BUTTONS if not pin()]
        if pressed != last:
            last = pressed
            display.fill(1)
            display.text("Pressed: " + (", ".join(pressed) or "none"), 24, 24, 0)
            await display.show()
        await asyncio.sleep_ms(50)


# Leaving the block, even on Ctrl-C, turns the panel's high voltage off.
with Display(reterminal_sticky.panel()) as display:
    asyncio.run(main(display))
