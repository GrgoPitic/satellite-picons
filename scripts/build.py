#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import io
import json
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import cairosvg
import requests
import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "channels.yml"
PROVIDERS_CONFIG = ROOT / "providers.yml"
PROVIDER_DATA_DIR = ROOT / "provider-data"
PUBLIC = ROOT / "public"
PICON_DIR = PUBLIC / "picons"
PACKAGE_DIR = PUBLIC / "packages"
WEB_DIR = ROOT / "web"
TEMPLATE = ROOT / "assets/templates/piconblack-150x90.png"
BASE_PACK = ROOT / "seed/base-pack.zip"

CANVAS = (150, 90)
MAX_LOGO = (148, 86)
SUPPORTED_LOGO_EXTENSIONS = {".png", ".svg", ".jpg", ".jpeg", ".webp"}
REMOTE_LOGO_TIMEOUT = 30
REMOTE_LOGO_USER_AGENT = (
    "SatellitePiconsBuilder/0.1 (+https://github.com/GrgoPitic/satellite-picons)"
)


def parse_ref(ref: str) -> list[str]:
    parts = [p.strip().upper() for p in ref.strip().strip(":").split(":")]
    if len(parts) != 10:
        raise ValueError(f"Service reference must have 10 fields: {ref}")
    return parts


def service_identity(ref: str) -> str:
    parts = parse_ref(ref)
    return "_".join(parts[3:7])


def ref_filename(ref_parts: list[str]) -> str:
    return "_".join(ref_parts) + ".png"


def make_variant(ref: str, service_type: str) -> str:
    parts = parse_ref(ref)
    parts[2] = service_type.upper()
    return ref_filename(parts)


def load_logo_image(logo_path: Path) -> Image.Image:
    ext = logo_path.suffix.lower()
    if ext not in SUPPORTED_LOGO_EXTENSIONS:
        raise ValueError(
            f"Unsupported logo format: {logo_path.name}. "
            f"Supported: {', '.join(sorted(SUPPORTED_LOGO_EXTENSIONS))}"
        )

    if ext == ".svg":
        svg_bytes = logo_path.read_bytes()
        png_bytes = cairosvg.svg2png(bytestring=svg_bytes)
        return Image.open(io.BytesIO(png_bytes)).convert("RGBA")

    return Image.open(logo_path).convert("RGBA")


def remove_edge_white(im: Image.Image) -> Image.Image:
    """Remove only near-white pixels connected to the outer edge."""
    im = im.convert("RGBA")
    px = im.load()
    w, h = im.size
    seen = set()
    stack = []

    for x in range(w):
        stack.extend([(x, 0), (x, h - 1)])
    for y in range(h):
        stack.extend([(0, y), (w - 1, y)])

    def is_bg(x: int, y: int) -> bool:
        r, g, b, a = px[x, y]
        return a > 0 and r >= 245 and g >= 245 and b >= 245

    while stack:
        x, y = stack.pop()
        if (x, y) in seen or not (0 <= x < w and 0 <= y < h):
            continue
        seen.add((x, y))
        if not is_bg(x, y):
            continue
        r, g, b, _ = px[x, y]
        px[x, y] = (r, g, b, 0)
        stack.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))

    return im


def has_real_transparency(im: Image.Image) -> bool:
    lo, _ = im.getchannel("A").getextrema()
    return lo < 250


def remove_corner_connected_background(im: Image.Image, tolerance: int = 28) -> Image.Image:
    im = im.convert("RGBA")
    if has_real_transparency(im):
        return im

    px = im.load()
    w, h = im.size
    if w < 2 or h < 2:
        return im

    seen = set()
    stack = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]

    def close(a, b):
        return max(abs(a[i] - b[i]) for i in range(3)) <= tolerance

    while stack:
        x, y = stack.pop()
        if (x, y) in seen or not (0 <= x < w and 0 <= y < h):
            continue
        seen.add((x, y))
        current = px[x, y]
        if current[3] == 0:
            continue
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if not (0 <= nx < w and 0 <= ny < h) or (nx, ny) in seen:
                continue
            neighbour = px[nx, ny]
            if neighbour[3] > 0 and close(current, neighbour):
                stack.append((nx, ny))

    if len(seen) < max(12, int(w * h * 0.015)):
        return im

    for x, y in seen:
        r, g, b, _ = px[x, y]
        px[x, y] = (r, g, b, 0)
    return im


