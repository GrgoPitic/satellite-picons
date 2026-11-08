#!/usr/bin/env python3
"""Generate the combined Skylink catalogue from Vhannibal settings, keeping artwork."""
import hashlib
import io
import json
import os
import re
from pathlib import Path
import tempfile
import zipfile
import requests
from catalog_common import (
    channel_identity,
    is_real_station_name,
    load_station_artwork,
    normalize_station_key,
    save_station_artwork,
    service_identity,
)

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://www.vhannibal.net/download_setting.php?action=download&id=6'
DEST = ROOT / 'provider-data/skylink-sk.json'


def parse(blob):
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        if sum(i.file_size for i in z.infolist()) > 40_000_000:
            raise ValueError('Settings archive is too large')
        dbs = [n for n in z.namelist() if n.rsplit('/',1)[-1]=='lamedb']
        if len(dbs)!=1: raise ValueError('Expected one lamedb')
        lines=z.read(dbs[0]).decode('utf-8-sig').splitlines()
        if lines[0]!='eDVB services /4/': raise ValueError('Unsupported lamedb version')
        # Extract physical transponder frequencies from Enigma2 lamedb v4.
        # The FastScan list is independent; compare it against this frequency
        # before assigning a Skylink-specific service reference.
        transponders = {}
        try:
            first = lines.index('transponders') + 1
            last = lines.index('end', first)
            current = None
            for line in lines[first:last]:
                clean = line.strip()
                pieces = clean.split(':')
                if len(pieces) == 3 and all(re.fullmatch(r'[0-9a-fA-F]+', part) for part in pieces):
                    current = tuple(int(part, 16) for part in pieces)
                elif current is not None and clean.lower().startswith('s '):
                    raw_freq = clean[2:].split(':', 1)[0]
                    if raw_freq.isdigit():
                        frequency = round(int(raw_freq) / 1000)
                        if 10000 <= frequency <= 14000:
                            transponders[current] = frequency
        except ValueError:
            pass
        start=lines.index('services')+1; end=lines.index('end',start); services={}
        if (end-start)%3: raise ValueError('Incomplete services section')
        for i in range(start,end,3):
            p=lines[i].split(':');sid,ns,tid,nid=[int(v,16) for v in p[:4]]
            services[(sid,tid,nid,ns)]=lines[i+1]
        # Parse all satellite TV bouquets from the selected Vhannibal settings.
        # The previous importer selected only the CZ/SK General bouquet and
        # therefore incorrectly limited the orbit catalogue to 23.5E.
        bouquets = [n for n in z.namelist()
                    if n.rsplit('/', 1)[-1].startswith('userbouquet.')
                    and n.endswith('.tv')]
        if not bouquets:
            raise ValueError('Vhannibal archive contains no TV bouquets; previous catalogue retained')
        rows = {}
        invalid = 0
        nonstation = 0
        for bouquet_name in sorted(bouquets):
            bouquet = z.read(bouquet_name).decode('utf-8-sig', errors='replace')
            for line in bouquet.splitlines():
                if not line.startswith('#SERVICE 1:0:'):
                    continue
                parts = line[9:].strip().split(':')
                if len(parts) < 10:
                    invalid += 1
                    continue
                try:
                    key = tuple(int(value, 16) for value in parts[3:7])
                except ValueError:
                    invalid += 1
                    continue
                name = services.get(key)
                if not name:
                    # A bouquet can refer to stale or non-satellite services.
                    # Never invent a service from an unresolved reference.
                    invalid += 1
                    continue
                if not is_real_station_name(name):
                    nonstation += 1
                    continue
                orbital_tenths = (key[3] >> 16) & 0xFFFF
                if not (0 < orbital_tenths < 3600):
                    invalid += 1
                    continue
                if orbital_tenths <= 1800:
                    position = f'{orbital_tenths/10:g}E'
                else:
                    position = f'{(3600-orbital_tenths)/10:g}W'
                ref = ':'.join(f'{int(value,16):X}' for value in parts[:10]) + ':'
                station = normalize_station_key(name)
                if key not in rows:
                    rows[key] = {
                        'id': station + '-' + format(key[0], 'x'),
                        'name': name,
                        'station_key': station,
                        'service_reference': ref,
                        'provider_group': 'skylink-sk',
                        'delivery': 'satellite',
                        'variant_types': list(dict.fromkeys([parts[2].upper(), '1', '16', '19'])),
                        'satellite_position': position,
                        'frequency_mhz': transponders.get((key[3], key[1], key[2])),
                    }
        if len(rows) < 50 or len(rows) > 15000:
            raise ValueError(f'Unexpected Vhannibal catalogue size: {len(rows)}; previous catalogue retained')
        positions = sorted(set(row['satellite_position'] for row in rows.values()))
        print(f'Parsed {len(rows)} services from {len(bouquets)} bouquets on {len(positions)} orbits; '
              f'skipped {invalid} invalid/unresolved references and {nonstation} technical placeholders')
        return list(rows.values()), f'Vhannibal TV bouquets ({len(bouquets)} files)'



