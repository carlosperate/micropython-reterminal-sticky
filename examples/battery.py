# Shows the battery on the panel every 30 s, so it can be read off USB too.
import time

import reterminal_sticky
from sticky.display import WHITE

display = reterminal_sticky.display()
gauge = reterminal_sticky.gauge()
while True:
    lines = (
        "USB power: %s" % reterminal_sticky.usb_power(),
        "Charging:  %s" % reterminal_sticky.charging(),
        "Battery:   %d%%, %d mV" % (gauge.state_of_charge(), gauge.voltage()),
        "Current:   %.1f mA" % gauge.average_current(),
    )
    display.fill(WHITE)
    for i, line in enumerate(lines):
        display.text(line, 24, 24 + 16 * i)
    display.show()
    time.sleep(30)
