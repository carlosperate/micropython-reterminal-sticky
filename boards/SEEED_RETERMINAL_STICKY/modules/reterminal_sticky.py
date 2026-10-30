# Seeed reTerminal Sticky board helpers: the shared SPI bus, which display controller the panel
# has, and its driver; the battery's gauge, USB power and charging. Pins come from pins.csv
# through Pin.board. Functions that take pins import machine only when they fall back to the
# board's, so the unix tests can pass fakes.

import time
from micropython import const

SSD1677 = "SSD1677"
SSD2677 = "SSD2677"

_REV = const(0x70)
_SSD2677_REV = const(0x07)
# R46, ten times the sense resistor TI calibrates the gauge for (docs/hardware.md).
_SENSE_MOHM = const(100)


def spi(baudrate=10_000_000):
    """Return SPI(1), the bus the panel shares with the microSD card."""
    from machine import Pin, SPI

    b = Pin.board
    # The panel never shows an image unless the card is powered and deselected.
    b.SD_EN.init(Pin.OUT, value=1)
    b.SD_CS.init(Pin.OUT, value=1)
    # With MISO even for the panel alone: a bus without it takes GPIO12 from the card.
    bus = SPI(1, baudrate=baudrate, sck=b.SPI_SCK, mosi=b.SPI_MOSI, miso=b.SPI_MISO)
    # Pin.init() on a bus pin, as detect() does, detaches it, and SPI() with unchanged settings
    # returns without attaching it again.
    bus.deinit()
    bus.init(baudrate=baudrate)
    return bus


def _panel_pins():
    from machine import Pin

    b = Pin.board
    return b.EPD_EN, b.EPD_CS, b.EPD_DC, b.EPD_RST, b.SPI_SCK, b.SPI_MOSI, b.EPD_BUSY


# Pins are (en, cs, dc, rst, sck, sda, busy); sda is the bus's MOSI.
def _start(pins):
    pins = pins or _panel_pins()
    en, cs, dc, rst, sck, sda, busy = pins
    cs.init(cs.OUT, value=1)
    en.init(en.OUT, value=1)
    time.sleep_ms(50)
    busy.init(busy.IN, None)
    rst.init(rst.OUT, value=0)
    time.sleep_ms(20)
    rst(1)
    time.sleep_ms(10)
    return pins


def read_id(pins=None, n=3):
    """Reset the panel, send REV (0x70) and return n bytes read back on SDA."""
    ident = bytearray(n)
    en, cs, dc, rst, sck, sda, busy = _start(pins)
    sck.init(sck.OUT, value=0)
    sda.init(sda.OUT, None, value=0)
    dc.init(dc.OUT, value=0)
    # Released even on Ctrl-C, so the panel never stays selected on the card's bus.
    try:
        cs(0)
        for i in range(7, -1, -1):
            sda((_REV >> i) & 1)
            sck(1)
            sck(0)
        # The SSD2677 has no SDO pin: it answers on SDA. Python's pin calls are far slower than
        # its 400 ns read cycle.
        sda.init(sda.IN, sda.PULL_UP)
        dc(1)
        for j in range(n):
            for _ in range(8):
                ident[j] = ident[j] << 1 | sda()
                sck(1)
                sck(0)
    finally:
        cs(1)
        sda.init(sda.OUT, None, value=0)
    return bytes(ident)


def ready_level(pins=None):
    """Reset the panel and return the level BUSY settles at: 1 on the SSD2677, 0 on the SSD1677."""
    busy = _start(pins)[6]
    # As Seeed_GFX2 does: the first change, or the level that holds for 200 ms.
    level = busy()
    for _ in range(100):
        time.sleep_ms(2)
        if busy() != level:
            return 1 - level
    return level


def detect(pins=None):
    """Return SSD1677 or SSD2677. Call spi() afterwards: this takes SCK and MOSI off the bus."""
    rev = read_id(pins, 1)[0]
    if rev == _SSD2677_REV:
        return SSD2677
    # 0x00 or 0xFF: nothing drove SDA, which happens on some units.
    if rev not in (0x00, 0xFF):
        return SSD1677
    return SSD2677 if ready_level(pins) else SSD1677


def panel(baudrate=10_000_000):
    """Detect the controller and return its driver on spi(), initialised."""
    from machine import Pin

    controller = detect()
    # Before any raise: detect() took SCK and MOSI from the bus the SD card may be using.
    bus = spi(baudrate)
    if controller != SSD1677:
        raise NotImplementedError("no driver for the " + controller)
    import ssd1677

    b = Pin.board
    driver = ssd1677.SSD1677(bus, b.EPD_CS, b.EPD_DC, b.EPD_RST, b.EPD_BUSY)
    driver.init()
    return driver


def gauge(i2c=None):
    """Return the battery's BQ27220 gauge, scaled for the board's sense resistor.

    Pass your I2C(0) if you have one: constructing it again rebuilds the bus.
    """
    import bq27220

    if i2c is None:
        from machine import I2C

        i2c = I2C(0)
    return bq27220.BQ27220(i2c, sense_mohm=_SENSE_MOHM)


def usb_power(vbus=None):
    """True while USB powers the board."""
    if vbus is None:
        from machine import Pin

        vbus = Pin(Pin.board.VBUS_SENSE, Pin.IN)
    return vbus.value() == 1


def charging(stat=None, vbus=None):
    """True while on USB with the charger's STAT low.

    One read: on a fault STAT blinks at 1 Hz, so this can read either way then.
    """
    if stat is None:
        from machine import Pin

        stat = Pin(Pin.board.CHG_STAT, Pin.IN, Pin.PULL_UP)
    # STAT is open drain, low while charging.
    return usb_power(vbus) and stat.value() == 0
