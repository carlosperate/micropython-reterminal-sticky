# Draws on the e-paper panel, then changes part of the picture with partial refreshes.
import time

import reterminal_sticky
from sticky.display import BLACK, WHITE

display = reterminal_sticky.display()
display.rect(0, 0, display.width, display.height, BLACK)
display.text("reTerminal Sticky", 24, 24)
display.ellipse(400, 240, 120, 120, BLACK, True)
display.show()  # the first refresh is full
for n in range(1, 6):
    display.fill_rect(24, 440, 300, 16, WHITE)
    display.text("partial refresh %d" % n, 24, 440)
    display.show()  # only the pixels that changed
    time.sleep(1)
display.sleep()  # the image stays, the panel powers down
