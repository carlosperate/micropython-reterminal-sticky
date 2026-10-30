# Draws on the e-paper panel, then changes part of the picture with partial refreshes.
import asyncio

import reterminal_sticky
from sticky.display import Display


async def main(display):
    display.fill(1)  # 1 is white
    display.rect(0, 0, 800, 480, 0)
    display.text("reTerminal Sticky", 24, 24, 0)
    display.ellipse(400, 240, 120, 120, 0, True)
    await display.show()  # the first refresh is full
    for n in range(1, 6):
        display.fill_rect(24, 440, 300, 16, 1)
        display.text("partial refresh %d" % n, 24, 440, 0)
        await display.show()  # only the pixels that changed
        await asyncio.sleep(1)
    await display.sleep()  # the image stays, the panel powers down


# Leaving the block, even on Ctrl-C, turns the panel's high voltage off.
with Display(reterminal_sticky.panel()) as display:
    asyncio.run(main(display))
