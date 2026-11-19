# Host: medians and worst cases per refresh kind and phase, in ms, from frame_time.py's CSV.
#   python3 tools/bench/stats.py cold.csv [warm.csv]
# Written for MicroPython too, so the unix port's tests can run it.
import sys

PHASES = ("draw_us", "spi_us", "rise_us", "wave_us", "off_us")


def parse(lines):
    """{kind: [row, ...]} from CSV lines; anything else in mpremote's output is skipped."""
    rows = {}
    for line in lines:
        fields = line.strip().split(",")
        if len(fields) != 2 + len(PHASES) or fields[0] == "kind":
            continue
        try:
            values = [int(f) for f in fields[1:]]
        except ValueError:
            continue
        row = dict(zip(PHASES, values[1:]))
        rows.setdefault(fields[0], []).append(row)
    return rows


def median(values):
    s = sorted(values)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2


def summary(rows):
    """{phase: (median_ms, worst_ms)}, with the total of all phases as "total"."""
    out = {}
    for phase in PHASES + ("total",):
        if phase == "total":
            values = [sum(r[p] for p in PHASES) for r in rows]
        else:
            values = [r[phase] for r in rows]
        out[phase] = (round(median(values) / 1000, 1), round(max(values) / 1000, 1))
    return out


def report(rows):
    phases = PHASES + ("total",)
    lines = ["%-12s %4s  " % ("kind", "n") + "  ".join("%13s" % p[:-3] for p in PHASES)]
    lines[0] += "  %13s" % "total"
    for kind, kind_rows in rows.items():
        stats = summary(kind_rows)
        cells = ["%6.1f /%6.1f" % stats[p] for p in phases]
        lines.append("%-12s %4d  " % (kind, len(kind_rows)) + "  ".join(cells))
    return "\n".join(lines)


if __name__ == "__main__":
    for path in sys.argv[1:]:
        with open(path) as f:
            print(path, "(median / worst, ms)")
            print(report(parse(f)))
