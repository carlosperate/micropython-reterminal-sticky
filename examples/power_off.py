# Turns the board off, leaving a note on the glass: e-paper keeps its picture without power.
# USB keeps the board on whatever the latch holds, so on USB it waits for an unplug.
import asyncio

import reterminal_sticky
from sticky.display import Display


async def note(display, text):
    display.fill(1)
    display.text(text, 24, 24, 0)
    await display.show()
    # Waits out the refresh and the power-down: the panel should be asleep when power goes.
    await display.sleep()


async def main(display):
    if reterminal_sticky.usb_power():
        await note(display, "Unplug USB to power off.")
        while reterminal_sticky.usb_power():
            await asyncio.sleep(1)
    await note(display, "Off. Hold AI Voice for a second to turn it on.")
    reterminal_sticky.power_off()
    # Only reached if USB came back in the meantime.
    await note(display, "Still on: USB power is back.")


with Display(reterminal_sticky.panel()) as display:
    asyncio.run(main(display))
