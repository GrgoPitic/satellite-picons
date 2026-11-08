#!/usr/bin/env python3
"""Tests: pending logos from older commits must all publish, without overwrites."""
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path

import yaml
from publish_artwork_sync import sync_curated_artwork


class PublishArtworkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.src, self.dst = base / "feature", base / "main"
        self.src.mkdir()
        self.dst.mkdir()
        self.local = {
            "old-logo": {
                "name": "TV JOJ HD", "logo": "assets/logos/stations/tv-joj.png",
                "source_logo": "assets/source-logos/stations/tv-joj.svg",
                "targets": ["sat:skylink-sk:3398_C9D_3_EB0000"], "updated_at": 20,
            },
            "new-logo": {
                "name": "Other HD", "logo": "assets/logos/stations/other.png",
                "targets": ["sat:skylink-sk:123_456_3_EB0000"], "updated_at": 30,
            },
        }
        for path, content in [
            ("assets/logos/stations/tv-joj.png", b"NEW JOJ"),
            ("assets/source-logos/stations/tv-joj.svg", b"<svg/>"),
            ("assets/logos/stations/other.png", b"NEW OTHER"),
        ]:
            f = self.src / path
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(content)
        self.save(self.src, self.local)
        self.save(self.dst, {"existing": {
            "name": "Already published", "logo": "assets/logos/stations/existing.png",
            "targets": ["sat:skylink-sk:ABC_DEF_3_EB0000"], "updated_at": 8,
        }})

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def save(root, stations):
        (root / "station-artwork.yml").write_text(
            yaml.safe_dump({"schema": 1, "stations": stations}, sort_keys=False),
            encoding="utf-8",
        )

    def published(self):
        return yaml.safe_load((self.dst / "station-artwork.yml").read_text())["stations"]

    def test_all_logos_from_old_and_new_commits_are_published(self):
        paths = sync_curated_artwork(self.src, self.dst)
        self.assertIn("station-artwork.yml", paths)
        self.assertIn("assets/logos/stations/tv-joj.png", paths)
        self.assertIn("assets/logos/stations/other.png", paths)
        self.assertEqual((self.dst / "assets/logos/stations/tv-joj.png").read_bytes(), b"NEW JOJ")
        self.assertEqual(set(self.published()), {"existing", "old-logo", "new-logo"})
        self.assertEqual(sync_curated_artwork(self.src, self.dst), [])

    def test_newer_production_artwork_is_preserved(self):
        main = {"old-logo": {
            **self.local["old-logo"], "updated_at": 50, "name": "Newer production logo"
        }}
        self.save(self.dst, main)
        self.assertIn("station-artwork.yml", sync_curated_artwork(self.src, self.dst))
        self.assertEqual(self.published()["old-logo"]["name"], "Newer production logo")

    def test_same_timestamp_conflict_is_rejected_without_side_effects(self):
        self.save(self.dst, {"new-logo": {
            **self.local["new-logo"], "name": "Different", "updated_at": 30,
        }})
        before = (self.dst / "station-artwork.yml").read_bytes()
        with self.assertRaisesRegex(ValueError, "same timestamp"):
            sync_curated_artwork(self.src, self.dst)
        self.assertEqual((self.dst / "station-artwork.yml").read_bytes(), before)

    def test_missing_file_rejected_before_changes(self):
        (self.src / "assets/logos/stations/other.png").unlink()
        with self.assertRaises(FileNotFoundError):
            sync_curated_artwork(self.src, self.dst)
        self.assertEqual(set(self.published()), {"existing"})

    def test_existing_targets_are_retained(self):
        main = {"old-logo": {
            **self.local["old-logo"], "updated_at": 10,
            "targets": ["sat:skylink-sk:OTHER_1_3_EB0000"],
        }}
        self.save(self.dst, main)
        sync_curated_artwork(self.src, self.dst)
        self.assertEqual(len(self.published()["old-logo"]["targets"]), 2)


if __name__ == "__main__":
    unittest.main()
