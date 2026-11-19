# The driver where only fakes can go: scripted BUSY, interrupted writes, cut resets, the reset
# pin's pulses, and other glasses' settings. The bytes it sends are in tests/common.
import unittest

import reterminal_sticky
import ssd1677
from fakes import SPI, Pin, script, word
from panel_log import INIT, POWER_OFF, frame, grey_frame, inverse, pattern
from sticky.display import Display


# Fixtures only: the test classes share them without running each other's tests.
class PanelCase(unittest.TestCase):
    def setUp(self):
        self.cs, self.dc, self.rst, self.busy = Pin(), Pin(), Pin(), Pin()
        self.spi = SPI(self.cs, self.dc)
        # Initialised, as reterminal_sticky.panel() returns it.
        self.panel = self.new_panel()
        self.panel.init()
        del self.spi.log[:]

    # The Sticky's glass, with any setting replaced.
    def new_panel(self, **settings):
        glass = dict(reterminal_sticky._GLASS)
        glass.update(settings)
        return ssd1677.SSD1677(self.spi, self.cs, self.dc, self.rst, self.busy, **glass)

    def log(self):
        return [(cmd, bytes(data)) for cmd, data in self.spi.log]

    def plane(self, cmd):
        return [data for c, data in self.log() if c == cmd][-1]

    # Each plane's writes, by size, from here on.
    def slice_sizes(self):
        sizes = []
        write = self.spi.write

        def recording(buf):
            if self.dc.level:
                sizes[-1][1].append(len(buf))
            else:
                sizes.append((buf[0], []))
            write(buf)

        self.spi.write = recording
        return sizes


class TestSSD1677(PanelCase):
    # A refresh turns the analog supply on, which power_off() and sleep() then turn off.
    def refreshed(self):
        self.panel.show(frame(1))
        del self.spi.log[:]

    def test_init_pulses_reset(self):
        resets = []
        self.rst.on_change = resets.append
        self.panel.init()
        self.assertEqual(resets, [0, 1])
        self.assertEqual(self.cs.level, 1)

    def test_interrupted_write_releases_cs(self):
        def interrupted(buf):
            raise KeyboardInterrupt

        for old in (None, frame(5)):
            self.spi.write = interrupted
            with self.assertRaises(KeyboardInterrupt):
                self.panel.show(frame(3), old)
            self.assertEqual(self.cs.level, 1)

    def test_show_waits_for_busy(self):
        self.busy.input = script([1] * 5 + [0])
        self.panel.show(frame(1))
        self.assertFalse(self.panel.busy())

    def test_busy_timeout(self):
        self.busy.input = script([1])
        self.panel.timeout_ms = 20
        with self.assertRaises(OSError):
            self.panel.show(frame(1))
        self.assertEqual(self.spi.log, [])

    # BUSY stays high in deep sleep; show() wakes the panel with init() first.
    def test_show_after_sleep(self):
        self.busy.input = script([0])
        self.panel.sleep()
        self.busy.input = script([1])
        self.assertFalse(self.panel.busy())
        self.panel.wait(0)
        del self.spi.log[:]
        self.busy.input = script([0])
        new = frame(7)
        self.panel.show(new)
        self.assertEqual(self.log()[: len(INIT)], INIT)
        self.assertEqual(self.log()[len(INIT) :][2], (0x24, new))

    # Cut short before the command is sent, the supply is still on: the next call sends it.
    def test_interrupted_power_off_retried(self):
        self.refreshed()
        write = self.spi.write

        def interrupted(buf):
            raise KeyboardInterrupt

        self.spi.write = interrupted
        with self.assertRaises(KeyboardInterrupt):
            self.panel.power_off()
        self.spi.write = write
        self.panel.power_off()
        self.assertEqual(self.spi.commands(), [0x3C, 0x22, 0x20])

    # Cut as 0x20 goes out, the supply may be on or off, and 0x22 03 with it off would hold BUSY:
    # power_off() resets instead, which turns it off either way.
    def test_cut_at_activate_resets(self):
        write = self.spi.write

        def cut(buf):
            write(buf)
            if not self.dc.level and buf[0] == 0x20:
                raise KeyboardInterrupt

        self.spi.write = cut
        with self.assertRaises(KeyboardInterrupt):
            self.panel.show(frame(1))
        self.spi.write = write
        del self.spi.log[:]
        resets = []
        self.rst.on_change = resets.append
        self.panel.power_off()
        self.assertEqual((resets, self.log()), ([0, 1], []))
        # The controller needs init() again, and the next refresh is full.
        self.panel.show(frame(3), frame(1))
        self.assertEqual(self.log()[: len(INIT)], INIT)
        self.assertEqual(self.plane(0x26), inverse(frame(3)))

    # Cut as power-off's 0x20 goes out, the supply may be off already: the next one resets.
    def test_cut_power_off_resets(self):
        self.refreshed()
        write = self.spi.write

        def cut(buf):
            write(buf)
            if not self.dc.level and buf[0] == 0x20:
                raise KeyboardInterrupt

        self.spi.write = cut
        with self.assertRaises(KeyboardInterrupt):
            self.panel.power_off()
        self.spi.write = write
        del self.spi.log[:]
        resets = []
        self.rst.on_change = resets.append
        self.panel.power_off()
        self.assertEqual((resets, self.log()), ([0, 1], []))

    # Cut inside a reset, the supply may be off already: power_off() resets again.
    def test_cut_reset_leaves_supply_unknown(self):
        self.panel.show(frame(1))

        def cut(level):
            if level:
                raise KeyboardInterrupt

        self.rst.on_change = cut
        with self.assertRaises(KeyboardInterrupt):
            self.panel.clean()
        resets = []
        self.rst.on_change = resets.append
        del self.spi.log[:]
        self.panel.power_off()
        self.assertEqual((resets, self.log()), ([0, 1], []))

    def test_sleep_after_stuck_power_off(self):
        self.refreshed()
        self.busy.input = script([0, 1])
        self.panel.sleep()
        self.assertEqual(self.spi.commands()[-1], 0x10)


