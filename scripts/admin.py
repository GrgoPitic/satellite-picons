#!/usr/bin/env python3
from __future__ import annotations

import html
import io
import json
import os
import re
import signal
import atexit
import shutil
import subprocess
import urllib.parse
import webbrowser
from pathlib import Path

from PIL import Image

import requests
import yaml
from bs4 import BeautifulSoup
from flask import Flask, flash, jsonify, redirect, render_template_string, request, send_file, send_from_directory, url_for
from werkzeug.utils import secure_filename

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "channels.yml"
PROVIDER_DATA_DIR = ROOT / "provider-data"
PROVIDERS_CONFIG = ROOT / "providers.yml"
LOGOS = ROOT / "assets" / "logos"
PUBLIC = ROOT / "public"
SUPPORTED = {".png", ".svg", ".jpg", ".jpeg", ".webp"}
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
ORBIT_RE = re.compile(r"(?P<deg>\d+(?:\.\d+)?)\s*°?\s*(?P<dir>[EW])", re.I)
KINGOFSAT_SEARCH = "https://en.kingofsat.net/find.php"
PROVIDER_DEFAULTS = {}

SATELLITE_POSITIONS = [
    ("19.2E", "19.2°E · Astra 1"),
    ("23.5E", "23.5°E · Astra 3B"),
    ("28.2E", "28.2°E · Astra 2"),
    ("1.9E", "1.9°E · BulgariaSat"),
    ("5W", "5.0°W · Eutelsat 5 West"),
    ("9E", "9.0°E · Eutelsat 9"),
    ("13E", "13.0°E · Hot Bird"),
    ("16E", "16.0°E · Eutelsat 16A"),
    ("30W", "30.0°W · Hispasat"),
    ("0.8W", "0.8°W · Thor / Intelsat"),
]

app = Flask(__name__)
app.secret_key = "satellite-picons-local-admin"

PID_FILE = Path("/tmp/satellite-picons-admin.pid")


def write_pid_file() -> None:
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")


def remove_pid_file() -> None:
    try:
        if PID_FILE.exists():
            current = PID_FILE.read_text(encoding="utf-8").strip()
            if current == str(os.getpid()):
                PID_FILE.unlink()
    except Exception:
        pass


def handle_shutdown_signal(signum, frame):
    remove_pid_file()
    raise SystemExit(0)


atexit.register(remove_pid_file)
signal.signal(signal.SIGTERM, handle_shutdown_signal)
signal.signal(signal.SIGINT, handle_shutdown_signal)

def git_branch() -> str:
    try:
        return subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def local_preview_ready() -> bool:
    return (PUBLIC / "index.html").is_file() and (PUBLIC / "providers.json").is_file()


