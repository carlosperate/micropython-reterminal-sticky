# MicroPython for the reTerminal Sticky

MicroPython firmware and libraries for the Seeed
[reTerminal Sticky](https://www.seeedstudio.com/sticky/docs/en/device-guide/hardware-overview/)
(ESP32-S3R8 and a 3.97" 800×480 e-paper panel), with a framework for creating animations on the panel.

## Status

Not much yet: the board's firmware builds, but hasn't run on a unit.

## Getting started

```sh
git clone https://github.com/carlosperate/micropython-reterminal-sticky.git
cd micropython-reterminal-sticky
make submodules
```

`make submodules` fetches MicroPython, and only the internal submodules the esp32 and unix ports
need. A recursive submodule init would fetch submodules for all the ports.

## Building

Builds run in Docker, in Espressif's `espressif/idf:v5.5.2` image, and go to `build/`:

```sh
make firmware     # build/SEEED_RETERMINAL_STICKY/firmware.bin
make unix         # build/unix/micropython, for host tests
make unix-amd64   # x86-64 unix port for viper code, emulated on Apple silicon
```

Set `BOARD` (and `BOARD_VARIANT`) to build one of upstream's boards, e.g.
`make firmware BOARD=ESP32_GENERIC_S3 BOARD_VARIANT=SPIRAM_OCT`.

Flashing runs on the host, as Docker on macOS can't reach USB devices. Back up the stock
firmware first, and keep the backup out of the repository: it holds the unit's NVS.

```sh
pip install --group dev  # pip 25.1 or later; esptool and mpremote, pinned in pyproject.toml
esptool --chip esp32s3 --port PORT read-flash 0 ALL ../sticky-backup.bin
esptool --chip esp32s3 --port PORT write-flash 0 build/SEEED_RETERMINAL_STICKY/firmware.bin
```

Checks, with the same tools and versions as MicroPython:

```sh
pip install --group dev  # pip 25.1 or later; versions pinned in pyproject.toml
ruff check
ruff format --check
# Always pass paths: with none, codeformat.py reformats the whole MicroPython tree
micropython/tools/codeformat.py -c 'boards/**/*.[ch]'
# Commit messages: "path: Sentence." and a sign-off (git commit -s)
micropython/tools/verifygitlog.py -n1
```

## License

MIT, see [LICENSE](LICENSE).
