#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import yaml

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS_CONFIG = ROOT / "providers.yml"
DEFAULT_OUTPUT_DIR = ROOT / "provider-data"

DEFAULT_TIMEOUT = (10, 25)
USER_AGENT = (
    "SatellitePiconsProviderSync/0.3 "
    "(+https://github.com/GrgoPitic/satellite-picons)"
)


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.8,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "channel"


def normalize_position(value: str) -> str:
    text = value.upper().replace(",", ".").replace("°", "").replace(" ", "")
    match = re.search(r"(\d+(?:\.\d+)?)[°]?([EW])", text)
    if not match:
        raise ValueError("Unsupported satellite position: %s" % value)

    number = match.group(1)
    if number.endswith(".0"):
        number = number[:-2]
    return "%s%s" % (number, match.group(2))


def namespace_for_position(position: str) -> str:
    normalized = normalize_position(position)
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([EW])", normalized)
    if not match:
        raise ValueError("Unsupported satellite position: %s" % position)

    tenths = int(round(float(match.group(1)) * 10))
    orbital = tenths if match.group(2) == "E" else (3600 - tenths) % 3600
    return "%X0000" % orbital


def parse_int_decimal(value: str, field: str) -> int:
    match = re.search(r"\d+", value.replace(" ", ""))
    if not match:
        raise ValueError("Missing %s: %s" % (field, value))
    return int(match.group(0), 10)


def parse_optional_int(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"\d+", value.replace(" ", ""))
    return int(match.group(0), 10) if match else None


def service_key(sid: int, tsid: int, onid: int, namespace: str) -> str:
    return "%X_%X_%X_%s" % (sid, tsid, onid, namespace.upper())


def service_reference(sid: int, tsid: int, onid: int, namespace: str) -> str:
    return "1:0:19:%X:%X:%X:%s:0:0:0:" % (
        sid,
        tsid,
        onid,
        namespace.upper(),
    )


def get_text_pairs(soup: BeautifulSoup) -> dict[str, str]:
    tokens = [x.strip() for x in soup.stripped_strings if x.strip()]
    wanted = {
        "Operátor",
        "Typ",
        "Družica",
        "Frekvencia",
        "Provider",
        "FastScan (LCN)",
        "TSID",
        "ONID",
        "SID",
        "Posledná aktualizácia",
    }
    result: dict[str, str] = {}
    for index, token in enumerate(tokens[:-1]):
        if token in wanted:
            result[token] = tokens[index + 1]
    return result


def station_name(soup: BeautifulSoup) -> str:
    heading = soup.find("h1")
    if not heading:
        raise ValueError("Missing H1 station name")
    title = " ".join(heading.stripped_strings).strip()
    title = re.split(r"\s+[–-]\s+frekvencia", title, maxsplit=1, flags=re.I)[0]
    return title.strip()


def station_links(soup: BeautifulSoup, operator_url: str) -> list[str]:
    operator_path = urlparse(operator_url).path.rstrip("/")
    prefix = operator_path + "/program/"
    links: list[str] = []
    seen: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        absolute = urljoin(operator_url, anchor["href"])
        if not urlparse(absolute).path.startswith(prefix):
            continue
        if absolute not in seen:
            seen.add(absolute)
            links.append(absolute)
    return links


def load_provider_config(provider_id: str) -> dict:
    cfg = yaml.safe_load(PROVIDERS_CONFIG.read_text(encoding="utf-8")) or {}
    for provider in cfg.get("providers", []):
        if str(provider.get("id", "")).strip().lower() == provider_id.lower():
            return provider
    raise SystemExit("Unknown provider in providers.yml: %s" % provider_id)


def available_provider_ids() -> list[str]:
    cfg = yaml.safe_load(PROVIDERS_CONFIG.read_text(encoding="utf-8")) or {}
    result: list[str] = []
    for provider in cfg.get("providers", []):
        provider_id = str(provider.get("id", "")).strip().lower()
        source = provider.get("source") or {}
        if provider_id and source.get("type") == "satelitnatv":
            result.append(provider_id)
    return result


