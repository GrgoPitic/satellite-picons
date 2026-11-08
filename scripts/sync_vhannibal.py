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
from catalog_common import normalize_station_key, service_identity

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
    import yaml
    import build_v2
    cfg=yaml.safe_load((ROOT/'channels.yml').read_text())
    old,_=build_v2.merged_channels_v2(cfg)
    fields=['logo','dark_to_white','optical_scale','edge_cleanup']
    by_ref={};by_name={}
    for ch in old:
        if ch.get('provider_group') not in {'skylink-sk','skylink-cz'} or not ch.get('logo'):continue
        style={k:ch[k] for k in fields if k in ch}
        by_ref.setdefault(service_identity(ch.get('service_reference','')),[]).append(style)
        by_name.setdefault(normalize_station_key(ch['name']),[]).append(style)
    for row in rows:
        choices=by_ref.get(service_identity(row['service_reference'])) or by_name.get(row['station_key'],[])
        unique={json.dumps(v,sort_keys=True):v for v in choices}
        if len(unique)==1: row.update(next(iter(unique.values())))
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
