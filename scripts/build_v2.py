#!/usr/bin/env python3
from __future__ import annotations
from catalog_common import current_manual_channels

import json
import re
import zipfile
from collections import defaultdict
from pathlib import Path

import yaml

import build as legacy
from catalog_common import (
    channel_identity,
    is_real_station_name,
    load_station_artwork,
    normalize_station_key,
    provider_definitions,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "channels.yml"


def safe_token(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "").strip()).strip("-").lower()
    return value or "channel"


def enrich_artwork(channel: dict, stations: dict | None = None) -> dict:
    item = dict(channel)
    provider_id = str(item.get("provider_group") or "").strip().lower()
    provider = provider_definitions().get(provider_id, {})
    item["delivery"] = str(item.get("delivery") or provider.get("delivery") or "satellite").lower()
    station_key = normalize_station_key(item.get("name", ""))
    item["station_key"] = station_key
    identity = channel_identity(item, provider_id)

    if stations is None:
        stations = load_station_artwork().get("stations") or {}
    artwork = stations.get(station_key)

    # An explicit service assignment takes precedence over name variations.
    # This is the same rule used by the administrator when sharing artwork
    # across operators (for example Skylink and ANTIK Sat).
    if not (isinstance(artwork, dict) and (
        not artwork.get("targets") or identity in {str(x) for x in artwork.get("targets", [])}
    )):
        artwork = next(
            (candidate for candidate in stations.values()
             if isinstance(candidate, dict)
             and identity in {str(x) for x in candidate.get("targets", []) or []}),
            None,
        )

    if isinstance(artwork, dict):
        provider_override = (artwork.get("provider_overrides") or {}).get(provider_id)
        selected = provider_override if isinstance(provider_override, dict) else artwork
        if selected.get("logo"):
            item["logo"] = selected.get("logo")
        for field in ("dark_to_white", "optical_scale", "edge_cleanup", "background_cleanup"):
            if field in selected:
                item[field] = selected[field]

    # Legacy renderer expects a service_reference. IPTV gets a deterministic
    # internal reference only for build/index purposes; it is not an Enigma2
    # stream URL. The receiver/client can later map tvg-id/channel_uid to its
    # real IPTV bouquet reference and rename the picon locally.
    if item["delivery"] == "iptv" and not item.get("service_reference"):
        token = str(item.get("tvg_id") or item.get("channel_uid") or station_key)
        item["service_reference"] = f"iptv:{provider_id}:{safe_token(token)}"
        item["variant_types"] = ["iptv"]

    return item


def merged_channels_v2(cfg: dict) -> tuple[list[dict], dict[str, dict]]:
    # Vhannibal is the single source of *which services exist*. Keep stored
    # artwork overrides, but do not expose services absent from its catalogue.
    synced_all, metadata = legacy.load_synced_provider_data()
    synced = [ch for ch in synced_all
              if str(ch.get("provider_group") or "").lower() == "skylink-sk"
              and is_real_station_name(ch.get("name") or "")]
    if not synced:
        raise RuntimeError("Vhannibal catalogue is empty or unavailable; refusing empty public build.")
    provider_metadata = {"skylink-sk": metadata.get("skylink-sk", {})}
    merged: dict[str, dict] = {
        channel_identity(ch, "skylink-sk"): dict(ch) for ch in synced
    }

    for channel in current_manual_channels(cfg):
        provider_id = str(channel.get("provider_group") or "").strip().lower()
        if provider_id not in {"skylink-sk", "skylink-cz"}:
            continue
        key = channel_identity(channel, "skylink-sk")
        if key not in merged:
            # Preserve the artwork on disk; only hide outdated service refs.
            continue
        base = dict(merged[key])
        # Keep the *current* Vhannibal tuning, never restore a stale ref.
        for field in ("logo", "dark_to_white", "optical_scale",
                      "edge_cleanup", "background_cleanup"):
            if field in channel:
                base[field] = channel[field]
        merged[key] = base

    artwork_stations = load_station_artwork().get("stations") or {}
    rows = [enrich_artwork(item, artwork_stations) for item in merged.values()]
    rows.sort(key=lambda ch: (
        str(ch.get("delivery") or ""),
        str(ch.get("provider_group") or ""),
        int(ch.get("fastscan") or 99999),
        str(ch.get("name") or "").lower(),
    ))
    return rows, provider_metadata


