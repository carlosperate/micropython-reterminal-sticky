# Runs every test_*.py in the folders given with micropython-lib's unittest: tests/unix and
# tests/common on the unix port (make.py test); tests/device then tests/common, the default, on
# the board over mpremote mount (make.py test-device). Both run from the repository root.
import os
import sys


# A lib/ folder with a manifest.py is a package root, as in micropython-lib.
def package_roots(path):
    roots = []
    # Listed whole: mpremote's mount keeps one listing open, so recursing mid-listing ends it.
    for name, kind, *_ in list(os.ilistdir(path)):
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

# Device first: test_pins.py checks the pins before any other test touches them.
folders = sys.argv[1:] or ["tests/device", "tests/common"]
# All on the path first, so a test in one can import helpers from another.
sys.path[:0] = folders
failed = 0
for folder in folders:
    try:
        names = sorted(os.listdir(folder))
    except OSError:  # git keeps no empty folder
        names = []
    # A module is imported once, so a test file's name is unique across the folders.
    for name in names:
        if name.startswith("test_") and name.endswith(".py"):
            result = unittest.main(name[:-3])
            failed += result.failuresNum + result.errorsNum
# Not sys.exit(): on the board it soft-resets under mpremote's mount, and mpremote then crashes.
if failed:
    raise AssertionError("%d tests failed" % failed)
