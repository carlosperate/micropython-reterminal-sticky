# Echoes each line sent over the BLE UART and shows it on the panel. Send from nRF Connect or
# Bluefruit Connect (their UART screens), or from examples/bleuart.html in Chrome.
import asyncio

import reterminal_sticky
from sticky.bleuart import BLEUART
from sticky.display import WHITE


async def show(display, text):
    display.fill(WHITE)
    display.text(text, 24, 24)
    await display.show_async()


async def main(uart, display):
    await show(display, "Connect to " + uart.name)
    reader = asyncio.StreamReader(uart)
    while True:
        line = await reader.readline()
        uart.write(b"echo: " + line)
        try:
            text = line.decode().strip()
        except UnicodeError:
            text = repr(line)
        await show(display, text)


# Leaving the block, even on Ctrl-C, stops advertising and turns the high voltage off.
with BLEUART() as uart, reterminal_sticky.display() as display:
    asyncio.run(main(uart, display))
