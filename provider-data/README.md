# Provider data

This directory contains generated operator channel metadata.

Do not hand-edit generated provider JSON unless a source has an exceptional
mapping that cannot be represented by the synchronization script.

## Skylink

Generate the current Skylink catalogue:

```bash
python scripts/sync_provider.py skylink
```

The synchronizer uses:

- SatelitnáTV.sk for current operator membership, FastScan order and DVB service IDs
- picons/picons for service-reference-to-logo mapping and source artwork

The build merges generated provider data with manually curated `channels.yml`.
Manual entries win when the same service reference exists in both sources.