class TestGrey(PanelCase):
    # Reset first: a second grey refresh without one swapped the middle greys on a unit.
    def test_resets_first(self):
        resets = []
        self.rst.on_change = resets.append
        self.panel.show_grey(pattern()[0])
        self.assertEqual(resets, [0, 1])
        self.assertEqual(self.cs.level, 1)

    # A reset cuts a running refresh short, so the wait comes first.
    def test_waits_before_reset(self):
        for call in (lambda: self.panel.show_grey(grey_frame()[0]), self.panel.clean):
            events = []
            levels = script([1, 1, 0])

            def busy():
                level = levels()
                events.append(("busy", level))
                return level

            self.busy.input = busy
            self.rst.on_change = lambda level: events.append(("reset", level))
            call()
            self.assertTrue(events.index(("reset", 0)) > events.index(("busy", 0)))

    def interrupt(self, call, *args):
        write = self.spi.write

        def interrupted(buf):
            raise KeyboardInterrupt

        self.spi.write = interrupted
        with self.assertRaises(KeyboardInterrupt):
            call(*args)
        self.spi.write = write
        self.assertEqual(self.cs.level, 1)

    def test_interrupted_grey_leaves_next_full(self):
        self.panel.show(frame(1))
        self.interrupt(self.panel.show_grey, grey_frame()[0])
        new = frame(3)
        del self.spi.log[:]
        self.panel.show(new, frame(1))
        self.assertEqual(self.plane(0x26), inverse(new))

    def test_interrupted_full_after_grey_leaves_next_full(self):
        self.panel.show_grey(grey_frame()[0])
        self.interrupt(self.panel.show, frame(3), frame(5))
        new = frame(3)
        del self.spi.log[:]
        self.panel.show(new, frame(5))
        self.assertEqual(self.plane(0x26), inverse(new))

    # A grey refresh that never starts changes nothing: the supply and the planes stay.
    def test_timeout_keeps_state(self):
        self.panel.show(frame(1))
        self.busy.input = script([1])
        self.panel.timeout_ms = 20
        del self.spi.log[:]
        with self.assertRaises(OSError):
            self.panel.show_grey(grey_frame()[0])
        self.assertEqual(self.spi.log, [])
        self.busy.input = script([0])
        self.panel.show(frame(3), frame(1))
        self.assertEqual(self.plane(0x26), frame(1))
        del self.spi.log[:]
        self.panel.power_off()
        self.assertEqual(self.spi.commands(), [0x3C, 0x22, 0x20])

    # A reset cut short (here at SWRESET) is done again before the next refresh of either kind.
    def test_cut_short_init_runs_again(self):
        for again in (
            lambda: self.panel.show(frame(1), frame(2)),
            lambda: self.panel.show_grey(grey_frame()[0]),
        ):
            self.interrupt(self.panel.show_grey, grey_frame()[0])
            del self.spi.log[:]
            self.panel.power_off()  # the reset turned the supply off
            self.assertEqual(self.spi.log, [])
            again()
            self.assertEqual(self.log()[: len(INIT)], INIT)

    def test_grey_after_sleep(self):
        self.panel.sleep()
        self.busy.input = script([1])
        self.assertFalse(self.panel.busy())
        self.busy.input = script([0])
        del self.spi.log[:]
        self.panel.show_grey(grey_frame()[0])
        self.assertEqual(self.log()[: len(INIT)], INIT)


# Built by hand and never initialised, onto a controller an earlier driver put in deep sleep.
class TestFirstRefresh(PanelCase):
    def setUp(self):
        super().setUp()
        self.panel = self.new_panel()

    # BUSY high until a reset.
    def asleep_until_reset(self):
        self.busy.input = script([1])

        def wake(level):
            if level:
                self.busy.input = script([0])

        self.rst.on_change = wake
        self.panel.timeout_ms = 20

    def test_busy_counts_from_the_first_reset(self):
        self.asleep_until_reset()
        self.assertFalse(self.panel.busy())
        self.panel.wait()
        self.panel.show(frame(1))
        self.busy.input = script([1])
        self.assertTrue(self.panel.busy())

    # Display waits before it shows: that wait mustn't time out before the driver's init().
    def test_display_on_a_controller_left_asleep(self):
        self.asleep_until_reset()
        display = Display(self.panel)
        display.show()
        self.assertEqual(self.log()[: len(INIT)], INIT)
        self.assertFalse(self.panel._powered)


