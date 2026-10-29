# Runs on the board (make info PORT=...) and prints its state for a person to read: these values
# change from moment to moment, so they aren't tests. The gauge is only read.
import gc
import time

from machine import I2C, Pin

BQ27220 = 0x55


def gauge(command):
    return int.from_bytes(I2C(0).readfrom_mem(BQ27220, command, 2), "little")


current = gauge(0x0C)
if current >= 0x8000:
    current -= 0x10000

print("USB power:  ", Pin("VBUS_SENSE").value() == 1)
# The charger's STAT is open drain, low while charging.
print("Charging:   ", Pin("CHG_STAT", Pin.IN, Pin.PULL_UP).value() == 0)
print("Battery:     %d%%, %d mV, %d mA" % (gauge(0x2C), gauge(0x08), current))
print("Uptime:      %d s" % (time.ticks_ms() // 1000))
gc.collect()
print("Heap free:   %d bytes" % gc.mem_free())
