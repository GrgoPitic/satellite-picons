#!/usr/bin/env python3
"""Zero-dependency OpenPLi updater for Satellite Picons.

Examples:
  python3 update_picons.py
  python3 update_picons.py /media/hdd/picon
  python3 update_picons.py /media/hdd/picon skylink
  python3 update_picons.py --list
  python3 update_picons.py --provider skylink --dest /media/hdd/picon
"""
from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import urllib.request
import zipfile

BASE_URL = "https://grgopitic.github.io/satellite-picons"
DEFAULT_DEST = "/media/hdd/picon"


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "SatellitePicons-Enigma2/1.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read()


def load_json(name: str) -> dict:
    return json.loads(get(BASE_URL.rstrip("/") + "/" + name).decode("utf-8"))


def list_providers(catalog: dict) -> int:
    providers = catalog.get("providers", [])
    if not providers:
        print("No provider packages available.")
        return 0

    print("Provider packages:")
    for provider in providers:
        state = "available" if provider.get("available") else "preparing"
        channels = int(provider.get("channel_count", 0))
        picons = int(provider.get("picon_count", 0))
        print(
            "  {id:<14} {name:<22} {state:<10} {channels:>3} channels / {picons:>3} picons".format(
                id=provider.get("id", ""),
                name=provider.get("name", ""),
                state=state,
                channels=channels,
                picons=picons,
            )
        )
    return 0


def select_provider(catalog: dict, provider_id: str) -> dict:
    wanted = provider_id.strip().lower()
    for provider in catalog.get("providers", []):
        if str(provider.get("id", "")).lower() == wanted:
            if not provider.get("available") or not provider.get("package"):
                raise SystemExit("Provider package is not available yet: " + provider_id)
            return provider
    raise SystemExit("Unknown provider: " + provider_id)


def install_package(package: str, dest: str) -> int:
    blob = get(BASE_URL.rstrip("/") + "/" + package)
    os.makedirs(dest, exist_ok=True)

    installed = 0
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        for info in archive.infolist():
            if info.is_dir() or not info.filename.lower().endswith(".png"):
                continue

            name = os.path.basename(info.filename)
            if not name:
                continue

            with archive.open(info) as src, open(os.path.join(dest, name), "wb") as dst:
                shutil.copyfileobj(src, dst)
            installed += 1

    return installed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Satellite Picons updater for Enigma2/OpenPLi")
    parser.add_argument("legacy_dest", nargs="?", help="Destination picon directory")
    parser.add_argument("legacy_provider", nargs="?", help="Provider id, e.g. skylink")
    parser.add_argument("--dest", help="Destination picon directory")
    parser.add_argument("--provider", help="Download only one provider package")
    parser.add_argument("--list", action="store_true", help="List provider packages")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dest = args.dest or args.legacy_dest or DEFAULT_DEST
    provider_id = args.provider or args.legacy_provider or ""

    version = load_json("version.json")
    catalog_name = version.get("providers", "providers.json")
    catalog = load_json(catalog_name)

    if args.list:
        return list_providers(catalog)

    package = version["package"]
    label = "all providers"

    if provider_id:
        provider = select_provider(catalog, provider_id)
        package = provider["package"]
        label = provider.get("name") or provider_id

    installed = install_package(package, dest)
    print("Updated", installed, "picons for", label, "into", dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