GREY = reterminal_sticky._GLASS["grey"]


# Other glasses than the unit's: on the unit they would drive its panel with the wrong settings.
class TestSettings(PanelCase):
    def small(self, **settings):
        return self.new_panel(width=400, height=300, **settings)

    # The last value each command was sent with.
    def sent(self):
        return dict(self.log())

    def test_size(self):
        self.assertEqual((self.panel.width, self.panel.height), (800, 480))
        panel = self.small()
        self.assertEqual((panel.width, panel.height), (400, 300))
        panel.init()
        self.assertEqual(self.sent()[0x01], word(299) + b"\x02")

    # 50 bytes a row: 81 rows fit a transaction, and the last slice is short.
    def test_small_slices(self):
        panel = self.small()
        sizes = self.slice_sizes()
        panel.show(bytes(15000))
        self.assertEqual([n for cmd, n in sizes if cmd == 0x26], [[4050, 4050, 4050, 2850]])

    def test_frame_sizes(self):
        panel = self.small()
        for call in (
            lambda: panel.show(frame(1)),
            lambda: panel.show(bytes(15000), frame(1)),
            lambda: panel.show_grey(bytes(96000)),
        ):
            with self.assertRaises(ValueError):
                call()
        self.assertEqual(self.spi.log, [])

    # Rows are whole bytes, and neither side is empty.
    def test_size_checked(self):
        for width, height in ((404, 480), (0, 480), (800, 0)):
            with self.assertRaises(ValueError):
                self.new_panel(width=width, height=height)

    def test_row_wider_than_transaction(self):
        panel = self.new_panel(width=32768, height=1)
        sizes = self.slice_sizes()
        panel.show(bytes(4096))
        self.assertEqual([n for cmd, n in sizes if cmd == 0x26], [[4096]])

    def test_settings_required(self):
        with self.assertRaises(TypeError):
            ssd1677.SSD1677(self.spi, self.cs, self.dc, self.rst, self.busy, 800, 480)

    # Bits 0 and 1 count X and Y up; a direction counting down starts at the far end.
    def test_data_entry(self):
        for mode, x, y in (
            (0x00, (399, 0), (299, 0)),
            (0x01, (0, 399), (299, 0)),
            (0x02, (399, 0), (0, 299)),
            (0x03, (0, 399), (0, 299)),
        ):
            del self.spi.log[:]
            self.small(data_entry=mode).init()
            sent = self.sent()
            self.assertEqual(sent[0x11], bytes((mode,)))
            self.assertEqual(
                (sent[0x44], sent[0x45]), (word(x[0]) + word(x[1]), word(y[0]) + word(y[1]))
            )
            self.assertEqual((sent[0x4E], sent[0x4F]), (word(x[0]), word(y[0])))

    # Bit 2 addresses along Y first, and frames go row by row.
    def test_data_entry_by_rows(self):
        with self.assertRaises(ValueError):
            self.new_panel(data_entry=0x05)

    # 0x1C runs a waveform without turning the clock and analog supply on; 0x01 never turns it off.
    def test_updates_checked(self):
        for settings in (
            {"refresh": (0xC0, 0x1C)},
            {"clean": (0x01, 0x1C)},
            {"grey": (0x00, 0x1C) + GREY[2:]},
            {"power_off": (0x80, 0x01)},
        ):
            with self.assertRaises(ValueError):
                self.new_panel(**settings)

    # The supply is off after init(); 0xFC leaves it on, so each refresh needs a power-off.
    def test_refresh_leaving_supply_on(self):
        self.panel.power_off()
        self.assertEqual(self.spi.log, [])
        for old in (None, frame(1)):
            self.panel.show(frame(3), old)
            del self.spi.log[:]
            self.panel.power_off()
            self.assertEqual(self.log(), POWER_OFF)

    def test_refresh_turning_supply_off(self):
        panel = self.new_panel(refresh=(0xC0, 0xFF))
        panel.show(frame(1))
        del self.spi.log[:]
        panel.power_off()
        self.assertEqual(self.spi.log, [])

    def test_no_grey(self):
        panel = self.new_panel(grey=None)
        with self.assertRaises(NotImplementedError):
            panel.show_grey(grey_frame()[0])
        self.assertEqual(self.spi.log, [])

    # A frame all at one level gives that level's bits in each plane; swapped levels swap them.
    def test_levels(self):
        levels = GREY[3]
        swapped = (levels[1], levels[0]) + levels[2:]
        for levels in (levels, swapped):
            panel = self.new_panel(grey=GREY[:3] + (levels,))
            for level in range(4):
                del self.spi.log[:]
                panel.show_grey(bytes((0x55 * level,)) * 96000)
                high, low = levels[level]
                self.assertEqual(self.plane(0x24), bytes((0xFF * high,)) * 48000)
                self.assertEqual(self.plane(0x26), bytes((0xFF * low,)) * 48000)


if __name__ == "__main__":
    unittest.main()
