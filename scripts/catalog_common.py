#!/usr/bin/env python3
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS_CONFIG = ROOT / "providers.yml"
IPTV_PROVIDERS_CONFIG = ROOT / "iptv-providers.yml"
ARTWORK_CONFIG = ROOT / "station-artwork.yml"



# Technical placeholders are present in some Vhannibal lamedb/bouquets.
# Do not treat those entries as broadcast channels or logo upload targets.
_TECHNICAL_SID_NAME = re.compile(
    r"^\\s*\\d{4,6}\\s*[HV]\\s+SID\\s+0x[0-9a-f]+\\s*$",
    re.IGNORECASE,
)
_DOTTED_SEPARATOR = re.compile(r"^\\s*\\.\\s*\\d+\\s*\\.\\s*$")


def is_real_station_name(name: str) -> bool:
    """Reject known service-list separators, not genuine numeric brand names.

    Conservatively preserve titles such as '1+1', '123.live', '24Kitchen',
    '3sat', and even a purely numeric station name.
    """
    value = str(name or "").strip()
    if not value:
        return False
    if not any(ch.isalnum() for ch in value):
        return False
    if _DOTTED_SEPARATOR.fullmatch(value):
        return False
    if _TECHNICAL_SID_NAME.fullmatch(value):
        return False
    return True


def normalize_station_key(name: str) -> str:
    """Return a conservative canonical key shared across SAT/IPTV providers.

    We intentionally remove only presentation suffixes such as HD/SD/UHD/4K.
    Distinct brands like "Markiza Krimi" therefore never collapse into
    "Markiza" automatically.
    """
    value = unicodedata.normalize("NFKD", str(name or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower().replace("+", " plus ")
    value = re.sub(r"\b(?:uhd|4k|full\s*hd|fhd|hd|sd)\b", " ", value, flags=re.I)
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "channel"


def provider_definitions() -> dict[str, dict]:
    result: dict[str, dict] = {}
    for path, default_delivery in (
        (PROVIDERS_CONFIG, "satellite"),
    ):
        if not path.exists():
            continue
        cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for provider in cfg.get("providers", []) or []:
            provider_id = str(provider.get("id") or "").strip().lower()
            if not provider_id:
                continue
            item = dict(provider)
            item["id"] = provider_id
            item["delivery"] = str(item.get("delivery") or default_delivery).strip().lower()
            result[provider_id] = item
    return result


def provider_delivery(provider_id: str) -> str:
    provider = provider_definitions().get(str(provider_id or "").strip().lower(), {})
    return str(provider.get("delivery") or "satellite").strip().lower()


def service_identity(ref: str) -> str:
    parts = str(ref or "").strip().strip(":").split(":")
    if len(parts) < 7:
        return str(ref or "").strip().upper()
    return "_".join(parts[i].upper() for i in (3, 4, 5, 6))


def channel_identity(channel: dict, provider_id: str | None = None) -> str:
    provider = str(channel.get("provider_group") or provider_id or "").strip().lower()
    delivery = str(channel.get("delivery") or provider_delivery(provider)).strip().lower()

    if delivery == "iptv":
        tvg_id = str(channel.get("tvg_id") or "").strip().lower()
        channel_uid = str(channel.get("channel_uid") or channel.get("id") or "").strip().lower()
        identity = tvg_id or channel_uid or normalize_station_key(channel.get("name", ""))
        return f"iptv:{provider}:{identity}"

    ref = str(channel.get("service_reference") or "").strip()
    return f"sat:{provider}:{service_identity(ref)}"


def load_station_artwork() -> dict:
    if not ARTWORK_CONFIG.exists():
        return {"schema": 1, "stations": {}}
    payload = yaml.safe_load(ARTWORK_CONFIG.read_text(encoding="utf-8")) or {}
    payload.setdefault("schema", 1)
    payload.setdefault("stations", {})
    return payload


def save_station_artwork(payload: dict) -> None:
    ARTWORK_CONFIG.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def artwork_for_channel(channel: dict) -> tuple[str, dict | None]:
    key = str(channel.get("station_key") or normalize_station_key(channel.get("name", "")))
    data = load_station_artwork()
    artwork = (data.get("stations") or {}).get(key)
    return key, dict(artwork) if isinstance(artwork, dict) else None


def current_manual_channels(cfg):
    """Keep manual artwork overrides while refreshing current Skylink tuning.

    Match current Vhannibal services conservatively:
    1. exact DVB identity,
    2. unique canonical station key,
    3. otherwise keep the manual row unchanged rather than dropping user data.
    """
    import json

    rows = cfg.get("channels", []) or []
    path = ROOT / "provider-data" / "skylink-sk.json"
    if not path.exists():
        return rows

    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("source", {}).get("type") != "vhannibal":
        return rows

    live_rows = data.get("channels", []) or []
    by_ref = {}
    by_station = {}
    for channel in live_rows:
        ref = str(channel.get("service_reference") or "")
        if ref:
            by_ref[service_identity(ref)] = channel
        key = str(channel.get("station_key") or normalize_station_key(channel.get("name", "")))
        by_station.setdefault(key, []).append(channel)

    result = []
    for row in rows:
        if row.get("provider_group") not in {"skylink-sk", "skylink-cz"}:
            result.append(row)
            continue

        current = by_ref.get(service_identity(row.get("service_reference", "")))
        if current is None:
            station_key = str(row.get("station_key") or normalize_station_key(row.get("name", "")))
            candidates = by_station.get(station_key, [])
            if len(candidates) == 1:
                current = candidates[0]

        if current is None:
            # Never delete/drop a curated user row only because the upstream
            # catalogue changed or matching is ambiguous.
            result.append(row)
            continue

        item = dict(row)
        item["provider_group"] = "skylink-sk"
        item["station_key"] = str(
            current.get("station_key") or normalize_station_key(current.get("name", row.get("name", "")))
        )
        for key in ("service_reference", "variant_types", "satellite_position"):
            if current.get(key) is not None:
                item[key] = current[key]
        result.append(item)

    return result
