#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import os
import time
from pathlib import Path

import yaml
from flask import jsonify, redirect, render_template_string, request, send_file, url_for, flash
from werkzeug.utils import secure_filename

import admin as legacy
from catalog_common import (
    ARTWORK_CONFIG,
    channel_identity,
    load_station_artwork,
    normalize_station_key,
    provider_definitions,
    save_station_artwork,
)

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "channels.yml"
PROVIDER_DATA_DIR = ROOT / "provider-data"
STATION_LOGOS = ROOT / "assets" / "logos" / "stations"


def provider_groups_v2() -> list[tuple[str, str]]:
    defs = provider_definitions()
    result = []
    for provider_id, meta in defs.items():
        delivery = str(meta.get("delivery") or "satellite").lower()
        tag = "IPTV" if delivery == "iptv" else "SAT"
        result.append((provider_id, f"{meta.get('name') or provider_id} · {tag}"))
    return sorted(result, key=lambda item: item[1].lower())


def load_admin_channels_v2() -> tuple[list[dict], dict]:
    cfg = yaml.safe_load(DB.read_text(encoding="utf-8")) or {"channels": []}
    defs = provider_definitions()
    merged: dict[str, dict] = {}
    generated_count = 0

    if PROVIDER_DATA_DIR.exists():
        for path in sorted(PROVIDER_DATA_DIR.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            provider_id = str(payload.get("provider") or path.stem).strip().lower()
            for channel in payload.get("channels", []) or []:
                item = dict(channel)
                item["provider_group"] = str(item.get("provider_group") or provider_id).strip().lower()
                item["delivery"] = str(defs.get(item["provider_group"], {}).get("delivery") or "satellite")
                item["station_key"] = str(item.get("station_key") or normalize_station_key(item.get("name", "")))
                item["_generated"] = True
                item["_manual_override"] = False
                key = channel_identity(item, item["provider_group"])
                merged[key] = item
                generated_count += 1

    for channel in cfg.get("channels", []) or []:
        item = dict(channel)
        provider_id = str(item.get("provider_group") or "").strip().lower()
        item["delivery"] = str(item.get("delivery") or defs.get(provider_id, {}).get("delivery") or "satellite")
        item["station_key"] = str(item.get("station_key") or normalize_station_key(item.get("name", "")))
        key = channel_identity(item, provider_id)
        base = dict(merged.get(key, {}))
        base.update(item)
        base["_generated"] = key in merged
        base["_manual_override"] = True
        merged[key] = base

    artwork = load_station_artwork().get("stations") or {}
    rows = []
    for identity, item in merged.items():
        row = dict(item)
        row["_identity"] = identity
        row["_service_key"] = legacy.service_identity(row.get("service_reference", ""))
        art = artwork.get(row["station_key"])
        if isinstance(art, dict):
            targets = set(str(x) for x in art.get("targets", []) or [])
            if identity in targets:
                row["_shared_artwork"] = True
                if art.get("logo"):
                    row["logo"] = art["logo"]
                for field in ("dark_to_white", "optical_scale", "edge_cleanup", "background_cleanup"):
                    if field in art:
                        row[field] = art[field]
        rows.append(row)

    rows.sort(key=lambda ch: (
        str(ch.get("delivery") or ""),
        str(ch.get("provider_group") or ""),
        int(ch.get("fastscan") or 99999),
        str(ch.get("name") or "").lower(),
    ))

    providers = {str(ch.get("provider_group") or "") for ch in rows if ch.get("provider_group")}
    stats = {
        "total": len(rows),
        "generated": generated_count,
        "overrides": sum(1 for ch in rows if ch.get("_manual_override")),
        "providers": len(set(provider_definitions()) | providers),
        "satellite": sum(1 for ch in rows if ch.get("delivery") != "iptv"),
        "iptv": sum(1 for ch in rows if ch.get("delivery") == "iptv"),
    }
    return rows, stats


def matching_channels(name: str, exclude_identity: str = "") -> list[dict]:
    station_key = normalize_station_key(name)
    rows, _ = load_admin_channels_v2()
    result = []
    seen = set()
    for row in rows:
        identity = str(row.get("_identity") or "")
        if not identity or identity == exclude_identity or identity in seen:
            continue
        if str(row.get("station_key") or "") != station_key:
            continue
        seen.add(identity)
        result.append({
            "identity": identity,
            "name": row.get("name"),
            "provider_group": row.get("provider_group"),
            "delivery": row.get("delivery") or "satellite",
            "satellite_position": row.get("satellite_position"),
            "tvg_id": row.get("tvg_id"),
            "has_logo": bool(row.get("logo")),
        })
    return result


def save_shared_logo(*, station_key: str, raw: bytes, ext: str) -> str:
    if ext not in legacy.SUPPORTED:
        raise ValueError("Nepodporovaný formát loga.")
    STATION_LOGOS.mkdir(parents=True, exist_ok=True)
    try:
        image = legacy.prepare_logo(raw, ext)
    except RuntimeError as exc:
        if ext == ".svg":
            raise ValueError("SVG sa na Macu nepodarilo spracovať. Použi PNG alebo oprav lokálny SVG renderer.") from exc
        raise
    destination = STATION_LOGOS / f"{station_key}.png"
    image.save(destination, format="PNG", optimize=True)
    return str(destination.relative_to(ROOT))


def publish_v2() -> str:
    stage = legacy.run_git("add", "-A", "station-artwork.yml", "iptv-providers.yml")
    if stage.returncode != 0:
        raise RuntimeError(stage.stderr.strip() or "Nepodarilo sa pridať Picon Hub dáta do commitu.")
    return ORIGINAL_PUBLISH()


def channel_by_identity(identity: str) -> dict | None:
    rows, _ = load_admin_channels_v2()
    return next((row for row in rows if row.get("_identity") == identity), None)


def PAGE_V2() -> str:
    page = legacy.PAGE
    page = page.replace("Satellite Picons Admin", "Picon Hub Admin")
    page = page.replace("<strong>Satellite Picons</strong>", "<strong>Picon Hub</strong>")
    page = page.replace("<span>Admin pracovisko</span>", "<span>SAT + IPTV · spoločné logá</span>")
    page = page.replace(
        '<input id="serviceRef" name="service_reference" placeholder="1:0:19:334F:C93:3:EB0000:0:0:0:" required>',
        '<input id="serviceRef" name="service_reference" placeholder="1:0:19:334F:C93:3:EB0000:0:0:0:">'
    )
    page = page.replace(
        '<div><label>Skupina / balík</label><select id="providerGroup" name="provider_group">',
        '<div><label>Typ príjmu</label><select id="delivery" name="delivery"><option value="satellite">Satelit</option><option value="iptv">IPTV</option></select></div><div><label>Provider</label><select id="providerGroup" name="provider_group">'
    )
    page = page.replace(
        '<label>Enigma2 service reference</label>\n            <input id="serviceRef"',
        '<label>Enigma2 service reference <span style="color:#6f7d8e">(SAT povinné, IPTV voliteľné)</span></label>\n            <input id="serviceRef"'
    )
    page = page.replace(
        '<label>Varianty service type</label>\n            <input name="variants" value="1,16,19">',
        '<div class="grid"><div><label>IPTV tvg-id</label><input id="tvgId" name="tvg_id" placeholder="markiza.sk"></div><div><label>IPTV interné ID</label><input id="channelUid" name="channel_uid" placeholder="markiza"></div></div><label>Varianty service type</label>\n            <input name="variants" value="1,16,19">'
    )
    page = page.replace(
        '<div class="status">Vybraný súbor zostane pripravený aj po prepnutí do sekcie „Upraviť logo“.</div>',
        '<div class="status">Vybraný súbor zostane pripravený aj po prepnutí do sekcie „Upraviť logo“.</div><div id="shareMatches" class="copy-logo" style="display:none"><strong>Rovnaká stanica je aj u ďalších providerov</strong><p class="note">Zaškrtni, kde sa má použiť rovnaké logo. Funguje spoločne pre SAT aj IPTV.</p><div id="shareMatchesList"></div></div><input type="hidden" id="currentIdentity" name="current_identity" value="">'
    )
    page = page.replace("'/api/logo/'+encodeURIComponent(ch._service_key||'')", "'/api/v2/logo?identity='+encodeURIComponent(ch._identity||'')")
    page = page.replace("'/api/logo/'+encodeURIComponent(ch._service_key||'')", "'/api/v2/logo?identity='+encodeURIComponent(ch._identity||'')")

    extra_js = r'''
<script>
const providerMeta={{ provider_meta|tojson }};
const deliverySelect=document.querySelector('#delivery');
const tvgId=document.querySelector('#tvgId');
const channelUid=document.querySelector('#channelUid');
const currentIdentity=document.querySelector('#currentIdentity');
const shareMatches=document.querySelector('#shareMatches');
const shareMatchesList=document.querySelector('#shareMatchesList');

function syncDeliveryFromProvider(){
  const p=providerMeta[providerGroup.value]||{};
  if(deliverySelect && p.delivery) deliverySelect.value=p.delivery;
}
if(providerGroup) providerGroup.addEventListener('change',syncDeliveryFromProvider);

async function refreshSharedMatches(ch){
  if(!shareMatches || !shareMatchesList) return;
  const name=(ch && ch.name) || document.querySelector('#channelName').value || '';
  const identity=(ch && ch._identity) || (currentIdentity ? currentIdentity.value : '');
  if(name.trim().length<2){shareMatches.style.display='none';shareMatchesList.innerHTML='';return;}
  try{
    const r=await fetch('/api/station-matches?name='+encodeURIComponent(name)+'&exclude='+encodeURIComponent(identity));
    const data=await r.json();
    const matches=data.matches||[];
    if(!matches.length){shareMatches.style.display='none';shareMatchesList.innerHTML='';return;}
    shareMatchesList.innerHTML=matches.map(m=>
      '<label class="check" style="margin-top:9px"><input type="checkbox" name="share_target" value="'+esc(m.identity)+'" checked> '+
      esc(m.name)+' · '+esc(m.provider_group||'')+' · '+(m.delivery==='iptv'?'IPTV':'SAT')+
      (m.satellite_position?' · '+esc(m.satellite_position):'')+'</label>'
    ).join('');
    shareMatches.style.display='block';
  }catch(e){shareMatches.style.display='none';}
}

if(manageChannel){
  manageChannel.addEventListener('change',()=>{
    const idx=manageChannel.value === '' ? -1 : Number(manageChannel.value);
    const ch=idx>=0 ? adminChannels[idx] : null;
    if(!ch) return;
    if(deliverySelect) deliverySelect.value=ch.delivery||'satellite';
    if(tvgId) tvgId.value=ch.tvg_id||'';
    if(channelUid) channelUid.value=ch.channel_uid||'';
    if(currentIdentity) currentIdentity.value=ch._identity||'';
    refreshSharedMatches(ch);
  });
}
const channelNameV2=document.querySelector('#channelName');
if(channelNameV2){
  let matchTimer=null;
  channelNameV2.addEventListener('input',()=>{
    clearTimeout(matchTimer);
    matchTimer=setTimeout(()=>refreshSharedMatches(null),300);
  });
}
</script>
'''
    return page.replace("</body>", extra_js + "</body>")


@legacy.app.get("/api/station-matches")
def api_station_matches():
    name = request.args.get("name", "").strip()
    exclude = request.args.get("exclude", "").strip()
    return jsonify(station_key=normalize_station_key(name), matches=matching_channels(name, exclude))


@legacy.app.get("/api/v2/logo")
def api_v2_logo():
    identity = request.args.get("identity", "").strip()
    channel = channel_by_identity(identity)
    if not channel or not channel.get("logo"):
        return jsonify(error="Logo sa nenašlo."), 404
    path = (ROOT / str(channel["logo"])).resolve()
    if not path.is_file():
        return jsonify(error="Logo sa nenašlo."), 404
    return send_file(path)


def index_v2():
    if request.method == "GET":
        channels, stats = load_admin_channels_v2()
        defs = provider_definitions()
        provider_meta = {
            pid: {"name": meta.get("name") or pid, "delivery": meta.get("delivery") or "satellite"}
            for pid, meta in defs.items()
        }
        return render_template_string(
            PAGE_V2(),
            channels=channels,
            stats=stats,
            satellite_positions=legacy.SATELLITE_POSITIONS,
            provider_groups=provider_groups_v2(),
            provider_defaults={},
            provider_meta=provider_meta,
            branch=legacy.git_branch(),
            preview_ready=legacy.local_preview_ready(),
        )

    try:
        cfg = yaml.safe_load(DB.read_text(encoding="utf-8")) or {"channels": []}
        channels = cfg.setdefault("channels", [])
        defs = provider_definitions()

        channel_id = request.form.get("channel_id", "").strip().lower()
        name = request.form.get("name", "").strip()
        provider_group = request.form.get("provider_group", "").strip().lower()
        delivery = request.form.get("delivery", "").strip().lower() or str(defs.get(provider_group, {}).get("delivery") or "satellite")
        ref = request.form.get("service_reference", "").strip()
        tvg_id = request.form.get("tvg_id", "").strip()
        channel_uid = request.form.get("channel_uid", "").strip() or channel_id
        satellite_position = legacy.normalize_orbit(request.form.get("satellite_position", "").strip())
        variants = [x.strip().upper() for x in request.form.get("variants", "1,16,19").split(",") if x.strip()]
        dark_to_white = request.form.get("dark_to_white", "false") == "true"
        edge_cleanup = request.form.get("edge_cleanup") == "on"
        optical_scale = float(request.form.get("optical_scale", "1.0"))
        publish = request.form.get("publish") == "on"

        if not legacy.ID_RE.match(channel_id):
            raise ValueError("ID môže obsahovať iba malé písmená, čísla a pomlčky.")
        if not name:
            raise ValueError("Názov kanála je povinný.")
        if not provider_group:
            raise ValueError("Vyber providera.")
        if delivery not in {"satellite", "iptv"}:
            raise ValueError("Neplatný typ príjmu.")
        if delivery == "satellite":
            if not ref:
                raise ValueError("Satelitný kanál musí mať Enigma2 service reference.")
            legacy.validate_ref(ref)
        elif not (tvg_id or channel_uid):
            raise ValueError("IPTV kanál musí mať tvg-id alebo interné ID.")
        if not 0.50 <= optical_scale <= 1.50:
            raise ValueError("Veľkosť loga musí byť medzi 0.50 a 1.50.")

        probe = {
            "id": channel_id,
            "name": name,
            "provider_group": provider_group,
            "delivery": delivery,
            "service_reference": ref or None,
            "tvg_id": tvg_id or None,
            "channel_uid": channel_uid or None,
        }
        identity = channel_identity(probe, provider_group)
        existing_index = next((i for i, ch in enumerate(channels) if channel_identity(ch, ch.get("provider_group")) == identity), None)
        existing = dict(channels[existing_index]) if existing_index is not None else {}

        station_key = normalize_station_key(name)
        entry = dict(existing)
        entry.update({
            "id": channel_id,
            "name": name,
            "station_key": station_key,
            "delivery": delivery,
            "provider_group": provider_group,
            "dark_to_white": dark_to_white,
            "optical_scale": optical_scale,
            "edge_cleanup": edge_cleanup,
            "background_cleanup": True,
        })
        if delivery == "satellite":
            entry["service_reference"] = ref
            entry["variant_types"] = variants or ["1", "16", "19"]
            entry["satellite_position"] = satellite_position or None
            entry.pop("tvg_id", None)
            entry.pop("channel_uid", None)
        else:
            entry["tvg_id"] = tvg_id or None
            entry["channel_uid"] = channel_uid
            if ref:
                entry["service_reference"] = ref
                entry["variant_types"] = variants or ["4097"]
            else:
                entry.pop("service_reference", None)
                entry.pop("variant_types", None)
            entry.pop("satellite_position", None)

        upload = request.files.get("logo")
        copy_ref = request.form.get("copy_logo_from_ref", "").strip()
        raw = None
        ext = None
        if upload and upload.filename:
            filename = secure_filename(upload.filename or "")
            ext = Path(filename).suffix.lower()
            raw = upload.read()
        elif copy_ref:
            source = legacy.effective_channel_by_ref(copy_ref)
            if source:
                raw, ext = legacy.read_effective_logo(source)

        if raw:
            if not raw:
                raise ValueError("Logo je prázdne.")
            logo_rel = save_shared_logo(station_key=station_key, raw=raw, ext=ext or ".png")
            artwork = load_station_artwork()
            targets = {identity}
            targets.update(request.form.getlist("share_target"))
            artwork.setdefault("stations", {})[station_key] = {
                "name": name,
                "logo": logo_rel,
                "dark_to_white": dark_to_white,
                "optical_scale": optical_scale,
                "edge_cleanup": edge_cleanup,
                "background_cleanup": True,
                "targets": sorted(targets),
                "updated_at": int(time.time()),
            }
            save_station_artwork(artwork)
            # Shared artwork is now authoritative for selected identities.
            entry.pop("logo", None)

        if existing_index is None:
            channels.append(entry)
        else:
            channels[existing_index] = entry
        DB.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")

        message = publish_v2() if publish else "Uložené lokálne; GitHub push nebol spustený."
        shared_count = len(request.form.getlist("share_target"))
        flash(f"{name}: uložené. Zdieľanie loga: {shared_count} ďalších výskytov. {message}")
    except Exception as exc:
        flash(f"Chyba: {exc}")
    return redirect(url_for("index"))


def build_preview_v2():
    try:
        result = legacy.subprocess.run(
            [str(ROOT / ".venv" / "bin" / "python"), str(ROOT / "scripts" / "build_v2.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "Neznáma chyba buildu").strip()
            flash("Lokálny náhľad sa nepodarilo vytvoriť: " + detail[-1200:])
            return redirect(url_for("index"))
        flash("Lokálny SAT + IPTV náhľad bol vytvorený z aktuálnej vetvy. Verejný web sa tým nemení.")
        return redirect("/preview/")
    except Exception as exc:
        flash(f"Chyba lokálneho náhľadu: {exc}")
        return redirect(url_for("index"))


ORIGINAL_PUBLISH = legacy.publish_pending_changes
legacy.publish_pending_changes = publish_v2
legacy.load_admin_channels = load_admin_channels_v2
legacy.load_provider_groups = provider_groups_v2
legacy.app.view_functions["index"] = index_v2
legacy.app.view_functions["build_preview"] = build_preview_v2


def main() -> None:
    legacy.main()


if __name__ == "__main__":
    main()
