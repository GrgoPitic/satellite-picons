#!/usr/bin/env python3
"""Regression tests for Vhannibal service-name filtering."""
import unittest

from catalog_common import is_real_station_name


class StationNameTests(unittest.TestCase):
    def test_rejects_known_technical_entries(self):
        for value in (
            "", "  ", "•", "—", ".1.", ".2.", ".3.", ".4.",
            "10847V SID 0x75f4", "10936V SID 0x7828",
            "11097V SID 0x7573", "12363V SID 0x2391",
            "12363V SID 0x2392", "12363H SID 0xAAAA",
        ):
            with self.subTest(value=value):
                self.assertFalse(is_real_station_name(value))

    def test_preserves_real_station_names(self):
        for value in (
            "Cartoon Network", "AMC", "Cinemax", "1+1",
            "1+1 International SES", "123.live", "24Kitchen",
            "3sat", "TV 2", "7", "ČT 1 HD", "JOJ Šport",
        ):
            with self.subTest(value=value):
                self.assertTrue(is_real_station_name(value))


if __name__ == "__main__":
    unittest.main()
