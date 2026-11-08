#!/usr/bin/env python3
"""Generate the combined Skylink catalogue from Vhannibal settings, keeping artwork."""
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import zipfile
import requests
from catalog_common import (
    channel_identity,
    load_station_artwork,
    normalize_station_key,
    save_station_artwork,
    service_identity,
)

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://www.vhannibal.net/download_setting.php?action=download&id=6'
DEST = ROOT / 'provider-data/skylink-sk.json'
STATE_DIR = ROOT / '.admin-state'
CHANGE_REPORT = STATE_DIR / 'vhannibal-changes.json'


def parse(blob):
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        if sum(i.file_size for i in z.infolist()) > 40_000_000:
            raise ValueError('Settings archive is too large')
        dbs = [n for n in z.namelist() if n.rsplit('/',1)[-1]=='lamedb']
        if len(dbs)!=1: raise ValueError('Expected one lamedb')
        lines=z.read(dbs[0]).decode('utf-8-sig').splitlines()
        if lines[0]!='eDVB services /4/': raise ValueError('Unsupported lamedb version')
        start=lines.index('services')+1; end=lines.index('end',start); services={}
        if (end-start)%3: raise ValueError('Incomplete services section')
        for i in range(start,end,3):
            p=lines[i].split(':');sid,ns,tid,nid=[int(v,16) for v in p[:4]]
            services[(sid,tid,nid,ns)]=lines[i+1]
        candidates=[]
        for n in z.namelist():
            if not n.endswith('.tv') or 'userbouquet' not in n: continue
            text=z.read(n).decode('utf-8-sig')
            if 'General Czech Republic' in text and 'General Slovakia' in text: candidates.append((n,text))
        if len(candidates)!=1: raise ValueError('Cannot uniquely identify the Czech/Slovak bouquet; previous catalogue retained')
        rows={}; section=''
        for line in candidates[0][1].splitlines():
            if line.startswith('#DESCRIPTION '): section=line
            if not line.startswith('#SERVICE 1:0:'): continue
            p=line[9:].strip().split(':')
            if len(p)<10: raise ValueError('Invalid bouquet reference')
            key=tuple(int(v,16) for v in p[3:7]);name=services.get(key)
            if not name: raise ValueError('Bouquet service missing in lamedb')
            ref=':'.join(f'{int(v,16):X}' for v in p[:10])+':'
            station=normalize_station_key(name)
            rows[key]={'id':station+'-'+format(key[0],'x'),'name':name,'station_key':station,
                       'service_reference':ref,'provider_group':'skylink-sk','delivery':'satellite',
                       'variant_types':list(dict.fromkeys([p[2].upper(),'1','16','19'])),
                       'satellite_position':f'{(key[3]>>16)/10:g}E'}
        if len(rows)<50: raise ValueError('Unexpectedly small Skylink catalogue; previous catalogue retained')
        return list(rows.values()),candidates[0][0]


def _identity_map(rows):
    return {channel_identity(row, str(row.get("provider_group") or "skylink-sk")): row for row in rows}


def _unique_station_map(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault(str(row.get("station_key") or normalize_station_key(row.get("name", ""))), []).append(row)
    return {key: values[0] for key, values in grouped.items() if len(values) == 1}


def build_change_report(old_rows, new_rows, *, source, sha256, migrated_artwork=0):
    old_by_id = _identity_map(old_rows)
    new_by_id = _identity_map(new_rows)
    old_station = _unique_station_map(old_rows)
    new_station = _unique_station_map(new_rows)

    renamed = []
    metadata_changed = []
    for identity in sorted(set(old_by_id) & set(new_by_id)):
        old = old_by_id[identity]
        new = new_by_id[identity]
        if str(old.get("name") or "") != str(new.get("name") or ""):
            renamed.append({
                "identity": identity,
                "old_name": old.get("name"),
                "new_name": new.get("name"),
            })
        changed_fields = []
        for field in ("satellite_position", "variant_types"):
            if old.get(field) != new.get(field):
                changed_fields.append(field)
        if changed_fields:
            metadata_changed.append({
                "identity": identity,
                "name": new.get("name") or old.get("name"),
                "fields": changed_fields,
            })

    tuning_changed = []
    moved_old_ids = set()
    moved_new_ids = set()
    for station_key in sorted(set(old_station) & set(new_station)):
        old = old_station[station_key]
        new = new_station[station_key]
        old_id = channel_identity(old, str(old.get("provider_group") or "skylink-sk"))
        new_id = channel_identity(new, str(new.get("provider_group") or "skylink-sk"))
        if old_id != new_id:
            moved_old_ids.add(old_id)
            moved_new_ids.add(new_id)
            tuning_changed.append({
                "station_key": station_key,
                "name": new.get("name") or old.get("name"),
                "old_identity": old_id,
                "new_identity": new_id,
                "old_reference": old.get("service_reference"),
                "new_reference": new.get("service_reference"),
            })

    added = [
        {"identity": identity, "name": new_by_id[identity].get("name")}
        for identity in sorted(set(new_by_id) - set(old_by_id) - moved_new_ids)
    ]
    removed = [
        {"identity": identity, "name": old_by_id[identity].get("name")}
        for identity in sorted(set(old_by_id) - set(new_by_id) - moved_old_ids)
    ]

    report = {
        "synced_at": __import__("time").time_ns() // 1_000_000_000,
        "source": source,
        "sha256": sha256,
        "previous_channels": len(old_rows),
        "current_channels": len(new_rows),
        "changed": bool(added or removed or renamed or tuning_changed or metadata_changed),
        "counts": {
            "added": len(added),
            "removed": len(removed),
            "renamed": len(renamed),
            "tuning_changed": len(tuning_changed),
            "metadata_changed": len(metadata_changed),
            "artwork_assignments_updated": int(migrated_artwork),
        },
        "added": added,
        "removed": removed,
        "renamed": renamed,
        "tuning_changed": tuning_changed,
        "metadata_changed": metadata_changed,
    }
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    CHANGE_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


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
    artwork_assignments_updated = 0
    for station_key, art in stations.items():
        if not isinstance(art, dict):
            continue
        targets = [str(x) for x in art.get("targets", []) or []]
        candidates = new_by_station.get(str(station_key), [])
        if not candidates:
            continue

        # Every exact station_key match gets the existing curated artwork.
        # Old Skylink identities are dropped when tuning changes, while targets
        # belonging to other operators are preserved.
        new_identities = {
            channel_identity(candidate, "skylink-sk")
            for candidate in candidates
        }
        preserved = [
            x for x in targets
            if not (x.startswith("sat:skylink-sk:") or x.startswith("sat:skylink-cz:"))
        ]
        migrated = sorted(set(preserved) | new_identities)
        before = set(targets)
        if set(migrated) != before:
            art["targets"] = migrated
            artwork_changed = True
            artwork_assignments_updated += len(set(migrated) - before)

    if artwork_changed:
        save_station_artwork(artwork)

    for row in rows:
        for field in ("logo", "dark_to_white", "optical_scale", "edge_cleanup", "background_cleanup"):
            row.pop(field, None)

    old_rows = []
    if DEST.exists():
        try:
            old_rows = (json.loads(DEST.read_text(encoding="utf-8")) or {}).get("channels", []) or []
        except Exception:
            old_rows = []

    digest = hashlib.sha256(blob).hexdigest()
    build_change_report(
        old_rows, rows, source=source, sha256=digest,
        migrated_artwork=artwork_assignments_updated,
    )

    payload={'provider':'skylink-sk','provider_name':'Skylink SK + CZ','source':{
        'type':'vhannibal','url':URL,'settings':source,'sha256':digest,
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
