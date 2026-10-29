# Runs after test_pins.py (the runner goes in name order): this powers the panel and drives its pins.
import unittest

import reterminal_sticky
from machine import mem32
from test_pins import PINS

# GPIO_FUNC0_OUT_SEL_CFG_REG and GPIO_FUNC0_IN_SEL_CFG_REG, then one word per GPIO or signal, and
# SPI2's signals (soc/esp32s3: register/soc/gpio_reg.h, include/soc/gpio_sig_map.h, IDF v5.5.2).
_OUT_SEL = 0x60004554
_IN_SEL = 0x60004154
_SIG_GPIO_OUT = 256
_FSPICLK_OUT = 101
_FSPIQ_IN = 102
_FSPID_OUT = 103


def out_signal(gpio):
    return mem32[_OUT_SEL + 4 * gpio] & 0x1FF


def in_gpio(signal):
    return mem32[_IN_SEL + 4 * signal] & 0x3F


class TestPanel(unittest.TestCase):
    def test_detect_agrees_with_itself(self):
        first = reterminal_sticky.detect()
        self.assertIn(first, (reterminal_sticky.SSD1677, reterminal_sticky.SSD2677))
        for _ in range(3):
            self.assertEqual(reterminal_sticky.detect(), first)

    def test_spi_after_detect(self):
        reterminal_sticky.spi()
        reterminal_sticky.detect()
        self.assertEqual(out_signal(PINS["SPI_SCK"]), _SIG_GPIO_OUT)
        self.assertEqual(out_signal(PINS["SPI_MOSI"]), _SIG_GPIO_OUT)
        reterminal_sticky.spi()
        self.assertEqual(out_signal(PINS["SPI_SCK"]), _FSPICLK_OUT)
        self.assertEqual(out_signal(PINS["SPI_MOSI"]), _FSPID_OUT)
        self.assertEqual(in_gpio(_FSPIQ_IN), PINS["SPI_MISO"])
