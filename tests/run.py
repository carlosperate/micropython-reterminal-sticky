# Runs every test_*.py in one folder with micropython-lib's unittest: tests/unix on the unix port
# (make test), tests/device on the board over mpremote mount (make test-device). Both run from the
# repository root, so the paths below are relative to it.
import os
import sys


# A lib/ folder with a manifest.py is a package root, as in micropython-lib.
def package_roots(path):
    roots = []
    for name, kind, *_ in os.ilistdir(path):
        if kind == 0x4000:
            roots += package_roots(path + "/" + name)
        elif name == "manifest.py":
            roots.append(path)
    return roots


sys.path[:0] = package_roots("lib") + [
    "boards/SEEED_RETERMINAL_STICKY/modules",
    "micropython/lib/micropython-lib/python-stdlib/unittest",
]
import unittest

folder = sys.argv[1] if len(sys.argv) > 1 else "tests/device"
sys.path.insert(0, folder)
try:
    names = sorted(os.listdir(folder))
except OSError:  # git keeps no empty folder
    names = []
failed = 0
for name in names:
    if name.startswith("test_") and name.endswith(".py"):
        result = unittest.main(name[:-3])
        failed += result.failuresNum + result.errorsNum
# Not sys.exit(): on the board it soft-resets under mpremote's mount, and mpremote then crashes.
if failed:
    raise AssertionError("%d tests failed" % failed)
