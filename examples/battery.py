# Shows the battery on the panel every 30 s, so it can be read off USB too.
import asyncio

import reterminal_sticky
from sticky.display import Display


async def main(display):
    gauge = reterminal_sticky.gauge()
    while True:
        lines = (
            "USB power: %s" % reterminal_sticky.usb_power(),
            "Charging:  %s" % reterminal_sticky.charging(),
            "Battery:   %d%%, %d mV" % (gauge.charge(), gauge.voltage()),
            "Current:   %.1f mA" % gauge.average_current(),
        )
        display.fill(1)
        for i, line in enumerate(lines):
            display.text(line, 24, 24 + 16 * i, 0)
        await display.show()
        await asyncio.sleep(30)


# Leaving the block, even on Ctrl-C, turns the panel's high voltage off.
with Display(reterminal_sticky.panel()) as display:
    asyncio.run(main(display))
