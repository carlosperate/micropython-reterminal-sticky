import sys
import unittest

sys.path.insert(0, "tools/bench")
import stats  # noqa: E402

OUTPUT = [
    "Local directory tools/bench is mounted at /remote",
    "kind,i,draw_us,spi_us,rise_us,wave_us,off_us",
    "full,0,1000,93000,10,477000,139000",
    "full,1,1000,95000,20,479000,141000",
    "full,2,3000,94000,30,478000,140000",
    "grey,0,0,163000,5,1700000,0",
    "",
    "not,a,row,1,2,3,4",
]


class TestStats(unittest.TestCase):
    def test_parse_skips_other_output(self):
        rows = stats.parse(OUTPUT)
        self.assertEqual(sorted(rows), ["full", "grey"])
        self.assertEqual(len(rows["full"]), 3)
        self.assertEqual(rows["grey"][0]["wave_us"], 1700000)

    def test_median(self):
        self.assertEqual(stats.median([3, 1, 2]), 2)
        self.assertEqual(stats.median([4, 1, 3, 2]), 2.5)

    def test_summary_in_ms(self):
        summary = stats.summary(stats.parse(OUTPUT)["full"])
        self.assertEqual(summary["spi_us"], (94.0, 95.0))
        self.assertEqual(summary["wave_us"], (478.0, 479.0))
        # Each row's phases add up first: 710.0, 716.0 and 715.0 ms.
        self.assertEqual(summary["total"], (715.0, 716.0))

    def test_report_names_each_kind(self):
        text = stats.report(stats.parse(OUTPUT))
        self.assertTrue(text.startswith("kind"))
        self.assertIn("full            3", text)
        self.assertIn("grey            1", text)


if __name__ == "__main__":
    unittest.main()
