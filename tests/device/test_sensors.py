# Runs after test_pins.py (the runner goes in name order): I2C(0) leaves GPIO0/1 set up for I2C.
# Not I2C(1): the GT911 is unpowered, and a scan could feed it through its pins.
import unittest

import reterminal_sticky
from machine import I2C, Pin

SHT40 = 0x44
PCF8563 = 0x51
BQ27220 = 0x55
LSM6DS3TR_C = 0x6A


class TestSensorBus(unittest.TestCase):
    def test_scan(self):
        self.assertEqual(I2C(0).scan(), [SHT40, PCF8563, BQ27220, LSM6DS3TR_C])

    def test_imu_who_am_i(self):
        self.assertEqual(I2C(0).readfrom_mem(LSM6DS3TR_C, 0x0F, 1), b"\x6a")


class TestPower(unittest.TestCase):
    def test_gauge(self):
        # Bounds that hold at any charge: the charger stops at 4.2 V and is set to 555 mA, so a
        # scale ten times out reads outside them.
        gauge = reterminal_sticky.gauge()
        self.assertTrue(0 < gauge.voltage() <= 4400)
        self.assertTrue(0 <= gauge.charge() <= 100)
        self.assertTrue(-1000 <= gauge.current() <= 1000)
        # Seeed's 750 mAh cell: a gauge reset would bring back TI's 3000 mAh, and the wrong scale.
        self.assertEqual(gauge.design_capacity(), 750)

    def test_usb_power(self):
        self.assertTrue(reterminal_sticky.usb_power())  # the tests run over USB

    def test_power_off_sets_latch_again_on_usb(self):
        reterminal_sticky.power_off()  # USB keeps the board on through the clear
        self.assertEqual(Pin(Pin.board.PWR_HOLD).value(), 1)
        self.assertEqual(Pin(Pin.board.PWR_LOCK).value(), 1)