def recolor_neutral_dark_to_white(im: Image.Image) -> Image.Image:
    """Turn neutral dark artwork/text to white, keep coloured elements intact."""
    im = im.convert("RGBA")
    data = list(im.getdata())
    out = []

    for r, g, b, a in data:
        if a == 0:
            out.append((r, g, b, a))
            continue

        mx, mn = max(r, g, b), min(r, g, b)
        chroma = mx - mn

        if mx <= 105 and chroma <= 28:
            lum = (r + g + b) / 3
            v = int(230 + (105 - lum) / 105 * 25)
            v = max(230, min(255, v))
            out.append((v, v, v, a))
        else:
            out.append((r, g, b, a))

    im.putdata(out)
    return im


def trim_alpha(im: Image.Image) -> Image.Image:
    alpha = im.getchannel("A")
    bbox = alpha.getbbox()
    if not bbox:
        raise ValueError("Logo is fully transparent")
    return im.crop(bbox)


def fit_logo(im: Image.Image, max_size=MAX_LOGO, optical_scale: float = 1.0) -> Image.Image:
    """Fill almost the entire picon while preserving the logo aspect ratio."""
    w, h = im.size
    if w <= 0 or h <= 0:
        raise ValueError("Invalid logo size")

    optical_scale = max(0.50, min(1.50, float(optical_scale)))
    scale = min(max_size[0] / w, max_size[1] / h) * optical_scale

    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))

    if new_w > max_size[0] or new_h > max_size[1]:
        cap = min(max_size[0] / new_w, max_size[1] / new_h)
        new_w = max(1, int(round(new_w * cap)))
        new_h = max(1, int(round(new_h * cap)))

    return im.resize((new_w, new_h), Image.Resampling.LANCZOS)


def render_logo(
    logo_path: Path,
    template: Image.Image,
    dark_to_white: bool,
    optical_scale: float = 1.0,
    ch_edge_cleanup: bool = False,
) -> Image.Image:
    logo = load_logo_image(logo_path)
    if bool(ch_edge_cleanup):
        logo = remove_edge_white(logo)

    logo = remove_corner_connected_background(logo)

    if dark_to_white:
        logo = recolor_neutral_dark_to_white(logo)

    logo = trim_alpha(logo)
    logo = fit_logo(logo, MAX_LOGO, optical_scale)

    out = template.copy().convert("RGBA")
    x = (CANVAS[0] - logo.width) // 2
    y = (CANVAS[1] - logo.height) // 2
    out.alpha_composite(logo, (x, y))
    return out


