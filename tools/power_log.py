# Runs on the board: logs the battery to flash every 10 s, as off USB there's no serial. Start it
# from boot.py with power_log.start(); each start writes a header, so the log shows every boot.
# Errors go in the log too. Read it back with mpremote cp :power.csv .
import time

import reterminal_sticky
from machine import Timer


def start(path="power.csv", period_ms=10_000):
    gauge = reterminal_sticky.gauge()

    def log(_):
        try:
            line = "%d,%d,%d,%.1f,%.1f,%d\n" % (
                time.ticks_ms(),
                reterminal_sticky.usb_power(),
                gauge.voltage(),
                gauge.current(),
                gauge.average_current(),
                gauge.charge(),
            )
        except Exception as e:
            line = "%d,error,%r\n" % (time.ticks_ms(), e)
        try:
            with open(path, "a") as f:
                f.write(line)
        except OSError:
            pass  # a full filesystem: nowhere to say so

    with open(path, "a") as f:
        f.write("ms,usb,mv,ma,avg_ma,soc\n")
    log(None)
    # A software timer: a hardware id is shared with any programme that asks for it.
    timer = Timer(-1)
    timer.init(period=period_ms, callback=log)
    return timer
