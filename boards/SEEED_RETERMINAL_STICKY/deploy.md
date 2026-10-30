Program your board using the esptool program, found [here](https://docs.espressif.com/projects/esptool/en/latest/{mcu}/).

The board has no BOOT button: the CH343P bridge resets it into the bootloader by itself. On Mac,
the port name is usually similar to `/dev/cu.usbmodem…` or `/dev/cu.usbserial-…`.

### Backing up

Back up the whole 32MiB flash before the first flash, and keep the file private. Erasing removes
the unit's own data (its Seeedash identity, saved settings and Wi-Fi credentials), which the
published stock firmware doesn't contain, so this backup is the only way to get it back:

```bash
esptool --port PORTNAME --baud 230400 read-flash 0 ALL sticky-backup.bin
esptool --port PORTNAME verify-flash 0 sticky-backup.bin
```

230400 baud takes about 20 minutes, but on macOS the CH343P loses data at 460800 and above with
Apple's driver. The file should be 33,554,432 bytes, with two halves that differ: identical halves
mean the read wrapped at 16MiB. Don't erase until `verify-flash` matches.

### Erasing

Erase the entire flash, so MicroPython finds a blank filesystem area:

```bash
esptool --port PORTNAME erase-flash
```

### Flashing

Then deploy the firmware to the board, starting at address {deploy_options[flash_offset]}:

```bash
esptool --port PORTNAME --baud 921600 write-flash {deploy_options[flash_offset]} SEEED_RETERMINAL_STICKY-DATE-VERSION.bin
```

### Restoring the stock firmware

Write the backup back:

```bash
esptool --port PORTNAME --baud 921600 write-flash 0 sticky-backup.bin
```

Without a backup, Seeed's [official firmware page](https://www.seeedstudio.com/sticky/playground/official-firmware/)
flashes the published stock image from desktop Chrome or Edge.

### Troubleshooting

If flashing starts and then fails partway through, try removing the `--baud 921600` option to
flash at the slower default speed. On macOS with Apple's driver the CH343P loses data at 460800
and above, so use `--baud 230400` there.
