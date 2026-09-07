# Satellite Picons

Free Enigma2 picon builder + static catalogue for satellite TV services and orbital positions.

## Goal

**Satellite Picons** is provider-neutral. Today the seed data can cover one service/orbital position; later the same repository can contain multiple satellites, orbital positions and operators without renaming the project.

Only the maintainer adds original channel logos. The build pipeline converts them into a consistent 150×90 dark picon style, generates multiple Enigma2 service-type filename variants, creates a ZIP package and publishes a searchable static catalogue on GitHub Pages.

No database, VPS or paid hosting is required.

`seed/base-pack.zip` is an optional baseline pack. When present, the builder imports all existing picons and then overlays your maintained replacements/new channels. This makes migration immediate: users get the full existing seed pack plus your fixes.

## Fast start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/build.py
python3 -m http.server 8080 -d public
```

Open `http://localhost:8080`.

## Add a channel

```bash
python scripts/add_channel.py \
  --id joj-krimi \
  --name "JOJ KRIMI" \
  --logo ~/Desktop/joj-krimi.png \
  --ref '1:0:19:334F:C93:3:EB0000:0:0:0:'
python scripts/build.py
```

The default variants are `1`, `16`, and `19`, so one reference produces e.g.:

```text
1_0_1_334F_C93_3_EB0000_0_0_0.png
1_0_16_334F_C93_3_EB0000_0_0_0.png
1_0_19_334F_C93_3_EB0000_0_0_0.png
```

Per-channel variants can be overridden in `channels.yml`.

## Rendering

- exact 150×90 common dark background template reconstructed from the supplied reference pack
- transparent PNG input preferred
- near-white edge-connected backgrounds are removed automatically
- neutral black/dark artwork is converted to white for contrast while coloured brand marks are preserved
- aspect ratio is preserved
- artwork is trimmed, scaled to a 140×80 safe box and centered

## Free publishing with GitHub Pages

1. Create a **public** GitHub repository.
2. Push this project to branch `main`.
3. Repository → **Settings → Pages → Source: GitHub Actions**.
4. Every push automatically rebuilds and deploys the catalogue, individual PNG files and ZIP package.

Expected URL:

```text
https://YOUR_GITHUB_NAME.github.io/YOUR_REPO/
```

## OpenPLi updater

`receiver/update_picons.py` is a zero-dependency Python 3 updater. After the Pages URL is known, change `BASE_URL` and run on OpenPLi:

```bash
python3 update_picons.py /media/hdd/picon
```

A full Enigma2 GUI plugin can use the same `version.json` and package endpoint.

## Files served publicly

```text
/index.json
/version.json
/picons/<service-reference>.png
/packages/satellite-picons-150x90-piconblack.zip
```

## Baseline pack and redistribution

The starter bundle can contain a local `seed/base-pack.zip` supplied by the maintainer. Before publishing that archive or its extracted artwork publicly, verify that its redistribution terms allow it. If not, remove the seed archive and maintain only logo assets you can redistribute.

## Naming and trademark independence

The project name is **Satellite Picons**. Operator and channel names are used only as descriptive metadata where needed. The project is independent and is not affiliated with, sponsored by, or endorsed by any satellite operator or broadcaster.

## Legal note

The MIT licence applies to the code only. Channel names, logos and trademarks remain the property of their respective owners. Only publish logo assets you are entitled to redistribute.


## Private maintainer admin

For adding/updating logos without editing YAML manually, run the local admin on macOS:

```bash
./admin.command
```

It opens:

```text
http://127.0.0.1:8765
```

The form lets the maintainer:

- upload PNG, SVG, JPG, JPEG or WEBP
- enter channel name and Enigma2 service reference
- select service-type variants
- save/update `channels.yml`
- optionally commit and push the change to GitHub automatically

The admin binds only to `127.0.0.1`, so it is not publicly exposed.


## Logo processing and replacement

The local maintainer admin can now preview the final 150×90 picon before publishing and can remove backgrounds in four modes: automatic, simple edge-connected background, AI, or disabled.

Automatic mode keeps already-transparent artwork untouched, removes simple solid backgrounds deterministically, and falls back to local `rembg` AI for complex backgrounds. The AI model is downloaded locally on first use.

Original uploads are stored under `assets/source-logos/`. A processed transparent PNG is stored under `assets/logos/` and is the file used by the public build.

Existing channels can be selected from the admin and their logo can be replaced without re-entering the service reference. `logo_version` and `updated_at` are updated, while Git history keeps prior revisions.