def load_synced_provider_data() -> tuple[list[dict], dict[str, dict]]:
    channels = []
    metadata = {}

    if not PROVIDER_DATA_DIR.exists():
        return channels, metadata

    for path in sorted(PROVIDER_DATA_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        provider_id = str(payload.get("provider", path.stem)).strip().lower()

        metadata[provider_id] = {
            "generated_at": payload.get("generated_at"),
            "source": payload.get("source") or {},
            "stats": payload.get("stats") or {},
        }

        for channel in payload.get("channels", []):
            item = dict(channel)
            item["provider_group"] = str(
                item.get("provider_group") or provider_id
            ).strip().lower()
            item["_generated_provider_data"] = True
            channels.append(item)

    return channels, metadata


def merged_channels(cfg: dict) -> tuple[list[dict], dict[str, dict]]:
    synced, provider_metadata = load_synced_provider_data()

    # Generated operator data provides the broad catalogue. Hand-curated
    # channels.yml entries intentionally override the same DVB service so local
    # artwork and per-logo rendering tweaks can always win.
    by_service = {}

    for channel in synced:
        ref = channel.get("service_reference")
        if not ref:
            continue
        by_service[service_identity(ref)] = channel

    for channel in cfg.get("channels", []):
        ref = channel.get("service_reference")
        if not ref:
            continue
        by_service[service_identity(ref)] = dict(channel)

    rows = list(by_service.values())
    rows.sort(
        key=lambda ch: (
            str(ch.get("provider_group") or ""),
            int(ch.get("fastscan") or 99999),
            str(ch.get("name") or "").lower(),
        )
    )
    return rows, provider_metadata


def download_remote_logo(
    url: str,
    cache_dir: Path,
    session: requests.Session,
) -> Path:
    parsed = urlparse(url)
    ext = Path(parsed.path).suffix.lower()
    if ext not in SUPPORTED_LOGO_EXTENSIONS:
        raise ValueError("Unsupported remote logo extension: %s" % url)

    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    destination = cache_dir / (digest + ext)

    if destination.exists():
        return destination

    response = session.get(url, timeout=REMOTE_LOGO_TIMEOUT)
    response.raise_for_status()
    destination.write_bytes(response.content)
    return destination


def resolve_channel_logo(
    channel: dict,
    cache_dir: Path,
    session: requests.Session,
) -> Path | None:
    local_logo = channel.get("logo")
    if local_logo:
        path = ROOT / str(local_logo)
        if path.exists():
            return path
        raise FileNotFoundError(path)

    logo_url = channel.get("logo_url")
    if logo_url:
        return download_remote_logo(str(logo_url), cache_dir, session)

    return None


def main() -> int:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    project = cfg["project"]

    providers_cfg = {"schema": 1, "providers": []}
    if PROVIDERS_CONFIG.exists():
        providers_cfg = (
            yaml.safe_load(PROVIDERS_CONFIG.read_text(encoding="utf-8"))
            or providers_cfg
        )

    provider_defs = {}
    for provider in providers_cfg.get("providers", []):
        provider_id = str(provider.get("id", "")).strip().lower()
        if not provider_id:
            continue
        provider_defs[provider_id] = {
            "id": provider_id,
            "name": str(provider.get("name") or provider_id),
            "description": str(provider.get("description") or ""),
            "countries": [str(x) for x in provider.get("countries", [])],
            "sort_order": int(provider.get("sort_order", 999)),
        }

    variant_types = [
        str(x).upper()
        for x in project.get("variant_types", ["1", "16", "19"])
    ]

    source_channels, provider_source_metadata = merged_channels(cfg)

    if PUBLIC.exists():
        shutil.rmtree(PUBLIC)
    PICON_DIR.mkdir(parents=True)
    PACKAGE_DIR.mkdir(parents=True)

    if BASE_PACK.exists():
        with zipfile.ZipFile(BASE_PACK) as base_zip:
            for info in base_zip.infolist():
                if (
                    info.is_dir()
                    or not info.filename.lower().endswith(".png")
                    or info.filename.startswith("__MACOSX/")
                ):
                    continue
                name = Path(info.filename).name
                if not name:
                    continue
                with base_zip.open(info) as src, open(PICON_DIR / name, "wb") as dst:
                    shutil.copyfileobj(src, dst)

    template = Image.open(TEMPLATE).convert("RGBA")
    if template.size != CANVAS:
        raise ValueError(
            f"Template must be {CANVAS[0]}x{CANVAS[1]}, got {template.size}"
        )

    index = {
        "schema": 2,
        "package": project["package"],
        "style": project["style"],
        "resolution": project["resolution"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "channels": [],
    }

    skipped_without_logo = []
    session = requests.Session()
    session.headers.update({"User-Agent": REMOTE_LOGO_USER_AGENT})

    with tempfile.TemporaryDirectory(prefix="satellite-picons-build-") as temp:
        cache_dir = Path(temp)

        for ch in source_channels:
            logo_path = resolve_channel_logo(ch, cache_dir, session)
            if logo_path is None:
                skipped_without_logo.append(
                    {
                        "id": ch.get("id"),
                        "name": ch.get("name"),
                        "service_reference": ch.get("service_reference"),
                        "provider_group": ch.get("provider_group"),
                    }
                )
                continue

            rendered = render_logo(
                logo_path,
                template,
                bool(ch.get("dark_to_white", False)),
                float(ch.get("optical_scale", 1.0)),
                bool(ch.get("edge_cleanup", False)),
            )
            files = []

            for stype in ch.get("variant_types", variant_types):
                filename = make_variant(ch["service_reference"], str(stype))
                rendered.save(PICON_DIR / filename, optimize=True)
                files.append(filename)

            index["channels"].append(
                {
                    "id": ch["id"],
                    "name": ch["name"],
                    "logo": ch.get("logo"),
                    "logo_url": ch.get("logo_url"),
                    "logo_source": ch.get("logo_source"),
                    "service_reference": ch["service_reference"],
                    "optical_scale": float(ch.get("optical_scale", 1.0)),
                    "logo_version": int(ch.get("logo_version", 1)),
                    "updated_at": ch.get("updated_at")
                    or ch.get("source_updated_at"),
                    "satellite_position": ch.get("satellite_position"),
                    "provider_group": ch.get("provider_group"),
                    "fastscan": ch.get("fastscan"),
                    "frequency_mhz": ch.get("frequency_mhz"),
                    "files": files,
                }
            )

    index["build_stats"] = {
        "source_channels": len(source_channels),
        "rendered_channels": len(index["channels"]),
        "skipped_without_logo": len(skipped_without_logo),
    }
    if skipped_without_logo:
        index["skipped_without_logo"] = skipped_without_logo

    for src in WEB_DIR.iterdir():
        if src.is_file():
            shutil.copy2(src, PUBLIC / src.name)

    (PUBLIC / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    package_name = (
        f"{project['package']}-{project['resolution']}-{project['style']}.zip"
    )
    package_path = PACKAGE_DIR / package_name

    with zipfile.ZipFile(
        package_path,
        "w",
        zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as zf:
        for file in sorted(PICON_DIR.glob("*.png")):
            zf.write(file, arcname=file.name)

    grouped_packages = {}
    grouped_channels = {}
    provider_channels = {}

    for ch in index["channels"]:
        provider_group = ch.get("provider_group")
        if provider_group:
            provider_group = str(provider_group).strip().lower()
            provider_channels.setdefault(provider_group, []).append(ch)

        group = provider_group or ch.get("satellite_position")
        if not group:
            continue
        grouped_channels.setdefault(group, []).extend(ch["files"])

    for group, files in sorted(grouped_channels.items()):
        safe_group = "".join(
            c if c.isalnum() or c in "-._" else "-"
            for c in str(group)
        ).strip("-").lower()

        group_name = (
            f"{project['package']}-{safe_group}-"
            f"{project['resolution']}-{project['style']}.zip"
        )
        group_path = PACKAGE_DIR / group_name

        with zipfile.ZipFile(
            group_path,
            "w",
            zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as zf:
            for filename in sorted(set(files)):
                src = PICON_DIR / filename
                if src.exists():
                    zf.write(src, arcname=filename)

        grouped_packages[str(group)] = {
            "package": f"packages/{group_name}",
            "count": len(set(files)),
        }

    providers_payload = {
        "schema": int(providers_cfg.get("schema", 1)),
        "generated_at": index["generated_at"],
        "providers": [],
    }

    all_provider_ids = set(provider_defs) | set(provider_channels)
    for provider_id in sorted(
        all_provider_ids,
        key=lambda pid: (
            provider_defs.get(pid, {}).get("sort_order", 999),
            provider_defs.get(pid, {}).get("name", pid).lower(),
        ),
    ):
        meta = provider_defs.get(
            provider_id,
            {
                "id": provider_id,
                "name": provider_id,
                "description": "",
                "countries": [],
                "sort_order": 999,
            },
        )
        channels = provider_channels.get(provider_id, [])
        files = sorted(
            {
                filename
                for channel in channels
                for filename in channel["files"]
            }
        )
        group_info = grouped_packages.get(provider_id)
        positions = sorted(
            {
                str(channel["satellite_position"])
                for channel in channels
                if channel.get("satellite_position")
            }
        )
        source_meta = provider_source_metadata.get(provider_id, {})

        providers_payload["providers"].append(
            {
                "id": provider_id,
                "name": meta["name"],
                "description": meta["description"],
                "countries": meta["countries"],
                "positions": positions,
                "channel_count": len(channels),
                "picon_count": len(files),
                "available": bool(group_info and files),
                "package": (
                    group_info["package"]
                    if group_info and files
                    else None
                ),
                "source_generated_at": source_meta.get("generated_at"),
                "source_stats": source_meta.get("stats") or None,
            }
        )

    (PUBLIC / "providers.json").write_text(
        json.dumps(providers_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    version = {
        "schema": 2,
        "version": datetime.now(timezone.utc).strftime("%Y.%m.%d.%H%M%S"),
        "package": f"packages/{package_name}",
        "index": "index.json",
        "providers": "providers.json",
        "count": len(list(PICON_DIR.glob("*.png"))),
        "groups": grouped_packages,
        "build_stats": index["build_stats"],
    }

    (PUBLIC / "version.json").write_text(
        json.dumps(version, indent=2),
        encoding="utf-8",
    )

    print(f"Built {version['count']} picons -> {PUBLIC}")
    print(f"Channels rendered: {len(index['channels'])}/{len(source_channels)}")
    if skipped_without_logo:
        print(
            f"Skipped channels without source logo: "
            f"{len(skipped_without_logo)}"
        )
    print(f"Package: {package_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
