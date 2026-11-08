#!/usr/bin/env python3
"""Offline tests for Skylink service-list parsing; external failures are not destructive."""
import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import skylink_lineups
from skylink_lineups import parse_listing, build


class SkylinkTests(unittest.TestCase):
    def test_canal_action_fastscan_7_selects_correct_transponder(self):
        # Same service name appears on two transponders in Vhannibal.
        # The verified 11973 MHz feed has SID 14134 = 3736 (hex).
        right = "1:0:19:3736:C8E:3:EB0000:0:0:0:"
        wrong = "1:0:19:101C:451:35:C00000:0:0:0:"
        slot = {"name": "CANAL+ Action", "position": "23.5E",
                "frequency_mhz": 11973, "fastscan": 7}
        rows = [
            {"name": "CANAL+ Action", "satellite_position": "23.5E",
             "frequency_mhz": 11739, "service_reference": wrong},
            {"name": "CANAL+ Action", "satellite_position": "23.5E",
             "frequency_mhz": 11973, "service_reference": right},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "public" / "picons").mkdir(parents=True)
            (root / "operators.yml").write_text(
                "operators:\\n  - id: skylink-sk\\n    name: Skylink SK\\n    enabled: true\\n"
                "    order: 1\\n    source_type: fastscan\\n"
                "    snapshot: skylink-lineups.json\\n", encoding="utf-8")
            with patch.object(skylink_lineups, "ROOT", root), \\
                 patch.object(skylink_lineups, "SNAPSHOT", root / "skylink-lineups.json"), \\
                 patch.object(skylink_lineups, "REGISTRY", root / "operators.yml"):
                result = build(
                    {"channels": [{"service_reference": right, "files": []}]},
                    rows, {"providers": {"skylink-sk": [slot]}}
                )
        found = result["providers"][0]["channels"][0]
        self.assertEqual(found["status"], "missing_logo")
        self.assertEqual(found["service_reference"], right)

    def test_same_name_same_frequency_stays_ambiguous(self):
        ref1 = "1:0:19:3736:C8E:3:EB0000:0:0:0:"
        ref2 = "1:0:19:3737:C8E:3:EB0000:0:0:0:"
        slot = {"name": "CANAL+ Action", "position": "23.5E",
                "frequency_mhz": 11973, "fastscan": 7}
        rows = [{"name": "CANAL+ Action", "satellite_position": "23.5E",
                 "frequency_mhz": 11973, "service_reference": ref}
                for ref in (ref1, ref2)]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "public").mkdir()
            (root / "operators.yml").write_text(
                "operators:\\n  - id: skylink-sk\\n    name: Skylink SK\\n"
                "    enabled: true\\n    order: 1\\n    source_type: fastscan\\n"
                "    snapshot: skylink-lineups.json\\n", encoding="utf-8")
            with patch.object(skylink_lineups, "ROOT", root), \\
                 patch.object(skylink_lineups, "SNAPSHOT", root / "skylink-lineups.json"), \\
                 patch.object(skylink_lineups, "REGISTRY", root / "operators.yml"):
                result = build({"channels": []}, rows,
                               {"providers": {"skylink-sk": [slot]}})
        self.assertEqual(result["providers"][0]["channels"][0]["status"], "ambiguous")

    def test_listing_parsing_does_not_invent_service_reference(self):
        html = '''
        <table><tr><th>Logo</th><th>Parametre</th></tr>
          <tr><td></td><td>
            <a href="/frekvencie/skylink-sk/program/cartoon-network/">Cartoon Network</a>
            (TV/MPEG-4)<p>Frekvencia: 11934 MHz</p>
            <p>Družica: 23,5°E</p><p>FastScan: 42</p>
          </td></tr>
          <tr><td></td><td>
            <a href="/frekvencie/skylink-sk/program/amc/">AMC</a>
            (TV/MPEG-4)<p>Frekvencia: 11973 MHz</p>
            <p>Družica: 23,5°E</p><p>FastScan: 43</p>
          </td></tr>
          <tr><td>Unexpected formatting</td><td>FastScan: 99</td></tr>
        </table>
        '''
        parsed = parse_listing(html, "skylink-sk")
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0], {
            "name": "Cartoon Network", "position": "23.5E",
            "frequency_mhz": 11934, "fastscan": 42,
        })
        self.assertNotIn("service_reference", parsed[0])


if __name__ == "__main__":
    unittest.main()