PAGE = r"""
<!doctype html>
<html lang="sk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Satellite Picons Admin</title>
<style>
:root{color-scheme:dark;font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
*{box-sizing:border-box}
body{margin:0;background:#070a0f;color:#f4f7fb;min-height:100vh}
button,input,select{font:inherit}
.app{display:grid;grid-template-columns:260px minmax(0,1fr);min-height:100vh}
.sidebar{position:sticky;top:0;height:100vh;padding:22px 16px;border-right:1px solid #202a36;background:#0a0f16;display:flex;flex-direction:column;gap:18px}
.brand{padding:6px 8px 14px}
.brand strong{display:block;font-size:19px}.brand span{display:block;color:#7f8da0;font-size:12px;margin-top:4px}
.channel-picker{padding:12px;border:1px solid #253242;border-radius:14px;background:#0d131b}
.channel-picker label{margin-top:0}
.nav{display:flex;flex-direction:column;gap:7px}
.nav button,.quick{margin:0;width:100%;text-align:left;padding:11px 12px;border:1px solid transparent;border-radius:10px;background:transparent;color:#aebaca;cursor:pointer;font-weight:650}
.nav button:hover,.nav button.active{background:#162131;color:#fff;border-color:#2c3d51}
.nav small{display:block;color:#6f7d8e;font-size:11px;margin-top:2px;font-weight:500}
.sidebar-foot{margin-top:auto;color:#667486;font-size:11px;padding:0 8px 4px}
.workspace{min-width:0;padding:34px}
.workspace-inner{width:min(1040px,100%);margin:0 auto}
.topbar{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;margin-bottom:24px}
h1{margin:0;font-size:30px;letter-spacing:-.02em}.sub{color:#8e9bad;margin:6px 0 0}
.panel{display:none}.panel.active{display:block}
.card{background:#0d131b;border:1px solid #202a36;border-radius:18px;padding:22px}
.card+.card{margin-top:14px}
.panel-head{margin-bottom:18px}.panel-head h2{margin:0 0 5px;font-size:23px}.panel-head p{margin:0;color:#8b98aa;font-size:14px}
label{display:block;font-size:13px;color:#a9b6c6;margin:16px 0 7px}
input,select{width:100%;padding:12px 13px;border-radius:11px;border:1px solid #2a3543;background:#090e14;color:#fff}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.lookup{display:grid;grid-template-columns:1fr 210px 190px 130px;gap:10px;align-items:end}
.check{display:flex;align-items:center;gap:9px;margin-top:16px}.check input{width:auto}
button.action{margin-top:18px;width:100%;padding:13px;border:0;border-radius:12px;font-weight:750;cursor:pointer}
button.primary{background:#edf3fb;color:#0a1017}
button.secondary{background:#182332;color:#fff;border:1px solid #304052}
button.danger{background:#3a1518;color:#ffd9dc;border:1px solid #6b2b31}
button:disabled{opacity:.45;cursor:not-allowed}
.msg{padding:12px 14px;border:1px solid #35506b;background:#102033;border-radius:10px;margin-bottom:14px}
.status{font-size:13px;color:#93a1b3;margin-top:8px;line-height:1.45}
.note{color:#8290a1;font-size:13px;line-height:1.5}
code{color:#d3deea}
.summary{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.summary div{background:#0a1017;border:1px solid #253242;border-radius:12px;padding:15px}
.summary strong{display:block;font-size:25px}.summary span{font-size:12px;color:#93a1b3}
.quick-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:14px}
.quick-card{padding:16px;border:1px solid #253242;border-radius:14px;background:#0a1017}
.quick-card strong{display:block;margin-bottom:4px}.quick-card p{margin:0 0 12px;color:#8492a4;font-size:13px;line-height:1.4}
.quick-card .quick{background:#162131;color:#fff;border-color:#2c3d51}
.manage-meta{margin-top:12px;padding:12px 14px;border:1px solid #253242;border-radius:10px;background:#081019;display:none}
.manage-meta strong{display:block;margin-bottom:5px}.manage-meta code{font-size:12px;word-break:break-all}
.logo-preview-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:14px 0 6px}
.logo-preview-box{border:1px solid #253242;border-radius:14px;background:#081019;padding:12px}
.logo-preview-box span{display:block;color:#93a1b3;font-size:12px;margin-bottom:8px}
.logo-canvas{height:160px;border-radius:10px;background:#111822;display:flex;align-items:center;justify-content:center;overflow:hidden}
.logo-canvas img{max-width:95%;max-height:135px;object-fit:contain}
.logo-empty{color:#657386;font-size:13px}
.copy-logo{margin-top:16px;padding:14px;border:1px solid #253242;border-radius:14px;background:#0a1017}
.results{margin-top:12px;display:none;border:1px solid #273342;border-radius:12px;overflow:hidden}
.result{padding:12px 14px;border-bottom:1px solid #202a36;cursor:pointer;background:#0a1017}
.result:last-child{border-bottom:0}.result:hover{background:#111b27}
.result strong{display:block}.result small{color:#93a1b3;display:block;margin-top:4px}
.badge{display:inline-block;font-size:11px;padding:3px 7px;border:1px solid #33465c;border-radius:999px;margin-left:6px;color:#b9c8da}
.split-actions{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:18px}
.split-actions .action{margin-top:0}
.hint{padding:12px 14px;border-left:3px solid #354f6c;background:#0a111a;color:#8f9daf;font-size:13px;line-height:1.5;border-radius:0 10px 10px 0}\n.env-card{margin-top:14px;padding:16px;border:1px solid #253242;border-radius:14px;background:#0a1017}.env-row{display:flex;justify-content:space-between;gap:16px;align-items:center}.env-row+.env-row{margin-top:9px;padding-top:9px;border-top:1px solid #1d2835}.env-row span{color:#8d9aac;font-size:13px}.env-row strong{font-size:13px;text-align:right}.ok{color:#9bd6aa}.warn{color:#e6c27a}\n@media(max-width:900px){
  .app{grid-template-columns:1fr}.sidebar{position:relative;height:auto;border-right:0;border-bottom:1px solid #202a36}
  .nav{display:grid;grid-template-columns:repeat(2,1fr)}.sidebar-foot{display:none}.workspace{padding:22px 16px}
  .summary,.quick-grid{grid-template-columns:1fr 1fr}.lookup{grid-template-columns:1fr 1fr}
}
@media(max-width:620px){.grid,.logo-preview-grid,.summary,.quick-grid,.lookup,.split-actions{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="app">
  <aside class="sidebar">
    <div class="brand">
      <strong>Satellite Picons</strong>
      <span>Admin pracovisko</span>
    </div>

    <div class="channel-picker">
      <label>Aktívny kanál</label>
      <select id="manageChannel">
        <option value="">— Vyber kanál —</option>
        {% for ch in channels %}
          <option value="{{ loop.index0 }}">{{ ch.name }} · {{ ch.provider_group or "bez skupiny" }} · {{ "override" if ch._manual_override else "sync" }}</option>
        {% endfor %}
      </select>
      <div class="status">Výber zostáva aktívny pri prepínaní sekcií.</div>
    </div>

    <nav class="nav">
      <button type="button" class="active" data-panel="overview">Prehľad<small>stav databázy a rýchle akcie</small></button>
      <button type="button" data-panel="upload">Nahrať logo<small>nový obrázok alebo kopírovanie</small></button>
      <button type="button" data-panel="edit">Upraviť logo<small>veľkosť, farby a čistenie</small></button>
      <button type="button" data-panel="channel">Kanál a údaje<small>service reference a provider</small></button>
      <button type="button" data-panel="manage">Správa<small>override a odstránenie</small></button>
      <button type="button" data-panel="publish">Publikovanie<small>GitHub commit a push</small></button>
    </nav>

    <div class="sidebar-foot">Lokálne rozhranie · 127.0.0.1:8765</div>
  </aside>

  <main class="workspace">
    <div class="workspace-inner">
      {% with messages = get_flashed_messages() %}
        {% for m in messages %}<div class="msg">{{ m }}</div>{% endfor %}
      {% endwith %}

      <section class="panel active" data-panel-view="overview">
        <div class="topbar">
          <div><h1>Prehľad</h1><p class="sub">Vyber vľavo, čo chceš práve riešiť. Ostatné nástroje sa skryjú.</p></div>
        </div>
        <div class="summary">
          <div><strong>{{ stats.total }}</strong><span>kanálov v admine</span></div>
          <div><strong>{{ stats.generated }}</strong><span>zo synchronizácie</span></div>
          <div><strong>{{ stats.overrides }}</strong><span>ručných override</span></div>
          <div><strong>{{ stats.providers }}</strong><span>providerov</span></div>
        </div>
        <div class="env-card">
          <div class="env-row"><span>Pracovná vetva</span><strong>{{ branch }}</strong></div>
          <div class="env-row"><span>Verejná stránka</span><strong class="warn">stále produkčný main</strong></div>
          <div class="env-row"><span>Lokálny náhľad pripravovanej stránky</span><strong class="{{ 'ok' if preview_ready else 'warn' }}">{{ 'pripravený' if preview_ready else 'treba vytvoriť' }}</strong></div>
        </div>
        <div class="quick-grid">
          <div class="quick-card"><strong>Nahrať logo</strong><p>Vyber súbor alebo prevezmi logo z iného providera.</p><button type="button" class="quick" data-go="upload">Otvoriť nahrávanie</button></div>
          <div class="quick-card"><strong>Upraviť logo</strong><p>Nastav veľkosť, tmavé prvky a čistenie okrajov.</p><button type="button" class="quick" data-go="edit">Otvoriť úpravu</button></div>
          <div class="quick-card"><strong>Kanál a údaje</strong><p>Vyhľadaj kanál a uprav jeho Enigma2 údaje.</p><button type="button" class="quick" data-go="channel">Otvoriť údaje</button></div>
          <div class="quick-card"><strong>Náhľad stránky</strong><p>Zostaví aktuálnu feature verziu webu vrátane tvojich log a providerov.</p><form method="post" action="/preview/build"><button type="submit" class="quick">Vytvoriť a otvoriť náhľad</button></form></div>
        </div>
      </section>

      <form id="channelForm" method="post" enctype="multipart/form-data">
        <section class="panel" data-panel-view="upload">
          <div class="card">
            <div class="panel-head"><h2>Nahrať alebo nahradiť logo</h2><p>Táto sekcia rieši iba zdroj obrázka. Úpravy vzhľadu sú samostatne v „Upraviť logo“.</p></div>
            <div class="logo-preview-grid">
              <div class="logo-preview-box"><span>Aktuálne logo</span><div class="logo-canvas" id="currentLogoPreview"><div class="logo-empty">Vyber kanál vľavo</div></div></div>
              <div class="logo-preview-box"><span>Nové logo</span><div class="logo-canvas" id="newLogoPreview"><div class="logo-empty">Zatiaľ nevybrané</div></div></div>
            </div>

            <label>Nahrať logo zo súboru</label>
            <input id="logoUpload" name="logo" type="file" accept=".png,.svg,.jpg,.jpeg,.webp">
            <div class="status">Vybraný súbor zostane pripravený aj po prepnutí do sekcie „Upraviť logo“.</div>

            <div class="copy-logo">
              <strong>Skopírovať iba logo z iného providera</strong>
              <div class="grid">
                <div><label>Zdrojový provider</label><select id="copyProvider"><option value="">— Vyber provider —</option>{% for key, label in provider_groups %}<option value="{{ key }}">{{ label }}</option>{% endfor %}</select></div>
                <div><label>Zdrojový kanál</label><select id="copyChannel" disabled><option value="">— Najprv vyber provider —</option></select></div>
              </div>
              <div class="logo-preview-box" style="margin-top:12px"><span>Logo, ktoré sa skopíruje</span><div class="logo-canvas" id="copyLogoPreview"><div class="logo-empty">Zatiaľ nevybrané</div></div></div>
              <input type="hidden" id="copyLogoFromRef" name="copy_logo_from_ref" value="">
            </div>
            <div class="split-actions">
              <button type="button" class="action secondary" data-go="edit">Pokračovať na úpravu loga</button>
              <button type="submit" class="action primary">Uložiť bez ďalšej úpravy</button>
            </div>
          </div>
        </section>

        <section class="panel" data-panel-view="edit">
          <div class="card">
            <div class="panel-head"><h2>Upraviť logo</h2><p>Tu riešiš iba výsledný vzhľad piconu. Zdroj loga vyber v sekcii „Nahrať logo“.</p></div>
            <div class="grid">
              <div>
                <label>Čierny/tmavý text → biely</label>
                <select id="darkToWhite" name="dark_to_white">
                  <option value="false" selected>Nie — zachovať originálne farby</option>
                  <option value="true">Áno — tmavé neutrálne časti prefarbiť na bielo</option>
                </select>
              </div>
              <div>
                <label>Veľkosť loga (optical scale)</label>
                <input id="opticalScale" name="optical_scale" type="number" min="0.50" max="1.50" step="0.05" value="1.00">
              </div>
            </div>
            <label class="check"><input id="edgeCleanup" type="checkbox" name="edge_cleanup">Odstrániť biely okraj napojený na hranu</label>

            <div class="logo-preview-box" style="margin-top:18px"><span>Výsledný náhľad</span><div class="logo-canvas" id="processedLogoPreview"><div class="logo-empty">Spusť náhľad úpravy</div></div></div>
            <button type="button" id="previewProcessedBtn" class="action secondary">Náhľad upraveného loga</button>

            <label class="check"><input type="checkbox" name="publish" checked>Po uložení automaticky commitnúť a pushnúť na GitHub</label>
            <button type="submit" class="action primary">Uložiť zmeny a publikovať</button>
          </div>
        </section>

        <section class="panel" data-panel-view="channel">
          <div class="card">
            <div class="panel-head"><h2>Kanál a technické údaje</h2><p>Vyhľadanie, service reference, satelitná pozícia a zaradenie do providera.</p></div>
            <div class="lookup">
              <div><label>Vyhľadať kanál v databáze</label><input id="lookupName" placeholder="napr. JOJ KRIMI"></div>
              <div><label>Satelitná pozícia</label><select id="lookupOrbit" name="satellite_position"><option value="">— Vyber pozíciu —</option>{% for value, label in satellite_positions %}<option value="{{ value }}">{{ label }}</option>{% endfor %}</select></div>
              <div><label>Skupina / balík</label><select id="providerGroup" name="provider_group"><option value="">— Automaticky —</option>{% for key, label in provider_groups %}<option value="{{ key }}">{{ label }}</option>{% endfor %}</select></div>
              <div><button type="button" class="action secondary" id="lookupBtn" style="margin-top:0">Nájsť</button></div>
            </div>
            <div id="lookupStatus" class="status"></div>
            <div id="results" class="results"></div>

            <div class="grid">
              <div><label>ID kanála</label><input id="channelId" name="channel_id" placeholder="joj-krimi" required></div>
              <div><label>Názov kanála</label><input id="channelName" name="name" placeholder="JOJ KRIMI" required></div>
            </div>
            <label>Enigma2 service reference</label>
            <input id="serviceRef" name="service_reference" placeholder="1:0:19:334F:C93:3:EB0000:0:0:0:" required>
            <label>Varianty service type</label>
            <input name="variants" value="1,16,19">
            <button type="submit" class="action primary">Uložiť údaje kanála</button>
          </div>
        </section>

        <section class="panel" data-panel-view="manage">
          <div class="card">
            <div class="panel-head"><h2>Správa kanála</h2><p>Kontrola zdroja, service reference a ručných override.</p></div>
            <div id="manageMeta" class="manage-meta"></div>
            <div class="hint">Synchronizované kanály sa berú z provider-data. Ručný override môžeš odstrániť; sync kanál sa tu zámerne nemaže.</div>
            <button type="button" id="deleteChannelBtn" class="action danger" disabled>Odstrániť override</button>
          </div>
        </section>
      </form>

      <section class="panel" data-panel-view="publish">
        <div class="card">
          <div class="panel-head"><h2>Publikovanie</h2><p>Samostatné miesto pre GitHub commit a push, bez miešania s úpravou loga.</p></div>
          <form id="publishForm" method="post" action="/publish">
            <button id="publishBtn" type="submit" class="action secondary">Publikovať už uložené lokálne zmeny</button>
            <div id="publishStatus" class="status"></div>
          </form>
          <form method="post" action="/preview/build">
            <button type="submit" class="action primary">Vytvoriť lokálny náhľad stránky</button>
          </form>
          {% if preview_ready %}
            <a href="/preview/" target="_blank" style="display:block;margin-top:10px;color:#cfe2ff">Otvoriť posledný lokálny náhľad →</a>
          {% endif %}
          <p class="note">Admin počúva iba na <code>127.0.0.1</code>. Zdroj satelitných údajov: KingOfSat.</p>
        </div>
      </section>
    </div>
  </main>
</div>
<script>

const btn=document.querySelector('#lookupBtn');
const results=document.querySelector('#results');
const status=document.querySelector('#lookupStatus');
const publishForm=document.querySelector('#publishForm');
const publishBtn=document.querySelector('#publishBtn');
const publishStatus=document.querySelector('#publishStatus');
const manageChannel=document.querySelector('#manageChannel');
const manageMeta=document.querySelector('#manageMeta');
const deleteChannelBtn=document.querySelector('#deleteChannelBtn');
const adminChannels={{ channels|tojson }};
const providerDefaults={{ provider_defaults|tojson }};
const providerGroup=document.querySelector('#providerGroup');
const lookupOrbit=document.querySelector('#lookupOrbit');
const currentLogoPreview=document.querySelector('#currentLogoPreview');
const newLogoPreview=document.querySelector('#newLogoPreview');
const logoUpload=document.querySelector('#logoUpload');
const copyProvider=document.querySelector('#copyProvider');
const copyChannel=document.querySelector('#copyChannel');
const copyLogoPreview=document.querySelector('#copyLogoPreview');
const copyLogoFromRef=document.querySelector('#copyLogoFromRef');
const darkToWhite=document.querySelector('#darkToWhite');
const opticalScale=document.querySelector('#opticalScale');
const edgeCleanup=document.querySelector('#edgeCleanup');
const previewProcessedBtn=document.querySelector('#previewProcessedBtn');
if(lookupOrbit && providerGroup){
  lookupOrbit.addEventListener('change',()=>{
    const d=providerDefaults[lookupOrbit.value];
    providerGroup.value=d ? d[0] : '';
  });
}
if(manageChannel){
  manageChannel.addEventListener('change',()=>{
    const idx=manageChannel.value === '' ? -1 : Number(manageChannel.value);
    const ch=idx >= 0 && Number.isInteger(idx) ? adminChannels[idx] : null;
    if(!ch){
      manageMeta.style.display='none';
      deleteChannelBtn.disabled=true;
      return;
    }

    document.querySelector('#channelId').value=ch.id||'';
    document.querySelector('#channelName').value=ch.name||'';
    document.querySelector('#serviceRef').value=ch.service_reference||'';
    document.querySelector('#lookupOrbit').value=ch.satellite_position||'';
    document.querySelector('#providerGroup').value=ch.provider_group||'';
    darkToWhite.value=ch.dark_to_white ? 'true' : 'false';
    opticalScale.value=Number(ch.optical_scale||1).toFixed(2);
    edgeCleanup.checked=Boolean(ch.edge_cleanup);

    const source=ch._manual_override ? 'Ručný override' : 'Automatická synchronizácia';
    const logo=ch.logo || ch.logo_url || 'bez loga';
    const previewUrl=ch.logo ? '/api/logo/'+encodeURIComponent(ch._service_key||'') : (ch.logo_url||'');
    currentLogoPreview.innerHTML=previewUrl
      ? '<img src="'+esc(previewUrl)+'" alt="Aktuálne logo">'
      : '<div class="logo-empty">Logo nie je dostupné</div>';
    newLogoPreview.innerHTML='<div class="logo-empty">Zatiaľ nevybrané</div>';
    if(logoUpload) logoUpload.value='';
    if(copyProvider) copyProvider.value='';
    if(copyChannel){
      copyChannel.innerHTML='<option value="">— Najprv vyber provider —</option>';
      copyChannel.disabled=true;
    }
    if(copyLogoPreview) copyLogoPreview.innerHTML='<div class="logo-empty">Zatiaľ nevybrané</div>';
    if(copyLogoFromRef) copyLogoFromRef.value='';
    manageMeta.innerHTML=
      '<strong>'+esc(ch.name)+' · '+esc(source)+'</strong>'+
      '<div>'+esc(ch.provider_group||'')+' · '+esc(ch.satellite_position||'')+
      (ch.fastscan ? ' · FastScan '+esc(ch.fastscan) : '')+
      (ch.frequency_mhz ? ' · '+esc(ch.frequency_mhz)+' MHz' : '')+'</div>'+
      '<div><code>'+esc(ch.service_reference||'')+'</code></div>'+
      '<div>Logo: '+esc(logo)+'</div>';
    manageMeta.style.display='block';

    deleteChannelBtn.disabled=!ch._manual_override;
    deleteChannelBtn.textContent=ch._manual_override ? 'Odstrániť override' : 'Sync kanál';
  });
}
function effectiveLogoPreviewUrl(ch){
  if(!ch) return '';
  if(ch.logo) return '/api/logo/'+encodeURIComponent(ch._service_key||'');
  return ch.logo_url||'';
}

if(copyProvider && copyChannel){
  copyProvider.addEventListener('change',()=>{
    const provider=copyProvider.value;
    copyChannel.innerHTML='<option value="">— Vyber kanál —</option>';
    copyLogoFromRef.value='';
    copyLogoPreview.innerHTML='<div class="logo-empty">Zatiaľ nevybrané</div>';

    if(!provider){
      copyChannel.disabled=true;
      return;
    }

    adminChannels
      .filter(ch=>String(ch.provider_group||'')===provider)
      .sort((a,b)=>String(a.name||'').localeCompare(String(b.name||''),'sk'))
      .forEach(ch=>{
        const option=document.createElement('option');
        option.value=ch._service_key||'';
        option.textContent=(ch.name||'')+(ch._manual_override?' · moje':' · upstream');
        copyChannel.appendChild(option);
      });

    copyChannel.disabled=false;
  });

  copyChannel.addEventListener('change',()=>{
    const key=copyChannel.value;
    const ch=adminChannels.find(item=>String(item._service_key||'')===key);
    if(!ch){
      copyLogoFromRef.value='';
      copyLogoPreview.innerHTML='<div class="logo-empty">Zatiaľ nevybrané</div>';
      return;
    }

    copyLogoFromRef.value=ch.service_reference||'';
    const url=effectiveLogoPreviewUrl(ch);
    copyLogoPreview.innerHTML=url
      ? '<img src="'+esc(url)+'" alt="Zdrojové logo">'
      : '<div class="logo-empty">Logo nie je dostupné</div>';
  });
}

if(logoUpload){
  logoUpload.addEventListener('change',()=>{
    const file=logoUpload.files && logoUpload.files[0];
    if(file && copyLogoFromRef) copyLogoFromRef.value='';
    if(!file){
      newLogoPreview.innerHTML='<div class="logo-empty">Zatiaľ nevybrané</div>';
      return;
    }
    const url=URL.createObjectURL(file);
    newLogoPreview.innerHTML='<img src="'+url+'" alt="Nové logo">';
  });
}
if(previewProcessedBtn){
  previewProcessedBtn.addEventListener('click', async ()=>{
    const file=logoUpload && logoUpload.files && logoUpload.files[0];
    const sourceRef=copyLogoFromRef ? copyLogoFromRef.value : '';

    if(!file && !sourceRef){
      alert('Najprv nahraj nové logo alebo vyber logo z iného providera.');
      return;
    }

    previewProcessedBtn.disabled=true;
    previewProcessedBtn.textContent='Spracovávam náhľad…';

    try{
      const fd=new FormData();
      if(file) fd.append('logo',file);
      if(sourceRef) fd.append('copy_logo_from_ref',sourceRef);
      fd.append('dark_to_white',darkToWhite.value);
      fd.append('optical_scale',opticalScale.value);
      if(edgeCleanup.checked) fd.append('edge_cleanup','on');

      const r=await fetch('/api/logo-preview',{method:'POST',body:fd});
      if(!r.ok){
        const data=await r.json().catch(()=>({error:'Náhľad zlyhal'}));
        throw new Error(data.error||'Náhľad zlyhal');
      }
      const blob=await r.blob();
      const url=URL.createObjectURL(blob);
      newLogoPreview.innerHTML='<img src="'+url+'" alt="Upravené logo">';
    }catch(e){
      alert('Chyba náhľadu: '+e.message);
    }finally{
      previewProcessedBtn.disabled=false;
      previewProcessedBtn.textContent='Náhľad upraveného loga';
    }
  });
}

if(deleteChannelBtn){
  deleteChannelBtn.disabled=true;
  deleteChannelBtn.addEventListener('click',async()=>{
    const idx=manageChannel.value === '' ? -1 : Number(manageChannel.value);
    const ch=idx >= 0 && Number.isInteger(idx) ? adminChannels[idx] : null;
    if(!ch){alert('Najprv vyber kanál.');return;}
    if(!ch._manual_override){alert('Synchronizovaný kanál sa nemaže priamo. Najprv sa spravuje cez override.');return;}
    const channelId=ch.id;
    const name=ch.name;
    if(!confirm('Naozaj odstrániť ručný override pre '+name+'? Synchronizovaný kanál zostane zachovaný.'))return;
    deleteChannelBtn.disabled=true;
    deleteChannelBtn.textContent='Mažem…';
    try{
      const r=await fetch('/api/channel/'+encodeURIComponent(channelId),{method:'DELETE'});
      const data=await r.json();
      if(!r.ok)throw new Error(data.error||'Mazanie zlyhalo');
      window.location.reload();
    }catch(e){
      alert('Chyba: '+e.message);
      deleteChannelBtn.disabled=false;
      deleteChannelBtn.textContent='Vymazať kanál';
    }
  });
}
if(publishForm){
  publishForm.addEventListener('submit',()=>{
    publishBtn.disabled=true;
    publishBtn.textContent='Publikujem…';
    publishStatus.textContent='Synchronizujem lokálny repozitár a odosielam zmeny na GitHub. Maximálne približne 30 sekúnd.';
  });
}

function slugify(v){
  return v.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'')
    .replace(/[^a-z0-9]+/g,'-').replace(/^-+|-+$/g,'').slice(0,64);
}
function esc(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));}

btn.addEventListener('click', async ()=>{
  const q=document.querySelector('#lookupName').value.trim();
  const orbit=document.querySelector('#lookupOrbit').value.trim();
  if(!q){status.textContent='Zadaj názov kanála.';return;}
  status.textContent='Hľadám v KingOfSat…'; results.style.display='none'; results.innerHTML='';
  try{
    const r=await fetch('/api/lookup?'+new URLSearchParams({q,orbit}));
    const data=await r.json();
    if(!r.ok) throw new Error(data.error||'Vyhľadávanie zlyhalo');
    status.textContent=data.results.length ? 'Klikni na správny výsledok.' : 'Nič sa nenašlo.';
    if(!data.results.length)return;
    results.innerHTML=data.results.map((x,i)=>`
      <div class="result" data-i="${i}">
        <strong>${esc(x.name)} <span class="badge">${esc(x.orbit)}</span></strong>
        <small>${esc(x.satellite)} • ${esc(x.frequency)} ${esc(x.polarization)} • SID ${x.sid} • TID ${x.tid} • NID ${x.nid}</small>
        <small><code>${esc(x.service_reference)}</code></small>
      </div>`).join('');
    results.style.display='block';
    [...results.querySelectorAll('.result')].forEach(el=>el.addEventListener('click',()=>{
      const x=data.results[Number(el.dataset.i)];
      document.querySelector('#channelName').value=x.name.replace(/\s+HD$/i,'');
      document.querySelector('#channelId').value=slugify(document.querySelector('#channelName').value);
      document.querySelector('#serviceRef').value=x.service_reference;
      document.querySelector('#lookupOrbit').value=x.orbit;
      status.textContent='Vybrané: '+x.name+' ('+x.orbit+')';
    }));
  }catch(e){status.textContent='Chyba: '+e.message;}
});

</script>
<script>
(function(){
  const navButtons=[...document.querySelectorAll('[data-panel]')];
  const panels=[...document.querySelectorAll('[data-panel-view]')];

  function showPanel(name){
    panels.forEach(p=>p.classList.toggle('active',p.dataset.panelView===name));
    navButtons.forEach(b=>b.classList.toggle('active',b.dataset.panel===name));
    try{localStorage.setItem('satellite-picons-admin-panel',name);}catch(e){}
    window.scrollTo({top:0,behavior:'instant'});
  }

  navButtons.forEach(button=>button.addEventListener('click',()=>showPanel(button.dataset.panel)));
  document.querySelectorAll('[data-go]').forEach(button=>button.addEventListener('click',()=>showPanel(button.dataset.go)));

  let saved='overview';
  try{saved=localStorage.getItem('satellite-picons-admin-panel')||'overview';}catch(e){}
  if(panels.some(p=>p.dataset.panelView===saved)) showPanel(saved);

  const originalPreview=document.querySelector('#newLogoPreview');
  const processed=document.querySelector('#processedLogoPreview');
  const observer=new MutationObserver(()=>{
    if(processed && originalPreview && originalPreview.innerHTML){
      processed.innerHTML=originalPreview.innerHTML;
    }
  });
  if(originalPreview) observer.observe(originalPreview,{childList:true,subtree:true});

  const selector=document.querySelector('#manageChannel');
  if(selector){
    selector.addEventListener('change',()=>{
      if(selector.value!=='' && document.querySelector('[data-panel-view="overview"].active')){
        showPanel('upload');
      }
    });
  }
})();
</script>
</body>
</html>
"""

