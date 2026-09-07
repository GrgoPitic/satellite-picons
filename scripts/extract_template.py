#!/usr/bin/env python3
"""Reconstruct the common 150x90 background from an existing picon ZIP."""
from __future__ import annotations
import argparse
import zipfile
from pathlib import Path
import numpy as np
from PIL import Image

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("zipfile", type=Path)
    ap.add_argument("output", type=Path)
    args = ap.parse_args()
    images=[]
    with zipfile.ZipFile(args.zipfile) as z:
        for name in z.namelist():
            if not name.lower().endswith('.png') or name.startswith('__MACOSX/'):
                continue
            with z.open(name) as f:
                im=Image.open(f).convert('RGBA')
                if im.size == (150,90):
                    images.append(np.array(im,dtype=np.uint8))
    if not images:
        raise SystemExit('No 150x90 PNG files found')
    arr=np.stack(images)
    packed=(arr[...,0].astype(np.uint32)<<24)|(arr[...,1].astype(np.uint32)<<16)|(arr[...,2].astype(np.uint32)<<8)|arr[...,3].astype(np.uint32)
    n,h,w=packed.shape
    out=np.empty((h,w),dtype=np.uint32)
    for y in range(h):
        for x in range(w):
            vals,cnt=np.unique(packed[:,y,x],return_counts=True)
            out[y,x]=vals[cnt.argmax()]
    rgba=np.stack([(out>>24)&255,(out>>16)&255,(out>>8)&255,out&255],axis=-1).astype(np.uint8)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba,'RGBA').save(args.output)
    print(f'Wrote {args.output} from {len(images)} picons')

if __name__=='__main__':
    main()
