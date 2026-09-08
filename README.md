<p align="center">
  <img src="assets/readme-banner.svg" alt="Satellite Picons" width="100%">
</p>

<p align="center">
  <a href="https://grgopitic.github.io/satellite-picons/"><strong>Open catalogue</strong></a>
  &nbsp;•&nbsp;
  <a href="https://github.com/GrgoPitic/satellite-picons/releases">Releases</a>
  &nbsp;•&nbsp;
  <a href="LICENSE">MIT License</a>
</p>

---

## Overview

**Satellite Picons** is a curated picon library for Enigma2 satellite receivers. The collection focuses on visual consistency, current channel branding and reliable service-reference naming.

The project is maintained continuously as channel identities and satellite services evolve.

<table>
  <tr>
    <td><strong>Format</strong><br>150×90 PNG</td>
    <td><strong>Platform</strong><br>Enigma2</td>
    <td><strong>Naming</strong><br>Service Reference</td>
    <td><strong>Style</strong><br>Consistent dark picon set</td>
  </tr>
</table>

## Catalogue

Browse the live catalogue, search by channel name or service reference, and download individual variants or the complete package.

<p>
  <a href="https://grgopitic.github.io/satellite-picons/">
    <strong>→ Open Satellite Picons Catalogue</strong>
  </a>
</p>

## Provider packages

The catalogue also publishes operator-specific packages from the same source data used by the website and Enigma2 updater.

- **Skylink** — available automatically from channels tagged with `provider_group: skylink`
- **ANTIK Sat** — prepared in the provider catalogue and becomes downloadable as soon as its channel/service-reference mapping is added

Generated metadata:

- `providers.json` — provider catalogue for the website and clients
- `version.json` — global package metadata and compatibility map
- `packages/*.zip` — full and provider-specific picon archives

The Enigma2 updater can list providers and install only one operator:

```bash
python3 update_picons.py --list
python3 update_picons.py --provider skylink --dest /media/hdd/picon
```

The older positional form remains supported:

```bash
python3 update_picons.py /media/hdd/picon skylink
```

## Collection principles

- current channel logos and branding
- consistent dimensions and visual balance
- service-reference compatible filenames
- individual channel downloads
- complete downloadable package
- ongoing maintenance and logo updates

## Project status

The collection is actively maintained and expanded. Existing channel entries can be updated when broadcasters change branding while preserving their service mapping.

## License & trademarks

Project code is licensed under the [MIT License](LICENSE).

Channel names, logos and trademarks remain the property of their respective owners. Satellite Picons is an independent community project and is not affiliated with or endorsed by any broadcaster or satellite operator.
