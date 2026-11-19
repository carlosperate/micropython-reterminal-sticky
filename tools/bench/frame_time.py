# Board: times each phase of a refresh on the panel, as CSV for stats.py. Run it from the
# repository root with this folder mounted, as it imports card.py:
#   mpremote connect PORT mount tools/bench run tools/bench/frame_time.py
import time

import card
import reterminal_sticky

panel = reterminal_sticky.panel()
W, H = panel.width, panel.height
# A full refresh after every 10 partials, as Display does by default.
BURST = 10


def busy_after(level, limit_us):
    start = time.ticks_us()
    while panel.busy() != level and time.ticks_diff(time.ticks_us(), start) < limit_us:
        pass
    return time.ticks_diff(time.ticks_us(), start)


def timed(kind, i, draw_us, send):
    panel.wait()
    start = time.ticks_us()
    send()
    spi_us = time.ticks_diff(time.ticks_us(), start)
    # BUSY should rise within 20 ms of the trigger (the research's bound).
    rise_us = busy_after(True, 20_000)
    start = time.ticks_us()
    panel.wait()
    wave_us = time.ticks_diff(time.ticks_us(), start)
    start = time.ticks_us()
    panel.power_off()
    panel.wait()
    off_us = time.ticks_diff(time.ticks_us(), start)
    print("%s,%d,%d,%d,%d,%d,%d" % (kind, i, draw_us, spi_us, rise_us, wave_us, off_us))


def drawn(fb, step):
    start = time.ticks_us()
    card.draw(fb, W, H, step)
    return time.ticks_diff(time.ticks_us(), start)


def run(kind, count):
    a, fb_a = card.buffer(W, H)
    b, fb_b = card.buffer(W, H)
    if kind == "full":
        for i in range(count):
            timed(kind, i, drawn(fb_a, i), lambda: panel.show(a))
    elif kind in ("partial", "partial-all"):
        card.draw(fb_a, W, H, 0)
        if kind == "partial-all":
            # Every pixel changes at every step: the card and its inverse in turn.
            b[:] = bytes(x ^ 0xFF for x in a)
        panel.show(a)
        prev, cur, fb_cur = a, b, fb_b
        for i in range(count):
            draw_us = drawn(fb_cur, i + 1) if kind == "partial" else 0
            if i and i % BURST == 0:
                panel.wait()
                panel.show(prev)
            timed(kind, i, draw_us, lambda: panel.show(cur, prev))
            prev, cur = cur, prev
            fb_cur = fb_a if fb_cur is fb_b else fb_b
    elif kind == "grey":
        grey = card.grey_bands(W, H)
        for i in range(count):
            timed(kind, i, 0, lambda: panel.show_grey(grey))
    elif kind == "clean":
        for i in range(count):
            timed(kind, i, 0, lambda: panel.clean(i % 2 == 1))


print("kind,i,draw_us,spi_us,rise_us,wave_us,off_us")
for kind, count in (
    ("full", 30),
    ("partial", 30),
    ("partial-all", 30),
    ("grey", 10),
    ("clean", 10),
):
    run(kind, count)
a, fb_a = card.buffer(W, H)
card.draw(fb_a, W, H, 0)
panel.show(a)
panel.sleep()
