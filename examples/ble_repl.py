# A REPL over Bluetooth as well as USB. Copy it to the board as boot.py, then connect from
# examples/bleuart.html in Chrome, or an app with a Nordic UART terminal.
from sticky.bleuart import repl

# Some tools only list devices whose names they know: repl("mpy-sticky"), say.
uart = repl()
print("REPL also on BLE as", uart.name)
