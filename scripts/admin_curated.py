#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

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

    return page


# admin_v2 registered its routes during import. The route functions resolve these
# globals at request time, so replacing them here safely changes the live app.
hub.load_admin_channels_v2 = load_curated_channels
hub.legacy.load_admin_channels = load_curated_channels
hub.PAGE_V2 = page_curated


def main() -> None:
    hub.main()


if __name__ == "__main__":
    main()
