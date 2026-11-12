#!/usr/bin/env python3
"""
Builds and tests the firmware on Linux, macOS or Windows.
Needs Python 3.8+ and Docker.

    python make.py submodules               # once, after cloning
    python make.py firmware                 # build/SEEED_RETERMINAL_STICKY/firmware.bin
    python make.py unix                     # build/unix/micropython
    python make.py test                     # tests/unix/ on the unix port
    python make.py test-device --port PORT  # tests/device/ on the board
    python make.py info --port PORT         # battery, charging and USB state
    python make.py packages                 # rewrite each lib/ package.json
    python make.py clean                    # delete the build output

PORT can be set in the environment instead of --port.

Builds run in Espressif's IDF image, so every machine gets the same toolchain.
Flashing and mpremote run on the host, as Docker on macOS can't reach USB devices.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

IDF_IMAGE = "espressif/idf:v5.5.2"

# The repository on the host, and inside the container.
ROOT = Path(__file__).resolve().parent
WORK = PurePosixPath("/work")

# Build folders, inside the container: the firmware's mpy-cross, and the unix port.
MPY_CROSS_BUILD = WORK / "build" / "mpy-cross"
UNIX_BUILD = WORK / "build" / "unix"

# x86-64 everywhere, emulated on Apple silicon: MicroPython has no arm64 native emitter for viper.
AMD64 = "--platform=linux/amd64"

# The image has no pkg-config to find libffi, and nothing here needs ffi.
NO_FFI = "MICROPY_PY_FFI=0"


# Helpers


def run(*command, **kwargs):
    """Print a command, then run it.

    A failure stops make.py.
    """
    command = [str(part) for part in command]
    # Flushed, or a log or CI shows it after the command's own output.
    print(" ".join(command), flush=True)
    subprocess.run(command, check=True, **kwargs)


def docker(*command, options=()):
    """Run a command in the IDF image, with the repository at /work.

    A fixed path, as Make breaks on spaces in paths and Linux can't use Windows ones.
    It runs as your user, or Linux leaves root's files in build/.
    """
    options = [
        *options,
        f"--volume={ROOT}:{WORK}",
        f"--workdir={WORK}",
        # Somewhere for the IDF's caches.
        "--env=HOME=/tmp",
        # Or git refuses a checkout owned by another user.
        "--env=GIT_CONFIG_COUNT=1",
        "--env=GIT_CONFIG_KEY_0=safe.directory",
        "--env=GIT_CONFIG_VALUE_0=*",
    ]
    # Windows has no user ids, and Docker there doesn't need one.
    if hasattr(os, "getuid"):
        options.append(f"--user={os.getuid()}:{os.getgid()}")
    run("docker", "run", "--rm", *options, IDF_IMAGE, *command)


def make_in(folder, *arguments, options=()):
    """Run make in a folder, in the IDF image."""
    docker("make", "-C", folder, *arguments, options=options)


def esp32(args, *arguments):
    """Run MicroPython's own esp32 Makefile, in micropython/ports/esp32, for --board.

    firmware() uses it to build, and submodules() to fetch what that build needs.
    """
    build = f"{args.board}-{args.variant}" if args.variant else args.board
    variables = [
        f"BOARD={args.board}",
        f"BOARD_VARIANT={args.variant}",
        f"BUILD={WORK / 'build' / build}",
    ]
    # A board in boards/ is ours; any other name is one of upstream's.
    if (ROOT / "boards" / args.board).is_dir():
        variables.append(f"BOARD_DIR={WORK / 'boards' / args.board}")
    make_in(WORK / "micropython" / "ports" / "esp32", *variables, *arguments)


def require_port(args):
    """Return the board's port, or stop if it's missing.

    mpremote on its own connects to the first device it finds.
    """
    if not args.port:
        sys.exit("Set --port (or PORT) to the board's serial port")
    return args.port


# Commands


def submodules(args):
    """Fetch MicroPython, then only the submodules the esp32 and unix ports need.

    Not --recursive: that would fetch every port's.
    """
    run("git", "-C", ROOT, "submodule", "update", "--init", ROOT / "micropython")
    esp32(args, "submodules")
    make_in(WORK / "micropython" / "ports" / "unix", NO_FFI, "submodules")


def firmware(args):
    """Build build/<BOARD>/firmware.bin."""
    mpy_cross(args)
    # Without MICROPY_MPYCROSS the build remakes mpy-cross itself, passing it BUILD=, and fails.
    esp32(args, f"MICROPY_MPYCROSS={MPY_CROSS_BUILD / 'mpy-cross'}")


def mpy_cross(args):
    """Build mpy-cross, for the firmware."""
    make_in(WORK / "micropython" / "mpy-cross", f"BUILD={MPY_CROSS_BUILD}")


def unix(args):
    """Build build/unix/micropython.

    It gets its own x86-64 mpy-cross: the firmware's is native.
    """
    mpy_cross_build = WORK / "build" / "unix-mpy-cross"
    make_in(WORK / "micropython" / "mpy-cross", f"BUILD={mpy_cross_build}", options=[AMD64])
    make_in(
        WORK / "micropython" / "ports" / "unix",
        NO_FFI,
        f"BUILD={UNIX_BUILD}",
        f"MICROPY_MPYCROSS={mpy_cross_build / 'mpy-cross'}",
        options=[AMD64],
    )


def test(args):
    """Run tests/unix/ on the unix port.

    It runs in Docker, as the binary is built for Linux.
    """
    unix(args)
    docker("python3", WORK / "tools" / "packages.py", "--check")
    docker(
        UNIX_BUILD / "micropython",
        WORK / "tests" / "run.py",
        WORK / "tests" / "unix",
        options=[AMD64],
    )


def test_device(args):
    """Run tests/device/ on the board.

    esptool resets it through EN first, so the pins start as board_init.c leaves them.
    machine.reset() would keep the GPIO setup of whatever ran before.
    """
    port = require_port(args)
    run("esptool", "--port", port, "chip-id", stdout=subprocess.DEVNULL)
    run("mpremote", "connect", port, "sleep", "2", "mount", ROOT, "run", ROOT / "tests" / "run.py")


def info(args):
    """Print the board's battery, charging and USB state, without a reset."""
    port = require_port(args)
    run("mpremote", "connect", port, "run", ROOT / "tools" / "info.py")


def packages(args):
    """Rewrite each lib/ package's package.json from its manifest.py."""
    docker("python3", WORK / "tools" / "packages.py")


def clean(args):
    """Delete build/."""
    build = ROOT / "build"
    if build.exists():
        shutil.rmtree(build)


COMMANDS = {
    "submodules": submodules,
    "firmware": firmware,
    "mpy-cross": mpy_cross,
    "unix": unix,
    "test": test,
    "test-device": test_device,
    "info": info,
    "packages": packages,
    "clean": clean,
}


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("command", nargs="?", default="firmware", choices=COMMANDS)
    parser.add_argument("--port", default=os.environ.get("PORT"), help="the board's serial port")
    parser.add_argument(
        "--board", default="SEEED_RETERMINAL_STICKY", help="in boards/, or upstream's"
    )
    parser.add_argument("--variant", default="", help="the board's variant, if any")
    args = parser.parse_args()
    try:
        COMMANDS[args.command](args)
    except subprocess.CalledProcessError as error:
        sys.exit(error.returncode)
    except OSError as error:
        # A missing tool (docker, git, esptool or mpremote), or a file clean can't delete.
        sys.exit(f"make.py: {error}")


if __name__ == "__main__":
    main()
