#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "channels.yml"
LOGOS = ROOT / "assets/logos"
SUPPORTED_LOGO_EXTENSIONS = {".png", ".svg", ".jpg", ".jpeg", ".webp"}


def main():
    ap = argparse.ArgumentParser(description="Add/update one channel in channels.yml")
    ap.add_argument("--id", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--logo", required=True, type=Path)
    ap.add_argument(
        "--ref",
        required=True,
        help="Enigma2 service ref, e.g. 1:0:19:334F:C93:3:EB0000:0:0:0:",
    )
    ap.add_argument("--variants", default="1,16,19")
    ap.add_argument("--dark-to-white", default="true", choices=["true", "false"])
    args = ap.parse_args()

    if not args.logo.exists():
        raise SystemExit(f"Logo not found: {args.logo}")

    ext = args.logo.suffix.lower()
    if ext not in SUPPORTED_LOGO_EXTENSIONS:
        raise SystemExit(
            f"Unsupported logo extension: {ext or '(none)'} | "
            f"Supported: {', '.join(sorted(SUPPORTED_LOGO_EXTENSIONS))}"
        )

    cfg = yaml.safe_load(DB.read_text(encoding="utf-8"))
    LOGOS.mkdir(parents=True, exist_ok=True)

    dst = LOGOS / f"{args.id}{ext}"
    shutil.copy2(args.logo, dst)

    entry = {
        "id": args.id,
        "name": args.name,
        "logo": str(dst.relative_to(ROOT)),
        "service_reference": args.ref,
        "variant_types": [x.strip().upper() for x in args.variants.split(",") if x.strip()],
        "dark_to_white": args.dark_to_white == "true",
    }

    channels = cfg.setdefault("channels", [])
    for i, ch in enumerate(channels):
        if ch.get("id") == args.id:
            channels[i] = entry
            break
    else:
        channels.append(entry)

    DB.write_text(
        yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"Updated {DB}: {args.name}")


if __name__ == "__main__":
    main()
