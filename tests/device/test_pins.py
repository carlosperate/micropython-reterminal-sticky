# Checks the pin map and the state board_init.c leaves, so make test-device hard-resets first.
import unittest

from machine import Pin, mem32

# pins.csv, repeated so a wrong or missing name fails here.
PINS = {
    "I2C_SCL": 0,
    "I2C_SDA": 1,
    "TP_SCL": 2,
    "TP_SDA": 3,
    "BTN_POWER": 4,
    "BTN_UP": 5,
    "BTN_DOWN": 6,
    "IMU_INT": 7,
    "SD_CS": 8,
    "VBUS_SENSE": 9,
    "SD_EN": 10,
    "SD_DET": 11,
    "SPI_MISO": 12,
    "SPI_SCK": 13,
    "SPI_MOSI": 14,
    "EPD_CS": 15,
    "EPD_DC": 16,
    "EPD_RST": 17,
    "EPD_BUSY": 18,
    "MIC_CLK": 19,
    "MIC_DATA": 20,
    "TP_INT": 21,
    "MIC_EN": 38,
    "CHG_EN_N": 39,
    "CHG_STAT": 40,
    "TP_RST": 41,
    "TP_EN": 42,
    "PWR_HOLD": 45,
    "PWR_LOCK": 46,
    "EPD_EN": 47,
    "BUZZER": 48,
}

# The levels board_init.c drives; every other pin is left an input.
DRIVEN = {
    "SD_CS": 1,
    "SD_EN": 1,
    "MIC_EN": 0,
    "CHG_EN_N": 0,
    "TP_RST": 0,
    "TP_EN": 0,
    "PWR_HOLD": 1,
    "PWR_LOCK": 1,
    "EPD_EN": 0,
    "BUZZER": 0,
}

# IO_MUX_GPIO0_REG, then one word per GPIO; MCU_SEL is bits 12-14 and PIN_FUNC_GPIO is 1
# (components/soc/esp32s3/register/soc/io_mux_reg.h in ESP-IDF v5.5.2).
_IO_MUX_GPIO0 = 0x60009004
_PIN_FUNC_GPIO = 1


def io_mux_function(gpio):
    return (mem32[_IO_MUX_GPIO0 + 4 * gpio] >> 12) & 7


class TestPins(unittest.TestCase):
    def test_names(self):
        names = [name for name in dir(Pin.board) if not name.startswith("_")]
        self.assertEqual(sorted(names), sorted(PINS))
        for name, gpio in PINS.items():
            self.assertIs(getattr(Pin.board, name), Pin(gpio), name)
            self.assertIs(Pin(name), Pin(gpio), name)

    # GPIO39-42 start as JTAG pads, so check the IO_MUX routes each one to the GPIO matrix.
    def test_driven_pins(self):
        for name, level in DRIVEN.items():
            gpio = PINS[name]
            config = repr(Pin(gpio))
            self.assertTrue(config.startswith("Pin(%d, mode=Pin.OUT" % gpio), config)
            self.assertFalse("pull=" in config, config)
            self.assertEqual(Pin(gpio).value(), level, name)
            self.assertEqual(io_mux_function(gpio), _PIN_FUNC_GPIO, name)

    # Output disabled. Pin's repr says IN for any pad that isn't output or open drain, so this
    # doesn't show the input buffer is on; drivers set that up when they claim a pin.
    def test_other_pins_not_driven(self):
        for name, gpio in PINS.items():
            if name not in DRIVEN:
                config = repr(Pin(gpio))
                self.assertFalse(config.startswith("Pin(%d, mode=Pin.OUT" % gpio), config)
