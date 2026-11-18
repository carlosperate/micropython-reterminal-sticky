# Turns the board off, leaving a note on the glass: e-paper keeps its picture without power.
# USB keeps the board on whatever the latch holds, so on USB it waits for an unplug.
import time

import reterminal_sticky
from sticky.display import WHITE

display = reterminal_sticky.display()


def note(text):
    display.fill(WHITE)
    display.text(text, 24, 24)
    display.show()
    # Waits out the power-down: the panel should be asleep when power goes.
    display.sleep()


if reterminal_sticky.usb_power():
    note("Unplug USB to power off.")
    while reterminal_sticky.usb_power():
        time.sleep(1)
note("Off. Hold AI Voice for a second to turn it on.")
reterminal_sticky.power_off()
# Only reached if USB came back in the meantime.
note("Still on: USB power is back.")