def load_provider_groups() -> list[tuple[str, str]]:
    """Return provider choices that actually have usable local data.

    During catalogue migrations provider-data can temporarily contain legacy
    IDs (for example "skylink" / "antik") while providers.yml already contains
    the new IDs. The admin must still show the channels that really exist
    locally instead of presenting an empty provider choice.
    """
    configured = {}
    if PROVIDERS_CONFIG.exists():
        cfg = yaml.safe_load(PROVIDERS_CONFIG.read_text(encoding="utf-8")) or {}
        for provider in cfg.get("providers", []):
            provider_id = str(provider.get("id") or "").strip().lower()
            name = str(provider.get("name") or provider_id).strip()
            if provider_id:
                configured[provider_id] = name

    actual_ids = set()
    if PROVIDER_DATA_DIR.exists():
        for path in sorted(PROVIDER_DATA_DIR.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            provider_id = str(payload.get("provider") or path.stem).strip().lower()
            if provider_id:
                actual_ids.add(provider_id)

    # Manual overrides can also refer to a provider before/without generated data.
    if DB.exists():
        try:
            manual_cfg = yaml.safe_load(DB.read_text(encoding="utf-8")) or {}
            for channel in manual_cfg.get("channels", []) or []:
                provider_id = str(channel.get("provider_group") or "").strip().lower()
                if provider_id:
                    actual_ids.add(provider_id)
        except Exception:
            pass

    legacy_names = {
        "skylink": "Skylink",
        "antik": "ANTIK Sat",
    }

    # Prefer providers that have data locally. If the new full sync already
    # exists, all new configured IDs appear automatically.
    provider_ids = actual_ids or set(configured)
    providers = []
    for provider_id in provider_ids:
        name = configured.get(provider_id) or legacy_names.get(provider_id) or provider_id
        providers.append((provider_id, name))

    return sorted(providers, key=lambda item: item[1].lower())


def service_identity(ref: str) -> str:
    parts = ref.strip().strip(":").split(":")
    if len(parts) < 7:
        return ref.strip().upper()
    return "_".join(parts[i].upper() for i in (3, 4, 5, 6))


def load_admin_channels() -> tuple[list[dict], dict]:
    cfg = yaml.safe_load(DB.read_text(encoding="utf-8")) or {"channels": []}
    manual = cfg.get("channels", []) or []
    manual_by_service = {
        service_identity(ch.get("service_reference", "")): dict(ch)
        for ch in manual
        if ch.get("service_reference")
    }

    merged = {}
    generated_count = 0
    providers = set()

    if PROVIDER_DATA_DIR.exists():
        for path in sorted(PROVIDER_DATA_DIR.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            provider_id = str(payload.get("provider") or path.stem).strip().lower()
            providers.add(provider_id)
            for channel in payload.get("channels", []) or []:
                if not channel.get("service_reference"):
                    continue
                generated_count += 1
                item = dict(channel)
                item["provider_group"] = str(item.get("provider_group") or provider_id).strip().lower()
                item["_generated"] = True
                item["_manual_override"] = False
                merged[service_identity(item["service_reference"])] = item

    for channel in manual:
        if not channel.get("service_reference"):
            continue
        key = service_identity(channel["service_reference"])
        base = dict(merged.get(key, {}))
        base.update(channel)
        base["_generated"] = bool(merged.get(key))
        base["_manual_override"] = True
        merged[key] = base
        if base.get("provider_group"):
            providers.add(str(base["provider_group"]).strip().lower())

    rows = []
    for key, item in merged.items():
        row = dict(item)
        row["_service_key"] = key
        rows.append(row)

    rows.sort(
        key=lambda ch: (
            str(ch.get("provider_group") or ""),
            int(ch.get("fastscan") or 99999),
            str(ch.get("name") or "").lower(),
        )
    )
    stats = {
        "total": len(rows),
        "generated": generated_count,
        "overrides": sum(1 for ch in rows if ch.get("_manual_override")),
        "providers": len(providers),
    }
    return rows, stats


def validate_ref(ref: str) -> None:
    parts = [p for p in ref.strip().strip(":").split(":")]
    if len(parts) != 10:
        raise ValueError("Service reference musí mať presne 10 polí oddelených dvojbodkou.")

def normalize_orbit(value: str) -> str:
    value = value.strip().upper().replace("°", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*([EW])", value)
    if not m:
        return ""
    return f"{float(m.group(1)):g}{m.group(2)}"

def orbit_to_namespace(orbit: str) -> str:
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([EW])", normalize_orbit(orbit))
    if not m:
        raise ValueError(f"Neplatná orbita: {orbit}")
    tenths = int(round(float(m.group(1)) * 10))
    pos = tenths if m.group(2) == "E" else (3600 - tenths) % 3600
    return f"{pos << 16:X}"

def compose_service_reference(*, sid: int, tid: int, nid: int, orbit: str, name: str) -> str:
    service_type = 0x19 if re.search(r"\bHD\b", name, re.I) else 0x1
    namespace = orbit_to_namespace(orbit)
    return f"1:0:{service_type:X}:{sid:X}:{tid:X}:{nid:X}:{namespace}:0:0:0:"

def row_texts(tr):
    return [" ".join(td.stripped_strings) for td in tr.find_all(["td", "th"])]

def search_kingofsat(query: str, orbit_filter: str = "") -> list[dict]:
    params = {
        "aff": "list",
        "filtre": "no",
        "lim": "0",
        "ordre": "nom_ch",
        "question": query,
        "standard": "All",
    }
    headers = {"User-Agent": "Satellite-Picons-Admin/1.0 (+https://github.com/GrgoPitic/satellite-picons)"}
    r = requests.get(KINGOFSAT_SEARCH, params=params, headers=headers, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    wanted = normalize_orbit(orbit_filter)
    current = None
    results = []

    for tr in soup.find_all("tr"):
        cells = row_texts(tr)
        if not cells:
            continue
        joined = " | ".join(cells)

        orbit_match = ORBIT_RE.search(joined)
        # Transponder rows contain orbital position + frequency and end in NID/TID.
        if orbit_match and re.search(r"\b\d{4,5}(?:\.\d+)?\b", joined):
            orbit = normalize_orbit(orbit_match.group(0))
            nums = []
            for c in cells[-4:]:
                if re.fullmatch(r"\d+", c):
                    nums.append(int(c))
            # KingOfSat list rows end with NID, TID. Keep only if present.
            nid = tid = None
            if len(nums) >= 2:
                nid, tid = nums[-2], nums[-1]
            freq = next((c for c in cells if re.fullmatch(r"\d{4,5}(?:\.\d+)?", c)), "")
            pol = next((c for c in cells if c in {"H", "V", "L", "R"}), "")
            sat = ""
            for c in cells:
                if orbit_match.group(0) in c:
                    continue
                if any(k in c.lower() for k in ("astra", "thor", "eutelsat", "hot bird", "hispa", "turksat", "amos", "intelsat")):
                    sat = c
                    break
            current = {"orbit": orbit, "frequency": freq, "polarization": pol, "satellite": sat, "nid": nid, "tid": tid}
            continue

        if not current or current["nid"] is None or current["tid"] is None:
            continue
        if wanted and current["orbit"] != wanted:
            continue

        # Channel rows: find the searched name and SID. KingOfSat list column order:
        # Name, Country, Category, Packages, Encryption, SID, ...
        low = joined.lower()
        if query.lower() not in low:
            continue

        # Ignore header rows.
        if any(c.strip().upper() == "SID" for c in cells):
            continue

        # Locate a plausible channel name cell containing query.
        name = next((c for c in cells if query.lower() in c.lower() and len(c) < 120), "")
        if not name:
            continue

        # SID is the first plain integer after the matching name area, but skip years/dates.
        name_idx = cells.index(name)
        sid = None
        for c in cells[name_idx + 1:]:
            if re.fullmatch(r"\d{1,5}", c):
                v = int(c)
                if 0 < v <= 65535:
                    sid = v
                    break
        if sid is None:
            continue

        try:
            service_ref = compose_service_reference(
                sid=sid, tid=current["tid"], nid=current["nid"], orbit=current["orbit"], name=name
            )
        except ValueError:
            continue

        item = {
            "name": html.unescape(name),
            "orbit": current["orbit"],
            "satellite": current["satellite"] or "Satellite",
            "frequency": current["frequency"],
            "polarization": current["polarization"],
            "sid": sid,
            "tid": current["tid"],
            "nid": current["nid"],
            "namespace": orbit_to_namespace(current["orbit"]),
            "service_reference": service_ref,
            "source": "KingOfSat",
        }
        if not any(x["service_reference"] == item["service_reference"] for x in results):
            results.append(item)

    return results[:30]

def load_uploaded_logo(data: bytes, ext: str) -> Image.Image:
    if ext == ".svg":
        try:
            import cairosvg
            data = cairosvg.svg2png(bytestring=data)
        except Exception as exc:
            raise RuntimeError("SVG_LOCAL_DEFER") from exc
    return Image.open(io.BytesIO(data)).convert("RGBA")

def has_real_transparency(im: Image.Image) -> bool:
    lo, _ = im.getchannel("A").getextrema()
    return lo < 250

def remove_corner_connected_background(im: Image.Image, tolerance: int = 28) -> Image.Image:
    """Remove smooth/solid backgrounds connected to image corners.

    This preserves the artwork itself and only turns the surrounding background
    transparent. It also handles many gradient backgrounds because the flood
    fill follows small local colour changes.
    """
    im = im.convert("RGBA")
    if has_real_transparency(im):
        return im

    px = im.load()
    w, h = im.size
    if w < 2 or h < 2:
        return im

    seeds = {(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)}
    seen = set()
    stack = list(seeds)

    def close(a, b):
        return max(abs(a[i] - b[i]) for i in range(3)) <= tolerance

    while stack:
        x, y = stack.pop()
        if (x, y) in seen or not (0 <= x < w and 0 <= y < h):
            continue
        seen.add((x, y))
        current = px[x, y]
        if current[3] == 0:
            continue

        for nx, ny in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
            if not (0 <= nx < w and 0 <= ny < h) or (nx, ny) in seen:
                continue
            neighbour = px[nx, ny]
            if neighbour[3] > 0 and close(current, neighbour):
                stack.append((nx, ny))

    # Do not apply suspicious cleanup if it would remove almost nothing.
    if len(seen) < max(12, int(w * h * 0.015)):
        return im

    for x, y in seen:
        r, g, b, _ = px[x, y]
        px[x, y] = (r, g, b, 0)
    return im

def trim_transparent(im: Image.Image) -> Image.Image:
    bbox = im.getchannel("A").getbbox()
    if not bbox:
        raise ValueError("Po odstránení pozadia nezostal žiadny obsah loga.")
    return im.crop(bbox)

def prepare_logo(data: bytes, ext: str) -> Image.Image:
    im = load_uploaded_logo(data, ext)
    im = remove_corner_connected_background(im)
    return trim_transparent(im)

def local_logo_destination(channel_id: str, ref: str, ext: str) -> Path:
    import hashlib

    suffix = hashlib.sha1(service_identity(ref).encode("utf-8")).hexdigest()[:10]
    return LOGOS / f"{channel_id}-{suffix}{ext}"


def remove_local_logo_if_unused(path_value: str | None, except_ref: str = "") -> None:
    if not path_value:
        return

    candidate = (ROOT / str(path_value)).resolve()
    try:
        candidate.relative_to(LOGOS.resolve())
    except ValueError:
        return

    cfg = yaml.safe_load(DB.read_text(encoding="utf-8")) or {"channels": []}
    wanted_key = service_identity(except_ref) if except_ref else ""

    for channel in cfg.get("channels", []):
        ref = channel.get("service_reference")
        if not ref:
            continue
        if wanted_key and service_identity(ref) == wanted_key:
            continue
        other = channel.get("logo")
        if other and (ROOT / str(other)).resolve() == candidate:
            return

    if candidate.exists() and candidate.is_file():
        candidate.unlink()


def effective_channel_by_ref(ref: str) -> dict | None:
    wanted = service_identity(ref)
    channels, _ = load_admin_channels()
    return next(
        (channel for channel in channels if channel.get("_service_key") == wanted),
        None,
    )


def read_effective_logo(channel: dict) -> tuple[bytes, str]:
    local_logo = channel.get("logo")
    if local_logo:
        path = (ROOT / str(local_logo)).resolve()
        if path.exists() and path.is_file():
            return path.read_bytes(), path.suffix.lower()

    logo_url = channel.get("logo_url")
    if logo_url:
        response = requests.get(
            str(logo_url),
            timeout=(10, 25),
            headers={"User-Agent": "Satellite-Picons-Admin/1.0"},
        )
        response.raise_for_status()
        ext = Path(urllib.parse.urlparse(str(logo_url)).path).suffix.lower()
        if ext not in SUPPORTED:
            ext = ".png"
        return response.content, ext

    raise ValueError("Zdrojový kanál nemá dostupné logo.")


def render_preview_png(
    *,
    raw: bytes,
    ext: str,
    dark_to_white: bool = False,
    optical_scale: float = 1.0,
    edge_cleanup: bool = False,
) -> bytes:
    if ext not in SUPPORTED:
        raise ValueError("Nepodporovaný formát loga.")

    im = load_uploaded_logo(raw, ext)
    if edge_cleanup:
        # Same edge cleanup principle as the build: remove near-white pixels
        # connected to the outer edge.
        px = im.load()
        w, h = im.size
        seen = set()
        stack = []
        for x in range(w):
            stack.extend([(x, 0), (x, h - 1)])
        for y in range(h):
            stack.extend([(0, y), (w - 1, y)])
        while stack:
            x, y = stack.pop()
            if (x, y) in seen or not (0 <= x < w and 0 <= y < h):
                continue
            seen.add((x, y))
            r, g, b, a = px[x, y]
            if not (a > 0 and r >= 245 and g >= 245 and b >= 245):
                continue
            px[x, y] = (r, g, b, 0)
            stack.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))

    im = remove_corner_connected_background(im)
    im = trim_transparent(im)

    if dark_to_white:
        data = list(im.getdata())
        out = []
        for r, g, b, a in data:
            if a == 0:
                out.append((r, g, b, a))
                continue
            mx, mn = max(r, g, b), min(r, g, b)
            if mx <= 105 and (mx - mn) <= 28:
                lum = (r + g + b) / 3
                v = int(230 + (105 - lum) / 105 * 25)
                v = max(230, min(255, v))
                out.append((v, v, v, a))
            else:
                out.append((r, g, b, a))
        im.putdata(out)

    optical_scale = max(0.50, min(1.50, float(optical_scale)))
    max_w, max_h = 148, 86
    w, h = im.size
    scale = min(max_w / w, max_h / h) * optical_scale
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    if new_w > max_w or new_h > max_h:
        cap = min(max_w / new_w, max_h / new_h)
        new_w = max(1, int(round(new_w * cap)))
        new_h = max(1, int(round(new_h * cap)))
    im = im.resize((new_w, new_h), Image.Resampling.LANCZOS)

    canvas = Image.new("RGBA", (150, 90), (0, 0, 0, 0))
    canvas.alpha_composite(im, ((150 - new_w) // 2, (90 - new_h) // 2))
    out = io.BytesIO()
    canvas.save(out, format="PNG", optimize=True)
    return out.getvalue()


def save_manual_logo(
    *,
    channel_id: str,
    ref: str,
    raw: bytes,
    ext: str,
    old_logo: str | None,
) -> str:
    if ext not in SUPPORTED:
        raise ValueError("Nepodporovaný formát loga.")

    LOGOS.mkdir(parents=True, exist_ok=True)

    try:
        processed = prepare_logo(raw, ext)
        dest = local_logo_destination(channel_id, ref, ".png")
        processed.save(dest, format="PNG", optimize=True)
    except RuntimeError as exc:
        if str(exc) != "SVG_LOCAL_DEFER" or ext != ".svg":
            raise
        dest = local_logo_destination(channel_id, ref, ".svg")
        dest.write_bytes(raw)

    new_rel = str(dest.relative_to(ROOT))
    if old_logo and old_logo != new_rel:
        remove_local_logo_if_unused(old_logo, except_ref=ref)

    return new_rel


def run_git(*args: str, timeout: int = 25) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes -o ConnectTimeout=10"
    try:
        return subprocess.run(
            ["git", *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Git operácia prekročila časový limit.") from exc

def publish_pending_changes() -> str:
    add_paths = ["channels.yml", "assets/logos"]
    if (ROOT / "assets" / "source-logos").exists():
        add_paths.append("assets/source-logos")

    branch_result = run_git("rev-parse", "--abbrev-ref", "HEAD")
    if branch_result.returncode != 0:
        raise RuntimeError("Nepodarilo sa zistiť aktuálnu Git vetvu.")
    branch = branch_result.stdout.strip()
    if not branch or branch == "HEAD":
        raise RuntimeError("Repozitár je v detached HEAD stave. Publikovanie bolo zastavené.")

    add = run_git("add", "-A", *add_paths)
    if add.returncode != 0:
        raise RuntimeError(add.stderr.strip() or "git add zlyhal")

    diff = run_git("diff", "--cached", "--quiet")
    if diff.returncode not in (0, 1):
        raise RuntimeError(diff.stderr.strip() or "Kontrola zmien zlyhala.")

    if diff.returncode == 1:
        commit = run_git("commit", "-m", "Update satellite picons")
        if commit.returncode != 0:
            raise RuntimeError(commit.stderr.strip() or commit.stdout.strip() or "git commit zlyhal")

    fetch = run_git("fetch", "origin", branch)
    if fetch.returncode != 0:
        raise RuntimeError(fetch.stderr.strip() or fetch.stdout.strip() or f"Načítanie origin/{branch} zlyhalo.")

    ahead = run_git("rev-list", "--count", "FETCH_HEAD..HEAD")
    behind = run_git("rev-list", "--count", "HEAD..FETCH_HEAD")
    if ahead.returncode != 0 or behind.returncode != 0:
        raise RuntimeError("Kontrola stavu lokálnej vetvy zlyhala.")

    ahead_count = int(ahead.stdout.strip() or "0")
    behind_count = int(behind.stdout.strip() or "0")

    if behind_count:
        rebase = run_git("rebase", "FETCH_HEAD", timeout=45)
        if rebase.returncode != 0:
            run_git("rebase", "--abort")
            raise RuntimeError(
                f"GitHub vetva {branch} obsahuje novšie zmeny a automatické zlúčenie nebolo bezpečné. "
                "Lokálne zmeny zostali zachované; publikovanie bolo zastavené."
            )

        ahead = run_git("rev-list", "--count", "FETCH_HEAD..HEAD")
        if ahead.returncode != 0:
            raise RuntimeError("Kontrola lokálnych commitov po synchronizácii zlyhala.")
        ahead_count = int(ahead.stdout.strip() or "0")

    if ahead_count == 0:
        return f"Nie sú žiadne lokálne zmeny pre vetvu {branch}."

    push = run_git("push", "origin", f"HEAD:{branch}", timeout=30)
    if push.returncode != 0:
        raise RuntimeError(push.stderr.strip() or push.stdout.strip() or "git push zlyhal")

    return f"Publikované do vetvy {branch}: {ahead_count} lokálny commit."

@app.get("/health")
def health():
    return jsonify(ok=True, pid=os.getpid())


@app.get("/api/logo/<service_key>")
def api_logo(service_key: str):
    cfg = yaml.safe_load(DB.read_text(encoding="utf-8")) or {"channels": []}
    existing = next(
        (
            ch for ch in cfg.get("channels", [])
            if ch.get("service_reference")
            and service_identity(ch["service_reference"]) == service_key.upper()
        ),
        None,
    )
    if not existing or not existing.get("logo"):
        return jsonify(error="Lokálne logo sa nenašlo."), 404

    path = (ROOT / str(existing["logo"])).resolve()
    try:
        path.relative_to(ROOT.resolve())
    except ValueError:
        return jsonify(error="Neplatná cesta loga."), 400

    if not path.exists() or not path.is_file():
        return jsonify(error="Lokálne logo sa nenašlo."), 404

    return send_file(path)


@app.post("/api/logo-preview")
def api_logo_preview():
    try:
        upload = request.files.get("logo")
        copy_logo_from_ref = request.form.get("copy_logo_from_ref", "").strip()
        dark_to_white = request.form.get("dark_to_white", "false") == "true"
        edge_cleanup = request.form.get("edge_cleanup") == "on"

        try:
            optical_scale = float(request.form.get("optical_scale", "1.0"))
        except ValueError:
            raise ValueError("Veľkosť loga musí byť číslo.")

        if upload and upload.filename:
            original_name = secure_filename(upload.filename or "")
            ext = Path(original_name).suffix.lower()
            raw = upload.read()
        elif copy_logo_from_ref:
            source_channel = effective_channel_by_ref(copy_logo_from_ref)
            if not source_channel:
                raise ValueError("Zdrojový kanál sa nenašiel.")
            raw, ext = read_effective_logo(source_channel)
        else:
            raise ValueError("Nie je vybrané žiadne logo.")

        if not raw:
            raise ValueError("Logo je prázdne.")

        png = render_preview_png(
            raw=raw,
            ext=ext,
            dark_to_white=dark_to_white,
            optical_scale=optical_scale,
            edge_cleanup=edge_cleanup,
        )
        return send_file(
            io.BytesIO(png),
            mimetype="image/png",
            download_name="preview.png",
        )
    except Exception as exc:
        return jsonify(error=str(exc)), 400


@app.get("/api/lookup")
def api_lookup():
    q = request.args.get("q", "").strip()
    orbit = request.args.get("orbit", "").strip()
    if len(q) < 2:
        return jsonify(error="Zadaj aspoň 2 znaky názvu kanála."), 400
    try:
        return jsonify(results=search_kingofsat(q, orbit))
    except requests.RequestException as exc:
        return jsonify(error=f"KingOfSat nie je dostupný: {exc}"), 502
    except Exception as exc:
        return jsonify(error=str(exc)), 500

@app.delete("/api/channel/<channel_id>")
def delete_channel(channel_id: str):
    try:
        cfg = yaml.safe_load(DB.read_text(encoding="utf-8")) or {"channels": []}
        channels = cfg.setdefault("channels", [])
        existing = next((ch for ch in channels if ch.get("id") == channel_id), None)
        if not existing:
            return jsonify(error="Kanál sa v databáze nenašiel."), 404

        channels.remove(existing)

        logo_rel = existing.get("logo")
        if logo_rel:
            remove_local_logo_if_unused(
                logo_rel,
                except_ref=existing.get("service_reference", ""),
            )

        source_logo_rel = existing.get("source_logo")
        if source_logo_rel:
            source_logo_path = ROOT / source_logo_rel
            if source_logo_path.exists() and source_logo_path.is_file():
                source_logo_path.unlink()

        DB.write_text(
            yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

        message = publish_pending_changes()
        return jsonify(ok=True, message=message)
    except Exception as exc:
        return jsonify(error=str(exc)), 500

@app.post("/preview/build")
def build_preview():
    try:
        result = subprocess.run(
            [str(ROOT / ".venv" / "bin" / "python"), str(ROOT / "scripts" / "build.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "Neznáma chyba buildu").strip()
            flash("Lokálny náhľad sa nepodarilo vytvoriť: " + detail[-1200:])
            return redirect(url_for("index"))

        flash(
            "Lokálny náhľad bol vytvorený z aktuálnej vetvy "
            + git_branch()
            + ". Verejný web na GitHub Pages sa tým nemení."
        )
        return redirect("/preview/")
    except subprocess.TimeoutExpired:
        flash("Build lokálneho náhľadu prekročil časový limit 5 minút.")
    except Exception as exc:
        flash(f"Chyba lokálneho náhľadu: {exc}")
    return redirect(url_for("index"))


@app.get("/preview/")
def preview_index():
    if not (PUBLIC / "index.html").is_file():
        flash("Lokálny náhľad ešte neexistuje. Najprv ho vytvor v Prehľade alebo Publikovaní.")
        return redirect(url_for("index"))
    return send_from_directory(PUBLIC, "index.html")


@app.get("/preview/<path:filename>")
def preview_file(filename: str):
    return send_from_directory(PUBLIC, filename)


@app.post("/publish")
def publish():
    try:
        flash(publish_pending_changes())
    except Exception as exc:
        flash(f"Chyba publikovania: {exc}")
    return redirect(url_for("index"))

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        channels, stats = load_admin_channels()
        return render_template_string(
            PAGE,
            channels=channels,
            stats=stats,
            satellite_positions=SATELLITE_POSITIONS,
            provider_groups=load_provider_groups(),
            provider_defaults=PROVIDER_DEFAULTS,
            branch=git_branch(),
            preview_ready=local_preview_ready(),
        )

    try:
        channel_id = request.form["channel_id"].strip().lower()
        name = request.form["name"].strip()
        ref = request.form["service_reference"].strip()
        satellite_position = normalize_orbit(request.form.get("satellite_position", "").strip())
        provider_group = request.form.get("provider_group", "").strip()
        variants = [x.strip().upper() for x in request.form.get("variants", "1,16,19").split(",") if x.strip()]
        dark_to_white = request.form.get("dark_to_white", "false") == "true"
        edge_cleanup = request.form.get("edge_cleanup") == "on"
        try:
            optical_scale = float(request.form.get("optical_scale", "1.0"))
        except ValueError:
            raise ValueError("Veľkosť loga musí byť číslo.")
        if not 0.50 <= optical_scale <= 1.50:
            raise ValueError("Veľkosť loga musí byť medzi 0.50 a 1.50.")
        publish = request.form.get("publish") == "on"
        upload = request.files.get("logo")
        copy_logo_from_ref = request.form.get("copy_logo_from_ref", "").strip()

        if not ID_RE.match(channel_id):
            raise ValueError("ID môže obsahovať iba malé písmená, čísla a pomlčky.")
        if not name:
            raise ValueError("Názov kanála je povinný.")
        validate_ref(ref)
        if not variants:
            raise ValueError("Musí byť zadaný aspoň jeden service type variant.")

        cfg = yaml.safe_load(DB.read_text(encoding="utf-8")) or {"channels": []}
        channels = cfg.setdefault("channels", [])
        ref_key = service_identity(ref)
        existing_index = next(
            (
                i for i, ch in enumerate(channels)
                if ch.get("service_reference") and service_identity(ch["service_reference"]) == ref_key
            ),
            None,
        )
        existing = channels[existing_index] if existing_index is not None else {}

        entry = dict(existing)
        entry.update({
            "id": channel_id,
            "name": name,
            "service_reference": ref,
            "variant_types": variants,
            "dark_to_white": dark_to_white,
            "optical_scale": optical_scale,
            "edge_cleanup": edge_cleanup,
            "background_cleanup": True,
            "satellite_position": satellite_position or None,
            "provider_group": provider_group or None,
        })

        if upload and upload.filename:
            original_name = secure_filename(upload.filename or "")
            ext = Path(original_name).suffix.lower()
            raw = upload.read()
            if not raw:
                raise ValueError("Logo je prázdne.")

            entry["logo"] = save_manual_logo(
                channel_id=channel_id,
                ref=ref,
                raw=raw,
                ext=ext,
                old_logo=existing.get("logo"),
            )

        elif copy_logo_from_ref:
            if service_identity(copy_logo_from_ref) == ref_key:
                raise ValueError("Zdrojové a cieľové logo sú rovnaký kanál.")

            source_channel = effective_channel_by_ref(copy_logo_from_ref)
            if not source_channel:
                raise ValueError("Zdrojový kanál sa nenašiel.")

            raw, ext = read_effective_logo(source_channel)
            entry["logo"] = save_manual_logo(
                channel_id=channel_id,
                ref=ref,
                raw=raw,
                ext=ext,
                old_logo=existing.get("logo"),
            )

        if existing_index is not None:
            channels[existing_index] = entry
        else:
            channels.append(entry)

        DB.write_text(
            yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

        if publish:
            message = publish_pending_changes()
            flash(f"{name}: uložené. {message}")
        else:
            flash(f"{name}: uložené lokálne. GitHub push nebol spustený.")

    except Exception as exc:
        flash(f"Chyba: {exc}")

    return redirect(url_for("index"))

def main():
    url = "http://127.0.0.1:8765"
    write_pid_file()
    print(f"Satellite Picons Admin: {url}")
    app.run(
        host="127.0.0.1",
        port=8765,
        debug=False,
        use_reloader=False,
        threaded=True,
    )

if __name__ == "__main__":
    main()
