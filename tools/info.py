# Runs on the board (make info PORT=...) and prints its state for a person to read: these values
# change from moment to moment, so they aren't tests.
import gc
import time

import reterminal_sticky

gauge = reterminal_sticky.gauge()
print("USB power:  ", reterminal_sticky.usb_power())
print("Charging:   ", reterminal_sticky.charging())
print("Battery:     %d%%, %d mV, %.1f mA" % (gauge.charge(), gauge.voltage(), gauge.current()))
print("Uptime:      %d s" % (time.ticks_ms() // 1000))
gc.collect()
print("Heap free:   %d bytes" % gc.mem_free())
