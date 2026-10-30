# TI BQ27220 fuel gauge, read only: it never writes the gauge, so it can't upset a profile the
# board's maker programmed. TI calibrates the gauge for a 10 mΩ sense resistor; pass the board's
# as sense_mohm and currents and capacities are scaled to match.

from micropython import const

_VOLTAGE = const(0x08)
_CURRENT = const(0x0C)
_REMAINING_CAPACITY = const(0x10)
_FULL_CHARGE_CAPACITY = const(0x12)
_AVERAGE_CURRENT = const(0x14)
_TIME_TO_EMPTY = const(0x16)
_STATE_OF_CHARGE = const(0x2C)
_DESIGN_CAPACITY = const(0x3C)
_NOT_DISCHARGING = const(0xFFFF)


class BQ27220:
    def __init__(self, i2c, addr=0x55, sense_mohm=10):
        self.i2c = i2c
        self.addr = addr
        self._scale = 10 / sense_mohm

    def _read(self, command):
        # No shared buffer: a timer callback reading the gauge could refill it mid-decode.
        return int.from_bytes(self.i2c.readfrom_mem(self.addr, command, 2), "little")

    def _ma(self, command):
        value = self._read(command)
        return (value - 0x10000 if value & 0x8000 else value) * self._scale

    def _mah(self, command):
        return round(self._read(command) * self._scale)

    def voltage(self):
        """Battery voltage, mV."""
        return self._read(_VOLTAGE)

    def current(self):
        """Current over the last second, mA: positive charging, negative discharging."""
        return self._ma(_CURRENT)

    def average_current(self):
        """Current filtered by the gauge, mA."""
        return self._ma(_AVERAGE_CURRENT)

    def charge(self):
        """State of charge, %."""
        return self._read(_STATE_OF_CHARGE)

    def remaining_capacity(self):
        """mAh."""
        return self._mah(_REMAINING_CAPACITY)

    def full_charge_capacity(self):
        """mAh."""
        return self._mah(_FULL_CHARGE_CAPACITY)

    def design_capacity(self):
        """mAh."""
        return self._mah(_DESIGN_CAPACITY)

    def time_to_empty(self):
        """Minutes at the average current, or None while not discharging."""
        minutes = self._read(_TIME_TO_EMPTY)
        return None if minutes == _NOT_DISCHARGING else minutes
