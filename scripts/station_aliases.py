#!/usr/bin/env python3
"""Conservative curated-logo aliases for verified rebrands and feed labels.

Never infer DVB membership or merge distinct channels based on generic tokens.
This only determines which approved artwork may be reused across services.
"""
from __future__ import annotations

from catalog_common import normalize_station_key

# Verified FilmBox+ branding variants used by Skylink and 16E feeds.
# Do not collapse other channel brands, locales or generic '24' suffixes.
_ALIASES = {
    "filmbox-plus-love-and-crime": "filmbox-plus-love-crime",
    "filmbox-plus-love-crime": "filmbox-plus-love-crime",
    "filmbox-plus-love-crime-adria": "filmbox-plus-love-crime",
    "filmbox-love-crime": "filmbox-plus-love-crime",
    "filmbox-love-crime-adria": "filmbox-plus-love-crime",
}

def artwork_family(value: str) -> str:
    key = normalize_station_key(value)
    return _ALIASES.get(key, key)


def unique_family_artwork(name: str, stations: dict) -> tuple[str, dict] | None:
    wanted = artwork_family(name)
    matches = [
        (str(key), art) for key, art in stations.items()
        if isinstance(art, dict) and art.get("logo")
        and artwork_family(str(key)) == wanted
    ]
    return matches[0] if len(matches) == 1 else None
