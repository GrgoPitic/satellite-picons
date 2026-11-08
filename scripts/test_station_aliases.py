#!/usr/bin/env python3
"""Safe cross-orbit logo sharing; preserve different channels and DVB refs."""
import unittest

from station_aliases import artwork_family, unique_family_artwork
from build_v2 import enrich_artwork


class ArtworkAliasTests(unittest.TestCase):
    def test_filmbox_love_crime_brand_aliases(self):
        canonical = artwork_family("FILMBOX+ Love and Crime")
        self.assertEqual(canonical, artwork_family("FILMBOX+ Love & Crime"))
        self.assertEqual(canonical, artwork_family("FILMBOX+ Love & Crime Adria"))
        self.assertEqual(canonical, artwork_family("FilmBox Love & Crime Adria"))

    def test_other_channels_never_share_brand(self):
        self.assertNotEqual(artwork_family("AMC"), artwork_family("AMC SK"))
        self.assertNotEqual(artwork_family(":24"), artwork_family("България 24"))
        self.assertNotEqual(artwork_family("FILMBOX+ Love & Crime"), artwork_family("FILMBOX+ one"))

    def test_unique_artwork_used_for_verified_16e_film_box(self):
        stations = {"filmbox-plus-love-and-crime": {
            "name": "FILMBOX+ Love and Crime",
            "logo": "assets/logos/stations/filmbox-plus-love-and-crime.png",
            "targets": ["sat:skylink-sk:3CF9_C95_3_EB0000"],
        }}
        row = {"id": "filmbox-16e", "name": "FILMBOX+ Love & Crime Adria",
               "provider_group": "skylink-sk", "delivery": "satellite",
               "service_reference": "1:0:19:A95:9DD0:16E:A00000:0:0:0:",
               "satellite_position": "16E"}
        enriched = enrich_artwork(row, stations)
        self.assertEqual(enriched["logo"], stations["filmbox-plus-love-and-crime"]["logo"])
        self.assertEqual(enriched["service_reference"], row["service_reference"])

    def test_ambiguous_artwork_is_not_autoselected(self):
        stations = {
            "filmbox-plus-love-and-crime": {"logo": "assets/logos/stations/a.png"},
            "filmbox-plus-love-crime-adria": {"logo": "assets/logos/stations/b.png"},
        }
        self.assertIsNone(unique_family_artwork("FILMBOX+ Love & Crime", stations))


if __name__ == "__main__":
    unittest.main()
