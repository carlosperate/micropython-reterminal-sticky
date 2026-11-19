# The bench's test card: a static frame around a disc, a pair of eyes and a counter, which change
# with each step as an animation's parts do. The research's ghosting card, in 1-bit.
import framebuf

DISC = (200, 240, 100)
EYES = (480, 640)
SCALE = 6


def buffer(width, height):
    buf = bytearray(width * height // 8)
    return buf, framebuf.FrameBuffer(buf, width, height, framebuf.MONO_HLSB)


def big_text(fb, text, x, y):
    small, fb_small = buffer(8 * len(text), 8)
    fb_small.fill(1)
    fb_small.text(text, 0, 0, 0)
    for gy in range(8):
        for gx in range(8 * len(text)):
            if not fb_small.pixel(gx, gy):
                fb.fill_rect(x + gx * SCALE, y + gy * SCALE, SCALE, SCALE, 0)


def draw(fb, width, height, step, disc=None):
    """The card for step: the disc filled on odd steps, the eyes shut, the counter at step.

    disc alone (True or False) draws only the disc, filled or not, on the static frame.
    """
    fb.fill(1)
    fb.rect(0, 0, width, height, 0)
    fb.text("bench", 16, 16, 0)
    x, y, r = DISC
    fb.ellipse(x, y, r, r, 0, step % 2 == 1 if disc is None else disc)
    if disc is not None:
        return
    for ex in EYES:
        if step % 2:
            fb.fill_rect(ex - 50, y - 5, 100, 10, 0)
        else:
            fb.ellipse(ex, y, 50, 50, 0, True)
    big_text(fb, "%04d" % step, 400, 380)


def grey_bands(width, height):
    """A GS2_HMSB frame of four bands, black to white."""
    buf = bytearray(width * height // 4)
    fb = framebuf.FrameBuffer(buf, width, height, framebuf.GS2_HMSB)
    for level in range(4):
        fb.fill_rect(level * width // 4, 0, width // 4, height, level)
    return buf
