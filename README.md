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

Browse the live catalogue, search by channel name or service reference, and download individual variants, complete provider packages or a custom package generated from your own Enigma2 bouquet files.

<p>
  <a href="https://grgopitic.github.io/satellite-picons/">
    <strong>→ Open Satellite Picons Catalogue</strong>
  </a>
</p>

### Custom "My channels" package

For available providers the website can read local `userbouquet*.tv` / `userbouquet*.radio` files directly in the browser, match their DVB service references against the catalogue and create a ZIP containing only matching picons.

Bouquet files are processed locally in the browser and are not uploaded to the project.

## Provider packages

Provider catalogues are generated from current operator/transponder metadata and the same result is used by the website, package builder and Enigma2 clients.

- **Skylink** — synchronized automatically
- **ANTIK Sat** — synchronized automatically
- additional providers can be added through `providers.yml`

Generated metadata:

- `provider-data/*.json` — normalized operator channel/service-reference data
- `providers.json` — provider catalogue for the website and clients
- `version.json` — global package metadata and compatibility map
- `packages/*.zip` — full and provider-specific picon archives

The provider synchronization workflow refreshes supported operator catalogues daily and after changes to synchronization configuration.

## Enigma2

The GUI plugin can install one provider in three modes:

- complete provider package
- only channels found in local Enigma2 bouquets
- update only picons already present in the selected picon directory

The command-line updater can also list and install provider packages:

```bash
python3 update_picons.py --list
python3 update_picons.py --provider skylink --dest /media/hdd/picon
python3 update_picons.py --provider antik --dest /media/hdd/picon
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
- provider-specific packages
- browser-generated packages from local bouquets
- ongoing automated metadata synchronization

## Project status

The collection is actively maintained and expanded. Existing channel entries can be updated when broadcasters change branding while preserving their service mapping. Manually curated channel entries override generated provider data for the same DVB service.

## License & trademarks

Project code is licensed under the [MIT License](LICENSE).

Channel names, logos and trademarks remain the property of their respective owners. Satellite Picons is an independent community project and is not affiliated with or endorsed by any broadcaster or satellite operator.
