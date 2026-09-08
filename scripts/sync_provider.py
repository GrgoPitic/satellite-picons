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
    "SatellitePiconsProviderSync/0.2 "
    "(+https://github.com/GrgoPitic/satellite-picons)"
)

NAMESPACE_BY_POSITION = {
    "23.5E": "EB0000",
    "19.2E": "C00000",
    "16E": "A00000",
    "13E": "820000",
}

PICONS_REPO = "picons/picons"
PICONS_BRANCH = "master"
PICONS_API_TREE = (
    "https://api.github.com/repos/%s/git/trees/%s?recursive=1"
    % (PICONS_REPO, PICONS_BRANCH)
)
PICONS_SRP_INDEX = (
    "https://raw.githubusercontent.com/%s/%s/build-source/srp.index"
    % (PICONS_REPO, PICONS_BRANCH)
)
PICONS_RAW_PREFIX = "https://raw.githubusercontent.com/%s/%s/" % (
    PICONS_REPO,
    PICONS_BRANCH,
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
    # Base service type is 19. The build creates the configured variants.
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
    result = {}

    for index, token in enumerate(tokens[:-1]):
        if token in wanted:
            result[token] = tokens[index + 1]

    return result


def station_name(soup: BeautifulSoup) -> str:
    heading = soup.find("h1")
    if not heading:
        raise ValueError("Missing H1 station name")

    title = " ".join(heading.stripped_strings).strip()
    title = re.split(
        r"\s+[–-]\s+frekvencia",
        title,
        maxsplit=1,
        flags=re.I,
    )[0]
    return title.strip()


def station_links(soup: BeautifulSoup, operator_url: str) -> list[str]:
    operator_path = urlparse(operator_url).path.rstrip("/")
    prefix = operator_path + "/program/"

    links = []
    seen = set()

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        absolute = urljoin(operator_url, href)
        path = urlparse(absolute).path

        if not path.startswith(prefix):
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
    result = []

    for provider in cfg.get("providers", []):
        provider_id = str(provider.get("id", "")).strip().lower()
        source = provider.get("source") or {}
        if provider_id and source.get("type") == "satelitnatv":
            result.append(provider_id)

    return result


def fetch_picons_indexes(
    session: requests.Session,
) -> tuple[dict[str, str], dict[str, str], str | None]:
    srp_response = session.get(PICONS_SRP_INDEX, timeout=DEFAULT_TIMEOUT)
    srp_response.raise_for_status()

    srp = {}
    for line in srp_response.text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, logo = line.split("=", 1)
        srp[key.strip().upper()] = logo.strip()

    tree_response = session.get(PICONS_API_TREE, timeout=DEFAULT_TIMEOUT)
    tree_response.raise_for_status()
    tree_payload = tree_response.json()

    preferred = {}
    priority = {
        ".default.svg": 0,
        ".default.png": 1,
        ".default.webp": 2,
        ".light.svg": 3,
        ".light.png": 4,
        ".dark.svg": 5,
        ".dark.png": 6,
    }

    for item in tree_payload.get("tree", []):
        path = item.get("path", "")
        if not path.startswith("build-source/logos/"):
            continue

        filename = Path(path).name
        lower = filename.lower()

        for suffix, rank in priority.items():
            if not lower.endswith(suffix):
                continue

            slug = filename[: -len(suffix)]
            current = preferred.get(slug)
            if current is None or rank < current[0]:
                preferred[slug] = (rank, path)
            break

    logo_paths = {
        slug: value[1]
        for slug, value in preferred.items()
    }
    revision = tree_payload.get("sha")
    return srp, logo_paths, revision


def resolve_logo(
    key: str,
    name: str,
    srp: dict[str, str],
    logo_paths: dict[str, str],
) -> tuple[str | None, str | None]:
    slug = srp.get(key.upper())

    if slug and slug in logo_paths:
        return slug, logo_paths[slug]

    # Conservative fallback: exact normalized channel name only.
    compact = re.sub(r"[^a-z0-9]", "", name.lower())
    candidates = []

    for upstream_slug in logo_paths:
        upstream_compact = re.sub(
            r"[^a-z0-9]",
            "",
            upstream_slug.lower(),
        )
        if upstream_compact == compact:
            candidates.append(upstream_slug)

    if len(candidates) == 1:
        fallback = candidates[0]
        return fallback, logo_paths[fallback]

    return None, None


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
        raise RuntimeError(
            "Provider %s is missing source.operator_url"
            % provider_id
        )

    session = make_session()

    listing_response = session.get(operator_url, timeout=DEFAULT_TIMEOUT)
    listing_response.raise_for_status()
    listing = BeautifulSoup(listing_response.text, "html.parser")

    links = station_links(listing, operator_url)
    if limit:
        links = links[:limit]

    if not links:
        raise RuntimeError(
            "No station detail links found for %s"
            % provider_id
        )

    srp, logo_paths, picons_revision = fetch_picons_indexes(session)

    channels = []
    missing_logo = []
    skipped_services = []
    errors = []

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
                    {
                        "name": name,
                        "type": values.get("Typ"),
                        "url": url,
                    }
                )
                continue

            sid = parse_int_decimal(values.get("SID", ""), "SID")
            tsid = parse_int_decimal(values.get("TSID", ""), "TSID")
            onid = parse_int_decimal(values.get("ONID", ""), "ONID")
            fastscan = parse_optional_int(values.get("FastScan (LCN)"))
            frequency = parse_optional_int(values.get("Frekvencia"))

            position = normalize_position(values.get("Družica", ""))
            namespace = NAMESPACE_BY_POSITION.get(position)
            if not namespace:
                raise ValueError(
                    "No Enigma2 namespace mapping for %s"
                    % position
                )

            key = service_key(sid, tsid, onid, namespace)
            logo_slug, logo_path = resolve_logo(
                key,
                name,
                srp,
                logo_paths,
            )
            logo_url = (
                PICONS_RAW_PREFIX + logo_path
                if logo_path
                else None
            )

            channel = {
                "id": slugify(name),
                "name": name,
                "provider_group": provider_id,
                "service_reference": service_reference(
                    sid,
                    tsid,
                    onid,
                    namespace,
                ),
                "satellite_position": position,
                "fastscan": fastscan,
                "frequency_mhz": frequency,
                "source_url": url,
                "source_updated_at": values.get(
                    "Posledná aktualizácia"
                ),
                "logo_slug": logo_slug,
                "logo_url": logo_url,
                "logo_source": (
                    PICONS_REPO
                    if logo_url
                    else None
                ),
            }
            channels.append(channel)

            if not logo_url:
                missing_logo.append(
                    {
                        "name": name,
                        "service_key": key,
                        "service_reference": channel[
                            "service_reference"
                        ],
                    }
                )

        except Exception as error:
            errors.append(
                {
                    "url": url,
                    "error": "%s: %s"
                    % (
                        error.__class__.__name__,
                        error,
                    ),
                }
            )

        if delay > 0 and position_index < len(links):
            time.sleep(delay)

    channels.sort(
        key=lambda item: (
            int(
                item.get("fastscan")
                if item.get("fastscan") is not None
                else 99999
            ),
            item["name"].lower(),
        )
    )

    matched = sum(
        1
        for item in channels
        if item.get("logo_url")
    )
    total = len(channels)
    coverage = (
        round((matched / total * 100.0), 2)
        if total
        else 0.0
    )

    payload = {
        "schema": 1,
        "provider": provider_id,
        "provider_name": provider.get(
            "name",
            provider_id,
        ),
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "source": {
            "operator_url": operator_url,
            "operator": "SatelitnaTV.sk",
            "logo_repository": PICONS_REPO,
            "logo_revision": picons_revision,
        },
        "stats": {
            "detail_links": len(links),
            "channels_parsed": total,
            "logos_matched": matched,
            "logos_missing": len(missing_logo),
            "services_skipped": len(skipped_services),
            "errors": len(errors),
            "logo_coverage_percent": coverage,
        },
        "channels": channels,
        "missing_logos": missing_logo,
        "skipped_services": skipped_services,
        "errors": errors,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return payload


def main() -> int:
    provider_ids = available_provider_ids()

    parser = argparse.ArgumentParser(
        description="Synchronize operator channel metadata"
    )
    parser.add_argument(
        "provider",
        choices=provider_ids,
    )
    parser.add_argument(
        "--output",
        help="Output JSON file",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only parse first N channels",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.10,
        help="Delay between station requests",
    )
    parser.add_argument(
        "--min-coverage",
        type=float,
        default=70.0,
        help="Fail when logo coverage is below this percentage",
    )
    args = parser.parse_args()

    provider = load_provider_config(args.provider)
    output = (
        Path(args.output)
        if args.output
        else DEFAULT_OUTPUT_DIR
        / ("%s.json" % args.provider)
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
        "Synced %(channels_parsed)s channels; "
        "%(logos_matched)s logos matched "
        "(%(logo_coverage_percent)s%%); "
        "%(logos_missing)s missing; "
        "%(services_skipped)s non-channel services skipped; "
        "%(errors)s errors."
        % stats
    )
    print("Output:", output)

    if stats["channels_parsed"] == 0:
        return 2

    if stats["logo_coverage_percent"] < args.min_coverage:
        print(
            "Coverage %.2f%% is below required %.2f%%"
            % (
                stats["logo_coverage_percent"],
                args.min_coverage,
            ),
            file=sys.stderr,
        )
        return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
