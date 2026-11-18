# Shows which of the side buttons are pressed. They're active low.
import time

import reterminal_sticky
from machine import Pin
from sticky.display import WHITE

BUTTONS = (
    ("AI Voice", Pin.board.BTN_POWER),
    ("Page Up", Pin.board.BTN_UP),
    ("Page Down", Pin.board.BTN_DOWN),
)

for _, pin in BUTTONS:
    pin.init(Pin.IN, Pin.PULL_UP)
display = reterminal_sticky.display()
last = None
while True:
    pressed = [name for name, pin in BUTTONS if not pin()]
    if pressed != last:
        last = pressed
        display.fill(WHITE)
        display.text("Pressed: " + (", ".join(pressed) or "none"), 24, 24)
        display.show()
    time.sleep_ms(50)
