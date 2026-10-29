import os
import unittest

import esp32


class TestFlash(unittest.TestCase):
    def test_running_app(self):
        app = esp32.Partition(esp32.Partition.RUNNING).info()
        self.assertEqual(app, (0, 0, 0x10000, 0x300000, "factory", False))

    # partitions.csv, repeated. The vfs ends at 16 MiB: filesystems above it break (#19766).
    def test_data_partitions(self):
        found = [p.info() for p in esp32.Partition.find(esp32.Partition.TYPE_DATA)]
        expected = [
            (1, 2, 0x9000, 0x6000, "nvs", False),
            (1, 1, 0xF000, 0x1000, "phy_init", False),
            (1, 0x81, 0x310000, 0xCF0000, "vfs", False),
        ]
        self.assertEqual(found, expected)

    def test_filesystem_fills_vfs(self):
        stat = os.statvfs("/")
        self.assertEqual((stat[0], stat[2]), (4096, 0xCF0000 // 4096))

    def test_write_read(self):
        path = "/test_flash.tmp"
        data = bytes(range(256)) * 16
        with open(path, "wb") as f:
            f.write(data)
        try:
            with open(path, "rb") as f:
                self.assertEqual(f.read(), data)
        finally:
            os.remove(path)