def sync_provider(
    provider_id: str,
    provider: dict,
    output: Path,
    limit: int | None = None,
    delay: float = 0.10,
) -> dict:
    source = provider.get("source") or {}
    if source.get("type") != "satelitnatv":
        raise RuntimeError(
            "Unsupported source type for %s: %s"
            % (provider_id, source.get("type"))
        )

    operator_url = source.get("operator_url")
    if not operator_url:
        raise RuntimeError("Provider %s is missing source.operator_url" % provider_id)

    session = make_session()
    listing_response = session.get(operator_url, timeout=DEFAULT_TIMEOUT)
    listing_response.raise_for_status()
    listing = BeautifulSoup(listing_response.text, "html.parser")

    links = station_links(listing, operator_url)
    if limit:
        links = links[:limit]
    if not links:
        raise RuntimeError("No station detail links found for %s" % provider_id)

    channels: list[dict] = []
    skipped_services: list[dict] = []
    errors: list[dict] = []

    for position_index, url in enumerate(links, 1):
        try:
            response = session.get(url, timeout=DEFAULT_TIMEOUT)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            name = station_name(soup)
            values = get_text_pairs(soup)
            service_kind = str(values.get("Typ", "")).strip().lower()
            if service_kind not in {"tv", "rádio", "radio"}:
                skipped_services.append(
                    {"name": name, "type": values.get("Typ"), "url": url}
                )
                continue

            sid = parse_int_decimal(values.get("SID", ""), "SID")
            tsid = parse_int_decimal(values.get("TSID", ""), "TSID")
            onid = parse_int_decimal(values.get("ONID", ""), "ONID")
            fastscan = parse_optional_int(values.get("FastScan (LCN)"))
            frequency = parse_optional_int(values.get("Frekvencia"))
            position = normalize_position(values.get("Družica", ""))
            namespace = namespace_for_position(position)

            channels.append(
                {
                    "id": slugify(name),
                    "name": name,
                    "provider_group": provider_id,
                    "service_reference": service_reference(sid, tsid, onid, namespace),
                    "satellite_position": position,
                    "fastscan": fastscan,
                    "frequency_mhz": frequency,
                    "source_url": url,
                    "source_updated_at": values.get("Posledná aktualizácia"),
                }
            )
        except Exception as error:
            errors.append(
                {
                    "url": url,
                    "error": "%s: %s" % (error.__class__.__name__, error),
                }
            )

        if delay > 0 and position_index < len(links):
            time.sleep(delay)

    channels.sort(
        key=lambda item: (
            int(item.get("fastscan") if item.get("fastscan") is not None else 99999),
            item["name"].lower(),
        )
    )

    total = len(channels)
    payload = {
        "schema": 2,
        "provider": provider_id,
        "provider_name": provider.get("name", provider_id),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "operator_url": operator_url,
            "operator": "SatelitnaTV.sk",
            "artwork_mode": "manual",
            "upstream_logos_imported": False,
        },
        "stats": {
            "detail_links": len(links),
            "channels_parsed": total,
            "services_skipped": len(skipped_services),
            "errors": len(errors),
            "upstream_logos_imported": 0,
        },
        "channels": channels,
        "skipped_services": skipped_services,
        "errors": errors,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> int:
    provider_ids = available_provider_ids()
    parser = argparse.ArgumentParser(
        description="Synchronize operator metadata only; artwork is curated manually"
    )
    parser.add_argument("provider", choices=provider_ids + ["all"])
    parser.add_argument("--output", help="Output JSON file (single provider only)")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--delay", type=float, default=0.10)
    parser.add_argument(
        "--min-coverage",
        type=float,
        default=0.0,
        help="Deprecated compatibility option; artwork is manual and coverage is not checked",
    )
    args = parser.parse_args()

    if args.provider == "all":
        if args.output:
            parser.error("--output cannot be used with provider=all")

        DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        valid_names = {"%s.json" % provider_id for provider_id in provider_ids}
        for path in DEFAULT_OUTPUT_DIR.glob("*.json"):
            if path.name not in valid_names:
                path.unlink()

        failed: list[tuple[str, str]] = []
        for provider_id in provider_ids:
            provider = load_provider_config(provider_id)
            output = DEFAULT_OUTPUT_DIR / ("%s.json" % provider_id)
            print("\n=== %s ===" % provider.get("name", provider_id))
            try:
                payload = sync_provider(
                    provider_id,
                    provider,
                    output=output,
                    limit=args.limit,
                    delay=max(0.0, args.delay),
                )
            except Exception as exc:
                reason = "%s: %s" % (exc.__class__.__name__, exc)
                failed.append((provider_id, reason))
                print("FAILED:", reason, file=sys.stderr)
                continue

            stats = payload["stats"]
            print(
                "Synced %(channels_parsed)s channels; metadata only; "
                "%(services_skipped)s skipped; %(errors)s errors."
                % stats
            )
            if stats["channels_parsed"] == 0:
                failed.append((provider_id, "zero parsed channels"))

        if failed:
            print("\nProvider sync failures:", file=sys.stderr)
            for provider_id, reason in failed:
                print(" - %s: %s" % (provider_id, reason), file=sys.stderr)
            return 2
        return 0

    provider = load_provider_config(args.provider)
    output = (
        Path(args.output)
        if args.output
        else DEFAULT_OUTPUT_DIR / ("%s.json" % args.provider)
    )
    payload = sync_provider(
        args.provider,
        provider,
        output=output,
        limit=args.limit,
        delay=max(0.0, args.delay),
    )
    stats = payload["stats"]
    print(
        "Synced %(channels_parsed)s channels; metadata only; "
        "%(services_skipped)s non-channel services skipped; %(errors)s errors."
        % stats
    )
    print("Output:", output)
    return 0 if stats["channels_parsed"] > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
