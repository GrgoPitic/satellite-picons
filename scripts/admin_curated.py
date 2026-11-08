#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from catalog_common import is_real_station_name
import admin_v2 as hub

ROOT = Path(__file__).resolve().parents[1]
LOGOS_ROOT = (ROOT / "assets" / "logos").resolve()

_ORIGINAL_LOAD = hub.load_admin_channels_v2
_ORIGINAL_PAGE = hub.PAGE_V2


def _is_local_user_logo(path_value: str) -> bool:
    """Return True only for a real logo stored in our local assets/logos tree."""
    if not path_value:
        return False
    try:
        path = (ROOT / path_value).resolve()
        path.relative_to(LOGOS_ROOT)
    except (OSError, ValueError):
        return False
    return path.is_file()


def load_curated_channels() -> tuple[list[dict], dict]:
    """Keep provider metadata, but never expose automatically imported artwork.

    The provider catalogue is still useful for selecting a channel and filling its
    DVB/IPTV metadata. Artwork in the admin, however, must come only from files
    stored under assets/logos (manual uploads / curated local artwork).
    """
    rows, stats = _ORIGINAL_LOAD()
    # Only stations currently present in Vhannibal are active; preserve all
    # historical artwork and archived operator catalogues on disk.
    rows = [row for row in rows if row.get("provider_group") == "skylink-sk"
            and row.get("_generated")
            # Use the same conservative filter as the Vhannibal importer.
            and is_real_station_name(row.get("name") or "")]
    # Vhannibal defines DVB existence, NOT Skylink operator membership.
    # Attach only independently verified SK/CZ FastScan memberships.
    from operator_membership import load_operator_membership
    memberships = load_operator_membership(rows)
    for row in rows:
        reference = str(row.get("service_reference") or "").upper()
        slots = memberships.get(reference, [])
        row["_operators"] = sorted({slot["operator"] for slot in slots})
        row["_operator_slots"] = slots
        row["_catalogue_source"] = "vhannibal"
    hidden_imported = 0
    local_logos = 0

    for row in rows:
        # logo_url is supplied by the automatic provider synchronisation. It is
        # metadata only and must not become the visible/editable admin artwork.
        if row.pop("logo_url", None):
            hidden_imported += 1
        row.pop("source_logo", None)

        local_logo = str(row.get("logo") or "").strip()
        if local_logo and _is_local_user_logo(local_logo):
            local_logos += 1
        elif local_logo:
            # Never display arbitrary external/non-local paths as curated logos.
            row.pop("logo", None)

    stats = dict(stats)
    stats["local_logos"] = local_logos
    stats["total"] = len(rows)
    stats["generated"] = len(rows)
    stats["curated"] = local_logos
    stats["missing_logo"] = len(rows) - local_logos
    stats["satellite"] = len(rows)
    stats["iptv"] = 0
    stats["providers"] = 2
    stats["verified_skylink_sk"] = sum("skylink-sk" in row["_operators"] for row in rows)
    stats["verified_skylink_cz"] = sum("skylink-cz" in row["_operators"] for row in rows)
    stats["hidden_imported_logos"] = hidden_imported
    return rows, stats


def page_curated() -> str:
    page = _ORIGINAL_PAGE()

    # Saving a logo must be immediate. Git operations are intentionally moved to
    # the dedicated Publish section so an upload cannot appear frozen while a
    # fetch/rebase/push is running in the same request.
    page = page.replace('name="publish" checked', 'name="publish"')
    page = page.replace(
        "Po uložení automaticky commitnúť a pushnúť na GitHub",
        "Publikovanie spusti samostatne v sekcii „Publikovanie“",
    )
    page = page.replace("Uložiť zmeny a publikovať", "Uložiť zmeny lokálne")

    # Make the artwork policy explicit in the UI.
    page = page.replace(
        "nový obrázok alebo kopírovanie",
        "iba tvoje lokálne logá",
    )
    page = page.replace(
        "Vyber súbor alebo prevezmi logo z iného providera.",
        "Vyber vlastný súbor alebo použi už uložené lokálne logo.",
    )
    page = page.replace(
        "Táto sekcia rieši iba zdroj obrázka. Úpravy vzhľadu sú samostatne v „Upraviť logo“.",
        "Nahraj vlastné logo. Automaticky synchronizované logá providerov sa tu nepoužívajú.",
    )
    page = page.replace(
        "const logo=ch.logo || ch.logo_url || 'bez loga';",
        "const logo=ch.logo || 'bez vlastného loga';",
    )

    page = page.replace("ručných override", "vlastných úprav")
    page = page.replace("providerov", "operátorov")
    page = page.replace("GitHub commit a push", "odoslať uložené zmeny na web")
    page = page.replace("Odstrániť override", "Odstrániť vlastnú úpravu")
    page = page.replace(
        '<h1>Prehľad</h1><p class="sub">Vyber vľavo, čo chceš práve riešiť. Ostatné nástroje sa skryjú.</p>',
        '<h1>Moje picony</h1><p class="sub">1. Vyber stanicu. 2. Nahraj a skontroluj logo. 3. Priraď ho ďalším service reference. 4. Publikuj po schválení.</p>'
    )
    page = page.replace(
        '<h2>Publikovanie</h2>',
        '<h2>Odoslať picony na web</h2><p>Uložiť znamená uložiť do tohto počítača. Publikovanie odošle zmeny do repozitára. Po úspešnom zostavení a nasadení vetvy main sa nový balík sprístupní na webe aj prijímaču OpenPLi.</p>'
    )
    from station_dashboard import enhance
    return enhance(page)


# admin_v2 registered its routes during import. The route functions resolve these
# globals at request time, so replacing them here safely changes the live app.
hub.load_admin_channels_v2 = load_curated_channels
hub.legacy.load_admin_channels = load_curated_channels
hub.PAGE_V2 = page_curated


@hub.legacy.app.get("/api/station-picon")
def station_picon():
    import io
    from flask import request, send_file, jsonify
    row = hub.channel_by_identity(request.args.get("identity", ""))
    if not row or not _is_local_user_logo(str(row.get("logo") or "")):
        return jsonify(error="Logo sa nenašlo."), 404
    path = ROOT / row["logo"]
    png = hub.legacy.render_preview_png(
        raw=path.read_bytes(), ext=path.suffix.lower(),
        dark_to_white=bool(row.get("dark_to_white", False)),
        optical_scale=float(row.get("optical_scale", 1)),
        edge_cleanup=bool(row.get("edge_cleanup", False)),
    )
    return send_file(io.BytesIO(png), mimetype="image/png")


@hub.legacy.app.get("/api/catalogue-changes")
def catalogue_changes():
    import json
    from flask import jsonify
    report = ROOT / "catalogue-changes.json"
    try:
        data = json.loads(report.read_text(encoding="utf-8")) if report.is_file() else {"schema": 1, "events": []}
    except (OSError, ValueError):
        data = {"schema": 1, "events": []}
    response = jsonify(data)
    response.headers["Cache-Control"] = "no-store"
    return response


from vhannibal_check import register
register(hub.legacy.app, load_curated_channels)


def main() -> None:
    from sync_vhannibal import sync
    try:
        print("Vhannibal: aktualizovaných", sync(), "satelitných DVB služieb.")
    except Exception as exc:
        print("Vhannibal nedostupný; používam posledný uložený katalóg:", exc)
    hub.main()


if __name__ == "__main__":
    main()
