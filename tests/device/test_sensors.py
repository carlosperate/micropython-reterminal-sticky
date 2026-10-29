# Runs after test_pins.py (the runner goes in name order): I2C(0) leaves GPIO0/1 set up for I2C.
# Not I2C(1): the GT911 is unpowered, and a scan could feed it through its pins.
import unittest

from machine import I2C

SHT40 = 0x44
PCF8563 = 0x51
BQ27220 = 0x55
LSM6DS3TR_C = 0x6A


class TestSensorBus(unittest.TestCase):
    def test_scan(self):
        self.assertEqual(I2C(0).scan(), [SHT40, PCF8563, BQ27220, LSM6DS3TR_C])

    def test_imu_who_am_i(self):
        self.assertEqual(I2C(0).readfrom_mem(LSM6DS3TR_C, 0x0F, 1), b"\x6a")
