#!/usr/bin/env python3
"""Verify operator membership independently of the Vhannibal orbital catalogue.

Only unique (station name, orbital position, transponder frequency) matches
are treated as verified. Operator presence is never inferred from a
Vhannibal filename, importer provider_group, or matching logo.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import yaml

from catalog_common import normalize_station_key

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "skylink-lineups.json"
REGISTRY = ROOT / "operators.yml"


def active_operators() -> list[dict]:
    """Load enabled operator identities from the shared configuration."""
    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    return sorted((item for item in data.get("operators", []) if item.get("enabled")),
                  key=lambda x: (int(x.get("order", 999)), x["id"]))



def build_operator_membership(channels: list[dict], snapshot: dict) -> dict[str, list[dict]]:
    """Return verified operator slots keyed by full DVB service reference."""
    by_station = defaultdict(list)
    for channel in channels:
        ref = str(channel.get("service_reference") or "").upper()
        orbit = str(channel.get("satellite_position") or "")
        freq = channel.get("frequency_mhz")
        if not ref or not orbit or freq is None:
            continue
        key = (normalize_station_key(channel.get("name") or ""), orbit)
        by_station[key].append(channel)

    membership = defaultdict(list)
    providers = snapshot.get("providers") or {}
    for op in active_operators():
        operator_id = str(op["id"])
        source_id = str(op.get("source_id") or operator_id)
        if op.get("snapshot", "skylink-lineups.json") != "skylink-lineups.json":
            continue  # Other snapshots are loaded separately by the exporter.
        for slot in providers.get(source_id, []) or []:
            key = (normalize_station_key(slot.get("name") or ""), str(slot.get("position") or ""))
            candidates = by_station.get(key, [])
            # Duplicate station names on the orbit are ambiguous; refuse to guess.
            if len(candidates) != 1:
                continue
            candidate = candidates[0]
            if abs(int(candidate["frequency_mhz"]) - int(slot["frequency_mhz"])) > 2:
                continue
            ref = str(candidate["service_reference"]).upper()
            membership[ref].append({
                "operator": operator_id,
                "fastscan": slot.get("fastscan"),
                "listing_name": slot["name"],
                "position": slot["position"],
                "frequency_mhz": slot["frequency_mhz"],
            })
    return dict(membership)


def load_operator_membership(channels: list[dict]) -> dict[str, list[dict]]:
    if not SNAPSHOT.is_file():
        return {}
    try:
        snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return build_operator_membership(channels, snapshot)