def make_variant_v2(ref: str, service_type: str) -> str:
    if str(ref).startswith("iptv:"):
        _, provider_id, token = (str(ref).split(":", 2) + ["", ""])[:3]
        return f"iptv_{safe_token(provider_id)}_{safe_token(token)}.png"
    return ORIGINAL_MAKE_VARIANT(ref, service_type)


def resolve_local_only(channel: dict, cache_dir: Path, session) -> Path | None:
    local_logo = channel.get("logo")
    if not local_logo:
        return None
    path = ROOT / str(local_logo)
    if path.exists() and path.is_file():
        return path
    raise FileNotFoundError(path)


def manual_iptv_catalogue() -> tuple[dict[str, int], dict[tuple[str, str], dict]]:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    counts: dict[str, int] = {}
    details: dict[tuple[str, str], dict] = {}
    defs = provider_definitions()

    for channel in current_manual_channels(cfg):
        provider_id = str(channel.get("provider_group") or "").strip().lower()
        delivery = str(channel.get("delivery") or defs.get(provider_id, {}).get("delivery") or "satellite").lower()
        if delivery != "iptv" or not provider_id:
            continue
        counts[provider_id] = counts.get(provider_id, 0) + 1
        details[(provider_id, str(channel.get("id") or "").lower())] = dict(channel)
    return counts, details


