# Shows a picture in four greys, then goes back to black and white.
import asyncio

import framebuf
import reterminal_sticky
from sticky.display import Display


async def main(display):
    grey = bytearray(800 * 480 // 4)
    fb = framebuf.FrameBuffer(grey, 800, 480, framebuf.GS2_HMSB)
    fb.fill(3)  # 0 is black, 3 white
    fb.text("four greys", 40, 60, 0)
    for level in range(4):
        fb.fill_rect(40 + 180 * level, 120, 160, 240, level)
        fb.text("level %d" % level, 40 + 180 * level, 380, 0)
    await display.show_grey(grey)  # about 1.2 s on the glass
    await asyncio.sleep(5)
    display.fill(1)
    display.text("back to black and white", 24, 24, 0)
    await display.show()  # full: a partial can't clear greys
    await display.sleep()


with Display(reterminal_sticky.panel()) as display:
    asyncio.run(main(display))
