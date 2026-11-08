#!/usr/bin/env python3
"""Safely link existing curated logos to new provider catalogue services.

No logos or service references are invented. Ambiguous station families and
services explicitly owned by another artwork are never reassigned.
"""
from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path

import yaml

from catalog_common import (
    ROOT,
    channel_identity,
    load_station_artwork,
    normalize_station_key,
    save_station_artwork,
)

PROVIDER_DATA_DIR = ROOT / "provider-data"


def family_key(name: str) -> str:
    key = normalize_station_key(name)
    while True:
        next_key = key
        for suffix in ("-cz", "-sk", "-hd", "-sd"):
            if next_key.endswith(suffix) and len(next_key) > len(suffix):
                next_key = next_key[: -len(suffix)]
                break
        if next_key == key:
            return key
        key = next_key


def assign_new_targets() -> dict:
    data = load_station_artwork()
    stations = data.get("stations") or {}
    family_owners = defaultdict(list)
    target_owner = {}

    for station_key, artwork in stations.items():
        if not isinstance(artwork, dict) or not artwork.get("logo"):
            continue
        if not (ROOT / str(artwork["logo"])).is_file():
            continue
        family_owners[family_key(station_key)].append(station_key)
        for identity in artwork.get("targets", []) or []:
            target_owner[str(identity)] = station_key

    added = defaultdict(int)
    ambiguous = set()
    catalogues = 0
    channels = 0

    for path in sorted(PROVIDER_DATA_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        provider_id = str(payload.get("provider") or path.stem).strip().lower()
        rows = payload.get("channels") or []
        if not rows:
            continue
        catalogues += 1

        for channel in rows:
            if not channel.get("service_reference"):
                continue
            channels += 1
            identity = channel_identity(channel, provider_id)
            key = str(channel.get("station_key") or normalize_station_key(channel.get("name", "")))
            matches = family_owners.get(family_key(key), [])
            if not matches:
                continue

            # An exact artwork key resolves otherwise ambiguous variants.
            if key in matches:
                selected = key
            elif len(matches) == 1:
                selected = matches[0]
            else:
                ambiguous.add(key)
                continue

            owner = target_owner.get(identity)
            if owner is not None and owner != selected:
                continue
            art = stations[selected]
            targets = {str(x) for x in art.get("targets", []) or []}
            if identity in targets:
                continue
            targets.add(identity)
            art["targets"] = sorted(targets)
            target_owner[identity] = selected
            added[selected] += 1

    if added:
        now = int(time.time())
        for key in added:
            stations[key]["updated_at"] = now
        save_station_artwork(data)

    result = {
        "catalogues": catalogues,
        "scanned_services": channels,
        "new_assignments": sum(added.values()),
        "stations_updated": dict(sorted(added.items())),
        "ambiguous_keys_skipped": sorted(ambiguous),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    assign_new_targets()
