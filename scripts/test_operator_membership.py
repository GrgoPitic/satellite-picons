#!/usr/bin/env python3
"""Regression checks for exact orbital/operator separation."""
import unittest

from operator_membership import build_operator_membership


class OperatorMembershipTests(unittest.TestCase):
    def setUp(self):
        self.channel = {
            "name": "RTVS 24 HD",
            "satellite_position": "23.5E",
            "frequency_mhz": 12012,
            "service_reference": "1:0:19:3C3E:C90:3:EB0000:0:0:0:",
        }
        self.snapshot = {"providers": {
            "skylink-sk": [{"name": "RTVS 24 HD", "position": "23.5E", "frequency_mhz": 12012, "fastscan": 21}],
            "skylink-cz": [{"name": "RTVS 24 HD", "position": "23.5E", "frequency_mhz": 12012, "fastscan": 56}],
        }}

    def test_same_reference_belongs_to_both_verified_operators(self):
        mapping = build_operator_membership([self.channel], self.snapshot)
        slots = mapping[self.channel["service_reference"].upper()]
        self.assertEqual([s["operator"] for s in slots], ["skylink-sk", "skylink-cz"])
        self.assertEqual([s["fastscan"] for s in slots], [21, 56])

    def test_different_frequency_never_matches(self):
        self.channel["frequency_mhz"] = 12040
        self.assertEqual(build_operator_membership([self.channel], self.snapshot), {})

    def test_same_name_wrong_orbit_never_matches(self):
        self.channel["satellite_position"] = "16E"
        self.assertEqual(build_operator_membership([self.channel], self.snapshot), {})

    def test_ambiguous_service_names_are_not_assigned(self):
        other = dict(self.channel, service_reference="1:0:19:3C3F:C90:3:EB0000:0:0:0:")
        self.assertEqual(build_operator_membership([self.channel, other], self.snapshot), {})

    def test_vhannibal_service_outside_skylink_is_not_operator_member(self):
        unrelated = dict(self.channel, name=":24", satellite_position="16E", frequency_mhz=11094)
        self.assertEqual(build_operator_membership([unrelated], self.snapshot), {})

    def test_logo_assignment_not_used_for_membership(self):
        unrelated = dict(self.channel, name=":24", satellite_position="16E", frequency_mhz=11094,
                         logo="assets/logos/stations/24.png")
        self.assertEqual(build_operator_membership([unrelated], self.snapshot), {})


if __name__ == "__main__":
    unittest.main()
