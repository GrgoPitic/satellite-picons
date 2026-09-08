# Provider data

This directory contains generated operator channel metadata used by the picon builder, website and Enigma2 clients.

Generated JSON files should not be hand-edited unless an exceptional mapping cannot be represented by the synchronization pipeline. Hand-curated overrides belong in `channels.yml`; they win over generated data for the same DVB service identity.

## Supported providers

### Skylink

```bash
python scripts/sync_provider.py skylink
```

### ANTIK Sat

```bash
python scripts/sync_provider.py antik
```

Both synchronizers currently use:

- SatelitnáTV.sk for operator membership, FastScan order, frequency and DVB SID/TSID/ONID
- picons/picons for service-reference-to-logo mapping and source artwork

## Output

Each provider JSON contains:

- current channel list
- Enigma2 service reference
- satellite position
- FastScan position when available
- frequency
- source update timestamp
- upstream logo mapping
- missing-logo and parsing diagnostics
- synchronization coverage statistics

The GitHub Actions provider workflow validates coverage before committing refreshed data. A failed or incomplete source refresh therefore does not silently replace known-good provider data.
