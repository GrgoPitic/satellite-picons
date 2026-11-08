#!/usr/bin/env python3
"""Offline tests for Skylink service-list parsing; external failures are not destructive."""
import unittest
from skylink_lineups import parse_listing


class SkylinkTests(unittest.TestCase):
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
