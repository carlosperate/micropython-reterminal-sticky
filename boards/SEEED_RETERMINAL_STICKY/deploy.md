Program your board using the esptool program, found [here](https://docs.espressif.com/projects/esptool/en/latest/{mcu}/).

The board has no BOOT button: the CH343P bridge resets it into the bootloader by itself. On Mac,
the port name is usually similar to `/dev/cu.usbmodem…` or `/dev/cu.usbserial-…`.

### Backing up

Back up the whole 32MiB flash before the first flash, and keep the file private. Erasing removes
the unit's own data (its Seeedash identity, saved settings and Wi-Fi credentials), which the
published stock firmware doesn't contain, so this backup is the only way to get it back:

```bash
esptool --port PORTNAME --baud 921600 read-flash 0 ALL sticky-backup.bin
```

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
flash at the slower default speed.
