# MicroPython for the reTerminal Sticky

MicroPython firmware and libraries for the Seeed
[reTerminal Sticky](https://www.seeedstudio.com/sticky/docs/en/device-guide/hardware-overview/),
an ESP32-S3R8 device with a 3.97" 800×480 e-paper panel.

## Status

Not much yet: the board's basic firmware builds, no lib/modules created yet.

## Getting started

```sh
git clone https://github.com/carlosperate/micropython-reterminal-sticky.git
cd micropython-reterminal-sticky
pip install --group dev     # pip 25.1 or later
```

`make submodules` fetches MicroPython, and only the internal submodules the esp32 and unix ports
need. A recursive submodule init would fetch submodules for all the ports.

## Building

Builds run in Espressif's `espressif/idf:v5.5.2` Docker image, and go to `build/`:

```sh
make firmware     # build/SEEED_RETERMINAL_STICKY/firmware.bin
make unix         # build/unix/micropython, x86-64 for viper (emulated on Apple silicon)
```

Flashing runs on the host, as Docker on macOS can't easily access USB devices.

Back up the stock firmware first, as the erase removes the unit's own data
(its Seeedash identity, settings and Wi-Fi credentials), and only a backup brings it back.

Erase before the first flash, or MicroPython finds the stock data where its filesystem goes and
reports it as corrupted.

```sh
esptool --chip esp32s3 --port PORT --baud 921600 read-flash 0 ALL sticky-backup.bin
esptool --chip esp32s3 --port PORT erase-flash
esptool --chip esp32s3 --port PORT --baud 921600 write-flash 0 build/SEEED_RETERMINAL_STICKY/firmware.bin
# To go back to stock
esptool --chip esp32s3 --port PORT --baud 921600 write-flash 0 sticky-backup.bin
```

## Testing

Tests use micropython-lib's `unittest`:

```sh
make test                   # tests/unix/ on the unix port, in Docker
make test-device PORT=PORT  # tests/device/ on the board, running lib/ from this checkout
make info PORT=PORT         # battery, charging and USB state
make packages               # rewrite each lib/ package.json from its manifest.py
```

Checks, with the same tools and versions as MicroPython:

```sh
ruff check
ruff format --check
# Formats in place, so check git diff after. Always pass paths: with none, it
# reformats the whole MicroPython tree
micropython/tools/codeformat.py -c 'boards/**/*.[ch]'
# Commit messages: "path: Sentence." and a sign-off (git commit -s)
micropython/tools/verifygitlog.py -n1
```

## Troubleshooting

**esptool fails partway on macOS** with "Invalid head of packet", "Serial data stream stopped" or
"Corrupt data". With Apple's built-in driver, the board's WCH CH343P USB-serial chip loses data at
high baud rates, 460800 and 921600 failed, 230400 worked.

Use `--baud 230400`, or try WCH's [macOS driver](https://github.com/WCHSoftGroup/ch34xser_macos)
and its `/dev/cu.wchusbserial*` port.

## License

MIT, see [LICENSE](LICENSE).
