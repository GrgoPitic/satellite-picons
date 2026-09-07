#!/usr/bin/env python3
"""Zero-dependency OpenPLi updater.

Usage:
  python3 update_picons.py /media/hdd/picon
"""
from __future__ import annotations
import io, json, os, shutil, sys, urllib.request, zipfile

BASE_URL = "https://grgopitic.github.io/satellite-picons"
DEST = sys.argv[1] if len(sys.argv) > 1 else "/media/hdd/picon"

def get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read()

version=json.loads(get(BASE_URL.rstrip('/')+'/version.json'))
blob=get(BASE_URL.rstrip('/')+'/'+version['package'])
os.makedirs(DEST,exist_ok=True)
with zipfile.ZipFile(io.BytesIO(blob)) as z:
    for info in z.infolist():
        if info.is_dir() or not info.filename.lower().endswith('.png'):
            continue
        name=os.path.basename(info.filename)
        with z.open(info) as src, open(os.path.join(DEST,name),'wb') as dst:
            shutil.copyfileobj(src,dst)
print('Updated',version['count'],'picons into',DEST)
