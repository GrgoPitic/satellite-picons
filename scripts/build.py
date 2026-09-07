#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import cairosvg
import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "channels.yml"
PUBLIC = ROOT / "public"
PICON_DIR = PUBLIC / "picons"
PACKAGE_DIR = PUBLIC / "packages"
WEB_DIR = ROOT / "web"
TEMPLATE = ROOT / "assets/templates/piconblack-150x90.png"
BASE_PACK = ROOT / "seed/base-pack.zip"

CANVAS = (150, 90)
MAX_LOGO = (140, 80)
SUPPORTED_LOGO_EXTENSIONS = {".png", ".svg", ".jpg", ".jpeg", ".webp"}


def parse_ref(ref: str) -> list[str]:
    parts = [p.strip().upper() for p in ref.strip().strip(":").split(":")]
    if len(parts) != 10:
        raise ValueError(f"Service reference must have 10 fields: {ref}")
    return parts


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
    """Scale artwork UP or DOWN to consistently fill the safe box.

    The transparent/white outer margin is removed before this function runs,
    so source pixel dimensions no longer influence the visual size.
    """
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
    ch_edge_cleanup: bool = True,
) -> Image.Image:
    logo = load_logo_image(logo_path)
    if ch_edge_cleanup:
        logo = remove_edge_white(logo)

    if dark_to_white:
        logo = recolor_neutral_dark_to_white(logo)

    logo = trim_alpha(logo)
    logo = fit_logo(logo, MAX_LOGO, optical_scale)

    out = template.copy().convert("RGBA")
    x = (CANVAS[0] - logo.width) // 2
    y = (CANVAS[1] - logo.height) // 2
    out.alpha_composite(logo, (x, y))
    return out


def main() -> int:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    project = cfg["project"]
    variant_types = [str(x).upper() for x in project.get("variant_types", ["1", "16", "19"])]

    if PUBLIC.exists():
        shutil.rmtree(PUBLIC)
    PICON_DIR.mkdir(parents=True)
    PACKAGE_DIR.mkdir(parents=True)

    if BASE_PACK.exists():
        with zipfile.ZipFile(BASE_PACK) as base_zip:
            for info in base_zip.infolist():
                if info.is_dir() or not info.filename.lower().endswith(".png") or info.filename.startswith("__MACOSX/"):
                    continue
                name = Path(info.filename).name
                if not name:
                    continue
                with base_zip.open(info) as src, open(PICON_DIR / name, "wb") as dst:
                    shutil.copyfileobj(src, dst)

    template = Image.open(TEMPLATE).convert("RGBA")
    if template.size != CANVAS:
        raise ValueError(f"Template must be {CANVAS[0]}x{CANVAS[1]}, got {template.size}")

    index = {
        "schema": 1,
        "package": project["package"],
        "style": project["style"],
        "resolution": project["resolution"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "channels": [],
    }

    for ch in cfg.get("channels", []):
        logo_path = ROOT / ch["logo"]
        if not logo_path.exists():
            raise FileNotFoundError(logo_path)

        rendered = render_logo(
            logo_path,
            template,
            bool(ch.get("dark_to_white", True)),
            float(ch.get("optical_scale", 1.0)),
            bool(ch.get("edge_cleanup", True)),
        )
        files = []

        for stype in ch.get("variant_types", variant_types):
            filename = make_variant(ch["service_reference"], str(stype))
            rendered.save(PICON_DIR / filename, optimize=True)
            files.append(filename)

        index["channels"].append({
            "id": ch["id"],
            "name": ch["name"],
            "logo": str(ch["logo"]),
            "service_reference": ch["service_reference"],
            "optical_scale": float(ch.get("optical_scale", 1.0)),
            "logo_version": int(ch.get("logo_version", 1)),
            "updated_at": ch.get("updated_at"),
            "files": files,
        })

    for src in WEB_DIR.iterdir():
        if src.is_file():
            shutil.copy2(src, PUBLIC / src.name)

    (PUBLIC / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    package_name = f"{project['package']}-{project['resolution']}-{project['style']}.zip"
    package_path = PACKAGE_DIR / package_name

    with zipfile.ZipFile(package_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for file in sorted(PICON_DIR.glob("*.png")):
            zf.write(file, arcname=file.name)

    version = {
        "schema": 1,
        "version": datetime.now(timezone.utc).strftime("%Y.%m.%d.%H%M%S"),
        "package": f"packages/{package_name}",
        "index": "index.json",
        "count": len(list(PICON_DIR.glob("*.png"))),
    }

    (PUBLIC / "version.json").write_text(
        json.dumps(version, indent=2),
        encoding="utf-8",
    )

    print(f"Built {version['count']} picons -> {PUBLIC}")
    print(f"Package: {package_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
