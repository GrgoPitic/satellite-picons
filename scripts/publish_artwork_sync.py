#!/usr/bin/env python3
"""Safely reconcile approved local station artwork with the production tree.

A published logo is defined by station-artwork.yml, not by the latest Git
commit. Reconcile complete curated records, preserving newer production edits
and rejecting equally-dated conflicting edits.
"""
from __future__ import annotations

from pathlib import Path
import shutil
import yaml


def _inside(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Artwork path is outside repository: " + relative)
    return path


def sync_curated_artwork(source_root: Path, target_root: Path) -> list[str]:
    source_root, target_root = Path(source_root), Path(target_root)
    source_yml = source_root / "station-artwork.yml"
    target_yml = target_root / "station-artwork.yml"
    source = yaml.safe_load(source_yml.read_text(encoding="utf-8")) or {}
    target = yaml.safe_load(target_yml.read_text(encoding="utf-8")) or {}
    source_stations = source.get("stations") or {}
    target_stations = target.setdefault("stations", {})
    if not isinstance(source_stations, dict) or not isinstance(target_stations, dict):
        raise ValueError("Invalid station-artwork.yml catalogue")

    changes: list[tuple[str, dict, list[tuple[Path, Path]]]] = []
    for key, entry in source_stations.items():
        if not isinstance(entry, dict):
            continue
        existing = target_stations.get(key)
        if existing == entry:
            continue
        if existing is not None and not isinstance(existing, dict):
            raise ValueError(f"Invalid production artwork for {key}")
        if existing:
            local_ts = int(entry.get("updated_at") or 0)
            main_ts = int(existing.get("updated_at") or 0)
            if local_ts < main_ts:
                continue  # Newer production artwork must not be overwritten.
            if local_ts == main_ts:
                # Target additions from Vhannibal are safely additive.
                comparable_local = {k: v for k, v in entry.items() if k != "targets"}
                comparable_main = {k: v for k, v in existing.items() if k != "targets"}
                if comparable_local != comparable_main:
                    raise ValueError(
                        f"Conflict for {key}: same timestamp but different artwork. "
                        "Resolve manually before publishing."
                    )
        updated = dict(entry)
        updated["targets"] = sorted(set(str(x) for x in (entry.get("targets") or []))
                                    | set(str(x) for x in ((existing or {}).get("targets") or [])))
        if existing == updated:
            continue
        file_pairs: list[tuple[Path, Path]] = []
        for field in ("logo", "source_logo"):
            relative = updated.get(field)
            if not relative:
                continue
            relative = str(relative)
            if not (relative.startswith("assets/logos/") or
                    relative.startswith("assets/source-logos/")):
                raise ValueError(f"Unexpected {field} path in {key}: {relative}")
            src = _inside(source_root, relative)
            dst = _inside(target_root, relative)
            if not src.is_file():
                raise FileNotFoundError(f"Cannot publish {key}: {relative} is missing")
            file_pairs.append((src, dst))
        changes.append((str(key), updated, file_pairs))

    # All conflict and missing-file checks have succeeded before modifications.
    staged_paths = set()
    for key, updated, file_pairs in changes:
        target_stations[key] = updated
        for src, dst in file_pairs:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            staged_paths.add(str(dst.relative_to(target_root)))
    if changes:
        target_yml.write_text(
            yaml.safe_dump(target, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        staged_paths.add("station-artwork.yml")
    return sorted(staged_paths)