def sync(blob=None):
    if blob is None:
        with requests.get(URL,timeout=(10,45),stream=True) as response:
            response.raise_for_status(); chunks=[];size=0
            for chunk in response.iter_content(65536):
                size+=len(chunk)
                if size>10_000_000: raise ValueError('Downloaded archive too large')
                chunks.append(chunk)
            blob=b''.join(chunks)
    rows,source=parse(blob)
    # Provider data is metadata-only. User logos and render settings live
    # exclusively in station-artwork.yml / assets/logos and are never copied
    # into synchronized upstream catalogues.
    artwork = load_station_artwork()
    stations = artwork.get("stations") or {}

    new_by_station = {}
    for row in rows:
        key = str(row.get("station_key") or normalize_station_key(row.get("name", "")))
        new_by_station.setdefault(key, []).append(row)

    artwork_changed = False
    for station_key, art in stations.items():
        if not isinstance(art, dict):
            continue
        targets = [str(x) for x in art.get("targets", []) or []]
        skylink_targets = [
            x for x in targets
            if x.startswith("sat:skylink-sk:") or x.startswith("sat:skylink-cz:")
        ]
        if not skylink_targets:
            continue

        candidates = new_by_station.get(str(station_key), [])
        if len(candidates) != 1:
            # Ambiguous or missing upstream match: preserve old assignment.
            continue

        new_identity = channel_identity(candidates[0], "skylink-sk")
        preserved = [
            x for x in targets
            if not (x.startswith("sat:skylink-sk:") or x.startswith("sat:skylink-cz:"))
        ]
        migrated = sorted(set(preserved + [new_identity]))
        if migrated != sorted(set(targets)):
            art["targets"] = migrated
            artwork_changed = True

    if artwork_changed:
        save_station_artwork(artwork)

    for row in rows:
        for field in ("logo", "dark_to_white", "optical_scale", "edge_cleanup", "background_cleanup"):
            row.pop(field, None)

    payload={'provider':'skylink-sk','provider_name':'Skylink SK + CZ','source':{
        'type':'vhannibal','url':URL,'settings':source,'sha256':hashlib.sha256(blob).hexdigest(),
        'artwork_mode':'manual','upstream_logos_imported':False},
        'stats':{'channels_parsed':len(rows),'upstream_logos_imported':0},'channels':rows}
    text=json.dumps(payload,ensure_ascii=False,indent=2)+'\n'
    if DEST.exists() and DEST.read_text()==text:return len(rows)
    fd,path=tempfile.mkstemp(dir=DEST.parent,prefix='.skylink-')
    try:
        with os.fdopen(fd,'w') as out:out.write(text)
        os.replace(path,DEST)
    finally:
        if os.path.exists(path):os.unlink(path)
    return len(rows)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--zip',type=Path);args=parser.parse_args()
    print('Skylink synchronized:',sync(args.zip.read_bytes() if args.zip else None))
