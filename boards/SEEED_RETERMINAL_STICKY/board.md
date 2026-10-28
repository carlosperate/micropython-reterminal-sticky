The following files are firmware for the Seeed reTerminal Sticky (ESP32-S3R8 with 8MiB octal
SPIRAM, a 3.97" 800x480 e-paper panel, GT911 touch, and a CH343P USB-UART bridge).

The REPL is on UART0, through the CH343P. The filesystem stays within the first 16MiB of flash.

At power-up, before Python starts, the firmware latches the power on (so the board stays on
battery when the button is released), enables battery charging, powers and deselects the microSD
card, and turns off the display, touch and microphone power.

This firmware has not yet been tested on a unit.