def postprocess_public() -> None:
    defs = provider_definitions()
    iptv_counts, iptv_details = manual_iptv_catalogue()
    providers_path = ROOT / "public" / "providers.json"

    if providers_path.exists():
        payload = json.loads(providers_path.read_text(encoding="utf-8"))
        providers = payload.setdefault("providers", [])
        by_id = {str(p.get("id") or "").lower(): p for p in providers}

        for provider in providers:
            provider_id = str(provider.get("id") or "").lower()
            meta = defs.get(provider_id, {})
            provider["delivery"] = str(meta.get("delivery") or provider.get("delivery") or "satellite").lower()
            provider["source_type"] = str((meta.get("source") or {}).get("type") or provider.get("source_type") or "legacy")
            provider["curated_channel_count"] = int(provider.get("curated_channel_count", provider.get("channel_count") or 0))
            source_stats = provider.get("source_stats") or {}
            if source_stats.get("channels_parsed") is not None:
                provider["channel_count"] = int(source_stats["channels_parsed"])
            elif provider["delivery"] == "iptv":
                provider["channel_count"] = int(iptv_counts.get(provider_id, provider.get("channel_count") or 0))

        for provider_id, meta in defs.items():
            provider = by_id.get(provider_id)
            if provider is None:
                provider = {
                    "id": provider_id,
                    "positions": [],
                    "channel_count": 0,
                    "picon_count": 0,
                    "available": False,
                    "package": None,
                    "source_generated_at": None,
                    "source_stats": None,
                }
                providers.append(provider)
                by_id[provider_id] = provider

            provider["name"] = str(meta.get("name") or provider_id)
            provider["description"] = str(meta.get("description") or provider.get("description") or "")
            provider["countries"] = [str(x) for x in meta.get("countries", provider.get("countries", []))]
            provider["delivery"] = str(meta.get("delivery") or "satellite").lower()
            provider["source_type"] = str((meta.get("source") or {}).get("type") or "manual")
            provider["curated_channel_count"] = int(provider.get("curated_channel_count", provider.get("channel_count") or 0))
            source_stats = provider.get("source_stats") or {}
            if source_stats.get("channels_parsed") is not None:
                provider["channel_count"] = int(source_stats["channels_parsed"])
            elif provider["delivery"] == "iptv":
                provider["channel_count"] = int(iptv_counts.get(provider_id, 0))

        providers.sort(key=lambda p: (
            int(defs.get(str(p.get("id") or "").lower(), {}).get("sort_order", 999)),
            str(p.get("name") or "").lower(),
        ))
        providers_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    index_path = ROOT / "public" / "index.json"
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))
        for channel in index.get("channels", []):
            provider_id = str(channel.get("provider_group") or "").lower()
            delivery = str(defs.get(provider_id, {}).get("delivery") or channel.get("delivery") or "satellite").lower()
            channel["delivery"] = delivery
            channel["station_key"] = normalize_station_key(channel.get("name", ""))
            if delivery == "iptv":
                detail = iptv_details.get((provider_id, str(channel.get("id") or "").lower()), {})
                channel["tvg_id"] = detail.get("tvg_id")
                channel["channel_uid"] = detail.get("channel_uid") or detail.get("id")
                if str(channel.get("service_reference") or "").startswith("iptv:"):
                    channel["service_reference"] = None
        index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_orbit_catalogue() -> None:
    """Generate per-orbit metadata and partial packs from Vhannibal data only."""
    catalogue_file = ROOT / "provider-data" / "skylink-sk.json"
    source = json.loads(catalogue_file.read_text(encoding="utf-8"))
    public = ROOT / "public"
    index = json.loads((public / "index.json").read_text(encoding="utf-8"))
    expected = defaultdict(int)
    for channel in source.get("channels", []):
        if not is_real_station_name(channel.get("name") or ""):
            continue
        position = str(channel.get("satellite_position") or "").strip()
        if position:
            expected[position] += 1

    grouped = defaultdict(list)
    for channel in index.get("channels", []):
        position = str(channel.get("satellite_position") or "").strip()
        if position:
            grouped[position].append(channel)

    packages_dir = public / "packages"
    packages_dir.mkdir(exist_ok=True)
    orbits = []
    for position in sorted(expected):
        channels = grouped.get(position, [])
        token = re.sub(r"[^a-z0-9]+", "-", position.lower()).strip("-")
        package = None
        files = sorted({filename for channel in channels
                        for filename in channel.get("files", [])})
        if files:
            package = f"packages/vhannibal-{token}-curated.zip"
            with zipfile.ZipFile(public / package, "w", compression=zipfile.ZIP_DEFLATED,
                                 compresslevel=9) as archive:
                for filename in files:
                    logo = public / "picons" / filename
                    if not logo.is_file():
                        raise FileNotFoundError(logo)
                    archive.write(logo, arcname=filename)
        orbits.append({
            "id": position, "name": position, "positions": [position],
            "channel_count": expected[position],
            "curated_channel_count": len(channels),
            "picon_count": len(files),
            "package": package,
            "complete": len(channels) == expected[position],
            "available": bool(files),
            "description": "Vhannibal · orbitálna pozícia " + position,
        })
    (public / "orbits.json").write_text(json.dumps({
        "schema": 1, "source": "Vhannibal", "orbits": orbits,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def copy_catalogue_change_history() -> None:
    """Expose the same public change history as the administrator."""
    history = ROOT / "catalogue-changes.json"
    destination = ROOT / "public" / "catalogue-changes.json"
    if history.is_file():
        destination.write_bytes(history.read_bytes())
    else:
        destination.write_text('{"schema":1,"events":[]}\n', encoding="utf-8")


def main() -> int:
    legacy.merged_channels = merged_channels_v2
    legacy.resolve_channel_logo = resolve_local_only
    legacy.make_variant = make_variant_v2
    rc = legacy.main()
    if rc == 0:
        postprocess_public()
        copy_catalogue_change_history()
        build_orbit_catalogue()
    return rc


ORIGINAL_MAKE_VARIANT = legacy.make_variant

if __name__ == "__main__":
    raise SystemExit(main())
