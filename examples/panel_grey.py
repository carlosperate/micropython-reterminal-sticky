# Shows a picture in four greys, then goes back to black and white.
import time

import framebuf
import reterminal_sticky

display = reterminal_sticky.display()
w, h = display.width, display.height
grey = bytearray(w * h // 4)
fb = framebuf.FrameBuffer(grey, w, h, framebuf.GS2_HMSB)
fb.fill(3)  # 0 is black, 3 white
fb.text("four greys", 40, 60, 0)
for level in range(4):
    fb.fill_rect(40 + 180 * level, 120, 160, 240, level)
    fb.text("level %d" % level, 40 + 180 * level, 380, 0)
display.show_grey(grey)  # about 1.2 s on the glass
time.sleep(5)
display.text("back to black and white", 24, 24)
display.show()  # full: a partial can't clear greys
display.sleep()
