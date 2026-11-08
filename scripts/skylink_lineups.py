#!/usr/bin/env python3
"""Import independent Skylink SK/CZ FastScan listings and generate a safe picon API.

External listings indicate membership, never DVB identities. Only an exact,
unique (Unicode-normalized name, orbital position) match to Vhannibal is allowed
to supply a service reference. Unresolved entries cannot receive a picon.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import requests
import yaml
from bs4 import BeautifulSoup
from catalog_common import normalize_station_key

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "skylink-lineups.json"
REGISTRY = ROOT / "operators.yml"
URLS = {
    "skylink-sk": "https://www.satelitnatv.sk/frekvencie/skylink-sk/",
    "skylink-cz": "https://www.satelitnatv.sk/frekvencie/skylink-cz/",
}
POSITION = re.compile(r"(\d{1,2})[,.](\d)\s*°?\s*([EW])", re.I)
FREQUENCY = re.compile(r"Frekvencia:\s*(\d{5})\s*MHz", re.I)
FASTSCAN = re.compile(r"FastScan:\s*(\d+)", re.I)


def parse_listing(html: str, provider: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    found = []
    for tr in soup.select("tr"):
        label = tr.get_text(" ", strip=True)
        fastscan = FASTSCAN.search(label)
        freq = FREQUENCY.search(label)
        pos = POSITION.search(label)
        if not (fastscan and freq and pos):
            continue
        # Station's detail link, not an image alt, transponder or orbit link.
        choices = [a.get_text(" ", strip=True) for a in tr.select('a[href*="/program/"]')]
        choices = [v for v in choices if v]
        if len(set(choices)) != 1:
            continue
        name = choices[0]
        position = f"{int(pos.group(1))}.{pos.group(2)}{pos.group(3).upper()}"
        found.append({
            "name": name,
            "position": position,
            "frequency_mhz": int(freq.group(1)),
            "fastscan": int(fastscan.group(1)),
        })
    # Preserve each FastScan slot; two slots for the same service are meaningful.
    unique = {(r["fastscan"], r["name"], r["position"]): r for r in found}
    return sorted(unique.values(), key=lambda row: (row["fastscan"], row["name"]))


def sync(timeout: int = 20) -> dict:
    snapshot = {"schema": 1, "sources": URLS, "providers": {}}
    for provider, url in URLS.items():
        response = requests.get(url, timeout=(8, timeout), headers={"User-Agent": "PiconHub/1.0 (metadata verification)"})
        response.raise_for_status()
        entries = parse_listing(response.text, provider)
        if len(entries) < 50:
            raise ValueError(f"{provider}: found only {len(entries)} FastScan entries; preserving existing snapshot")
        snapshot["providers"][provider] = entries
    # Do not replace a previous valid snapshot if either source failed.
    output = json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"
    if not SNAPSHOT.exists() or SNAPSHOT.read_text(encoding="utf-8") != output:
        SNAPSHOT.write_text(output, encoding="utf-8")
    return snapshot


def build(index: dict, source_rows: list[dict], snapshot: dict) -> dict:
    """Create distinct provider packs while keeping orbital packs unchanged."""
    public = ROOT / "public"
    ready_by_ref = {
        str(ch.get("service_reference") or "").upper(): ch
        for ch in index.get("channels", [])
    }
    by_name = {}
    for ch in source_rows:
        if not ch.get("service_reference") or not ch.get("satellite_position"):
            continue
        key = (normalize_station_key(ch.get("name", "")), str(ch["satellite_position"]))
        by_name.setdefault(key, []).append(ch)

    import zipfile
    config = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    operators = sorted(
        (op for op in config.get("operators", []) if op.get("enabled", False)),
        key=lambda op: (int(op.get("order", 999)), op["id"]),
    )
    ids = [str(op["id"]) for op in operators]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate operator ids in operators.yml")
    result = {
        "schema": 2,
        "source": "Verified operator lineups + Vhannibal DVB references",
        "providers": [],
    }
    for op in operators:
        ident, display = str(op["id"]), str(op["name"])
        if op.get("source_type") != "fastscan":
            raise ValueError(f"{ident}: unsupported operator source_type")
        source_file = ROOT / str(op.get("snapshot") or "")
        if source_file != SNAPSHOT:
            if not source_file.is_file():
                raise FileNotFoundError(f"{ident}: missing operator lineup {source_file}")
            source_data = json.loads(source_file.read_text(encoding="utf-8"))
        else:
            source_data = snapshot
        source_id = str(op.get("source_id") or ident)
        catalogue = source_data.get("providers", {}).get(source_id, [])
        entries = []
        package_files = set()
        for station in catalogue:
            matches = by_name.get((normalize_station_key(station["name"]), station["position"]), [])
            # Vhannibal may contain several feeds with the same display name
            # on one orbit. Resolve the transponder BEFORE checking uniqueness.
            # Do not attach artwork to an unverified or different frequency.
            verified = [
                row for row in matches
                if row.get("frequency_mhz") is not None
                and abs(int(row["frequency_mhz"]) - int(station["frequency_mhz"])) <= 2
            ]
            if len(verified) == 1:
                ch = verified[0]
                status = "missing_logo"
            else:
                ch = None
                if len(verified) > 1:
                    status = "ambiguous"
                elif not matches:
                    status = "unresolved"
                elif all(row.get("frequency_mhz") is None for row in matches):
                    status = "unverified_frequency"
                else:
                    status = "frequency_mismatch"
            published = ready_by_ref.get(str(ch.get("service_reference") or "").upper()) if ch else None
            files = published.get("files", []) if published else []
            if files:
                status = "ready"
                package_files.update(files)
            entries.append({
                **station,
                "status": status,
                "service_reference": ch.get("service_reference") if ch else None,
                "files": files,
            })
        package = None
        if package_files:
            package = f"packages/{ident}-curated.zip"
            with zipfile.ZipFile(public / package, "w", compression=zipfile.ZIP_DEFLATED,
                                 compresslevel=9) as archive:
                for filename in sorted(package_files):
                    picon = public / "picons" / filename
                    if not picon.is_file():
                        raise FileNotFoundError(picon)
                    archive.write(picon, arcname=filename)
        result["providers"].append({
            "id": ident,
            "name": display,
            "description": "Skylink FastScan; nezameniteľné SK/CZ poradie. Picon len pri jednoznačnej DVB zhode.",
            "positions": sorted({entry["position"] for entry in entries}),
            "channel_count": len(entries),
            "curated_channel_count": sum(e["status"] == "ready" for e in entries),
            "matched_channel_count": sum(e["service_reference"] is not None for e in entries),
            "package": package,
            "source_url": op.get("source_url"),
            "source_type": "fastscan",
            "complete": bool(entries) and all(e["status"] == "ready" for e in entries),
            "channels": entries,
        })
    (public / "operators.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    # Backwards compatibility while older clients use skylink.json.
    (public / "skylink.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for item in result["providers"]:
        unresolved = sum(entry["status"] != "ready" for entry in item["channels"])
        print(f'Operator {item["name"]}: {item["channel_count"]} FastScan entries, '
              f'{item["matched_channel_count"]} verified DVB services, '
              f'{item["curated_channel_count"]} ready picons, {unresolved} not ready')
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sync", action="store_true")
    args = parser.parse_args()
    if args.sync:
        result = sync()
        print("Skylink lineup snapshot:", {k: len(v) for k, v in result["providers"].items()})
