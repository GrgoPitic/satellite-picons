#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

import build as legacy
from catalog_common import (
    channel_identity,
    load_station_artwork,
    normalize_station_key,
    provider_definitions,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "channels.yml"


def safe_token(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "").strip()).strip("-").lower()
    return value or "channel"


def enrich_artwork(channel: dict) -> dict:
    item = dict(channel)
    provider_id = str(item.get("provider_group") or "").strip().lower()
    provider = provider_definitions().get(provider_id, {})
    item["delivery"] = str(item.get("delivery") or provider.get("delivery") or "satellite").lower()
    station_key = str(item.get("station_key") or normalize_station_key(item.get("name", "")))
    item["station_key"] = station_key
    identity = channel_identity(item, provider_id)

    artwork = (load_station_artwork().get("stations") or {}).get(station_key)
    if isinstance(artwork, dict):
        targets = {str(x) for x in artwork.get("targets", []) or []}
        selected_for_channel = not targets or identity in targets
        if selected_for_channel:
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
    synced, provider_metadata = legacy.load_synced_provider_data()
    merged: dict[str, dict] = {}

    for channel in synced:
        provider_id = str(channel.get("provider_group") or "").strip().lower()
        if provider_id:
            merged[channel_identity(channel, provider_id)] = dict(channel)

    for channel in cfg.get("channels", []) or []:
        provider_id = str(channel.get("provider_group") or "").strip().lower()
        key = channel_identity(channel, provider_id)
        base = dict(merged.get(key, {}))
        base.update(channel)
        merged[key] = base

    rows = [enrich_artwork(item) for item in merged.values()]
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

    for channel in cfg.get("channels", []) or []:
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


def main() -> int:
    legacy.merged_channels = merged_channels_v2
    legacy.resolve_channel_logo = resolve_local_only
    legacy.make_variant = make_variant_v2
    rc = legacy.main()
    if rc == 0:
        postprocess_public()
    return rc


ORIGINAL_MAKE_VARIANT = legacy.make_variant

if __name__ == "__main__":
    raise SystemExit(main())
