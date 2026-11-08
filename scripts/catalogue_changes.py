#!/usr/bin/env python3
"""Persistent, conservative operator catalogue change history.

Compare saved catalogue snapshots only after a completed import. A missing or
unreachable provider is NOT a deletion. Store history so admin and public site
can show the same changes independently of GitHub Actions logs.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from catalog_common import ROOT, normalize_station_key, service_identity

REPORT = ROOT / "catalogue-changes.json"
LIMIT = 600


def catalogue(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    rows = payload.get("channels")
    if not isinstance(rows, list) or not rows:
        return None
    return payload


def snapshot(folder: Path) -> dict:
    return {
        file.stem: data
        for file in sorted(folder.glob("*.json"))
        if (data := catalogue(file)) is not None
    }


def identity(row: dict) -> str:
    return service_identity(row.get("service_reference", ""))


def station(row: dict) -> str:
    return str(row.get("station_key") or normalize_station_key(row.get("name", "")))


def label(row: dict) -> str:
    return str(row.get("name") or station(row))


def compare(provider: str, old: dict | None, new: dict) -> list[dict]:
    # The first successful import creates a baseline, not hundreds of
    # misleading "new" stations.
    if old is None:
        return [{"provider": provider, "kind": "catalogue_added",
                 "name": str(new.get("provider_name") or provider),
                 "count": len(new["channels"])}]

    prev = {identity(ch): ch for ch in old["channels"] if identity(ch)}
    curr = {identity(ch): ch for ch in new["channels"] if identity(ch)}
    removed = set(prev) - set(curr)
    added = set(curr) - set(prev)
    changes = []

    # A station can move to another transponder/service reference. Treat
    # it as a change of tuning only when old and new names match uniquely.
    old_by_key = {}
    new_by_key = {}
    for ref in removed:
        old_by_key.setdefault(station(prev[ref]), []).append(ref)
    for ref in added:
        new_by_key.setdefault(station(curr[ref]), []).append(ref)
    for key in old_by_key.keys() & new_by_key.keys():
        olds, news = old_by_key[key], new_by_key[key]
        if len(olds) == len(news) == 1:
            old_ref, new_ref = olds[0], news[0]
            changes.append({
                "provider": provider, "kind": "tuning_changed",
                "name": label(curr[new_ref]), "old_reference": prev[old_ref].get("service_reference"),
                "new_reference": curr[new_ref].get("service_reference"),
            })
            removed.discard(old_ref)
            added.discard(new_ref)

    for ref in sorted(prev.keys() & curr.keys()):
        before, after = prev[ref], curr[ref]
        if label(before) != label(after):
            changes.append({"provider": provider, "kind": "renamed",
                            "name": label(after), "old_name": label(before),
                            "reference": after.get("service_reference")})
        fields = ("frequency_mhz", "satellite_position", "fastscan", "tvg_id", "channel_uid")
        delta = {field: {"old": before.get(field), "new": after.get(field)}
                 for field in fields if before.get(field) != after.get(field)}
        if delta:
            changes.append({"provider": provider, "kind": "metadata_changed",
                            "name": label(after), "reference": after.get("service_reference"),
                            "details": delta})

    for ref in sorted(added):
        changes.append({"provider": provider, "kind": "added", "name": label(curr[ref]),
                        "reference": curr[ref].get("service_reference")})
    for ref in sorted(removed):
        changes.append({"provider": provider, "kind": "removed", "name": label(prev[ref]),
                        "reference": prev[ref].get("service_reference")})
    return changes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, default=ROOT / "provider-data")
    args = parser.parse_args()

    old, new = snapshot(args.before), snapshot(args.after)
    if REPORT.is_file():
        history = json.loads(REPORT.read_text(encoding="utf-8"))
    else:
        history = {"schema": 1, "events": []}

    configured = yaml.safe_load((ROOT / "providers.yml").read_text(encoding="utf-8")) or {}
    provider_names = {str(x["id"]): str(x.get("name") or x["id"])
                      for x in configured.get("providers", []) if x.get("id")}

    now = datetime.now(timezone.utc).isoformat()
    new_events = []
    # Missing after-sync catalogues are not removals. Failed syncs leave
    # their last known good catalogues intact.
    for provider, payload in new.items():
        for event in compare(provider, old.get(provider), payload):
            event["provider_name"] = provider_names.get(provider, provider)
            event["at"] = now
            new_events.append(event)

    if new_events:
        history["events"] = (new_events + history.get("events", []))[:LIMIT]
        history["last_change_at"] = now
        history["schema"] = 1
        REPORT.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"catalogues": len(new), "new_events": len(new_events),
                      "by_kind": {k: sum(x["kind"] == k for x in new_events)
                                  for k in sorted({x["kind"] for x in new_events})}},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
