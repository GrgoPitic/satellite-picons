#!/usr/bin/env python3
from __future__ import annotations

import html
import io
import re
import subprocess
import webbrowser
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import cairosvg
import requests
import yaml
from bs4 import BeautifulSoup
from flask import Flask, flash, jsonify, redirect, render_template_string, request, send_file, url_for
from PIL import Image
from werkzeug.utils import secure_filename

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "channels.yml"
LOGOS = ROOT / "assets" / "logos"
SOURCE_LOGOS = ROOT / "assets" / "source-logos"
TEMPLATE = ROOT / "assets" / "templates" / "piconblack-150x90.png"
SUPPORTED = {".png", ".svg", ".jpg", ".jpeg", ".webp"}
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
ORBIT_RE = re.compile(r"(?P<deg>\d+(?:\.\d+)?)\s*°?\s*(?P<dir>[EW])", re.I)
KINGOFSAT_SEARCH = "https://en.kingofsat.net/find.php"
CANVAS = (150, 90)
MAX_LOGO = (140, 80)

app = Flask(__name__)
app.secret_key = "satellite-picons-local-admin"
_REMBG_SESSION = None

PAGE = r"""
<!doctype html>
<html lang="sk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Satellite Picons Admin</title>
<style>
:root{color-scheme:dark;font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
*{box-sizing:border-box}body{margin:0;background:#070a0f;color:#f4f7fb}
main{width:min(980px,calc(100% - 32px));margin:40px auto 80px}
.card{background:#0d131b;border:1px solid #202a36;border-radius:18px;padding:22px}
h1{margin:0 0 8px;font-size:34px}.sub{color:#93a1b3;margin:0 0 24px}
label{display:block;font-size:13px;color:#a9b6c6;margin:16px 0 7px}
input,select{width:100%;padding:13px 14px;border-radius:11px;border:1px solid #2a3543;background:#090e14;color:#fff;font-size:15px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.lookup{display:grid;grid-template-columns:1fr 170px 150px;gap:10px;align-items:end}
.check{display:flex;align-items:center;gap:9px;margin-top:16px}.check input{width:auto}
button{margin-top:22px;width:100%;padding:14px;border:0;border-radius:12px;font-weight:700;font-size:15px;cursor:pointer;background:#eef4fb;color:#08111b}
button.secondary{margin-top:0;background:#182332;color:#fff;border:1px solid #304052}
.note{margin-top:18px;color:#8290a1;font-size:13px;line-height:1.5}.msg{padding:12px 14px;border:1px solid #35506b;background:#102033;border-radius:10px;margin-bottom:14px}
code{color:#d3deea}.results{margin-top:12px;display:none;border:1px solid #273342;border-radius:12px;overflow:hidden}
.result{padding:12px 14px;border-bottom:1px solid #202a36;cursor:pointer;background:#0a1017}.result:last-child{border-bottom:0}.result:hover{background:#111b27}
.result strong{display:block}.result small{color:#93a1b3;display:block;margin-top:4px}.badge{display:inline-block;font-size:11px;padding:3px 7px;border:1px solid #33465c;border-radius:999px;margin-left:6px;color:#b9c8da}
.status{font-size:13px;color:#93a1b3;margin-top:8px}.section{margin-top:22px;padding-top:18px;border-top:1px solid #202a36}
details{margin-top:20px;border:1px solid #202a36;border-radius:12px;padding:12px 14px;background:#0a1017}summary{cursor:pointer;font-weight:700;color:#d7e2ee}
.preview-wrap{display:grid;grid-template-columns:190px 1fr;gap:18px;align-items:center;margin-top:18px;padding:16px;border:1px solid #263443;border-radius:14px;background:#090e14}
.preview-box{width:150px;height:90px;display:flex;align-items:center;justify-content:center;background:#05080c;border-radius:8px;overflow:hidden}.preview-box img{width:150px;height:90px;object-fit:contain}.preview-copy{color:#95a5b6;font-size:13px;line-height:1.5}
@media(max-width:700px){.grid,.lookup,.preview-wrap{grid-template-columns:1fr}}
</style>
</head>
<body>
<main><div class="card">
<h1>Satellite Picons Admin</h1>
<p class="sub">Pridanie nového kanála, aktualizácia loga, automatické odstránenie pozadia a náhľad pred publikovaním.</p>
{% with messages = get_flashed_messages() %}{% for m in messages %}<div class="msg">{{ m }}</div>{% endfor %}{% endwith %}

<div>
<label>Aktualizovať existujúci kanál</label>
<select id="existingChannel"><option value="">— Nový kanál —</option>{% for ch in channels %}<option value="{{ ch.id }}">{{ ch.name }}{% if ch.logo_version %} · logo v{{ ch.logo_version }}{% endif %}</option>{% endfor %}</select>
<div class="status">Ak stanica zmení logo, vyber ju tu. Reference a ostatné údaje sa zachovajú a nahradí sa iba aktuálne logo.</div>
</div>

<div class="section">
<div class="lookup">
<div><label>Vyhľadať nový kanál v databáze</label><input id="lookupName" placeholder="napr. JOJ KRIMI"></div>
<div><label>Orbita (voliteľné)</label><input id="lookupOrbit" placeholder="23.5E"></div>
<div><button type="button" class="secondary" id="lookupBtn">Nájsť</button></div>
</div>
<div id="lookupStatus" class="status"></div><div id="results" class="results"></div>
</div>

<form id="channelForm" method="post" enctype="multipart/form-data">
<div class="grid">
<div><label>ID kanála</label><input id="channelId" name="channel_id" placeholder="joj-krimi" required></div>
<div><label>Názov kanála</label><input id="channelName" name="name" placeholder="JOJ KRIMI" required></div>
</div>

<label>Originálne logo</label>
<input id="logoFile" name="logo" type="file" accept=".png,.svg,.jpg,.jpeg,.webp" required>

<div class="grid">
<div><label>Odstránenie pozadia</label><select id="backgroundRemoval" name="background_removal">
<option value="auto" selected>Automaticky (odporúčané)</option><option value="edge">Iba jednoduché/jednofarebné pozadie</option><option value="ai">AI odstránenie pozadia</option><option value="none">Bez odstránenia</option>
</select></div>
<div><label>Optická veľkosť loga</label><input id="opticalScale" name="optical_scale" type="number" step="0.01" min="0.50" max="1.50" value="1.00"></div>
</div>

<div class="preview-wrap"><div class="preview-box"><img id="previewImage" alt="Náhľad" style="display:none"></div><div class="preview-copy"><strong>Náhľad výsledného piconu</strong><br>Najprv vyber logo a potom klikni na tlačidlo. Náhľad používa rovnaké pozadie, veľkosť a spracovanie ako výsledný build.<button type="button" class="secondary" id="previewBtn" style="margin-top:12px">Vytvoriť náhľad</button><div id="previewStatus" class="status"></div></div></div>

<details>
<summary>Pokročilé nastavenia</summary>
<label>Enigma2 service reference</label><input id="serviceRef" name="service_reference" placeholder="Vyplní sa automaticky po výbere kanála z databázy">
<div class="grid">
<div><label>Varianty service type</label><input id="variants" name="variants" value="1,16,19"></div>
<div><label>Čierny/tmavý text → biely</label><select id="darkToWhite" name="dark_to_white"><option value="true" selected>Áno</option><option value="false">Nie</option></select></div>
</div>
<div class="status">Reference zostáva dostupná na kontrolu alebo ručnú opravu. Pri aktualizácii existujúceho loga sa automaticky zachová.</div>
</details>

<label class="check"><input type="checkbox" name="publish" checked>Po uložení automaticky commitnúť a pushnúť na GitHub</label>
<button type="submit" id="saveBtn">Uložiť a publikovať</button>
</form>
<p class="note">Originálny súbor sa archivuje v <code>assets/source-logos/</code>. Pre build sa uloží vyčistený transparentný PNG do <code>assets/logos/</code>. Git zachová históriu starších verzií loga.</p>
</div></main>
<script>
const channels={{ channels|tojson }};
const btn=document.querySelector('#lookupBtn'),results=document.querySelector('#results'),status=document.querySelector('#lookupStatus');
const existing=document.querySelector('#existingChannel'),saveBtn=document.querySelector('#saveBtn');
function slugify(v){return v.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]+/g,'-').replace(/^-+|-+$/g,'').slice(0,64)}
function esc(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
existing.addEventListener('change',()=>{const ch=channels.find(x=>x.id===existing.value);if(!ch){saveBtn.textContent='Uložiť a publikovať';return}document.querySelector('#channelId').value=ch.id;document.querySelector('#channelName').value=ch.name;document.querySelector('#serviceRef').value=ch.service_reference||'';document.querySelector('#variants').value=(ch.variant_types||['1','16','19']).join(',');document.querySelector('#darkToWhite').value=String(ch.dark_to_white!==false);document.querySelector('#opticalScale').value=ch.optical_scale||1.0;document.querySelector('#backgroundRemoval').value=ch.background_removal||'auto';saveBtn.textContent='Aktualizovať logo a publikovať'});
btn.addEventListener('click',async()=>{const q=document.querySelector('#lookupName').value.trim(),orbit=document.querySelector('#lookupOrbit').value.trim();if(!q){status.textContent='Zadaj názov kanála.';return}status.textContent='Hľadám v KingOfSat…';results.style.display='none';results.innerHTML='';try{const r=await fetch('/api/lookup?'+new URLSearchParams({q,orbit})),data=await r.json();if(!r.ok)throw new Error(data.error||'Vyhľadávanie zlyhalo');status.textContent=data.results.length?'Klikni na správny výsledok.':'Nič sa nenašlo.';if(!data.results.length)return;results.innerHTML=data.results.map((x,i)=>`<div class="result" data-i="${i}"><strong>${esc(x.name)} <span class="badge">${esc(x.orbit)}</span></strong><small>${esc(x.satellite)} • ${esc(x.frequency)} ${esc(x.polarization)} • SID ${x.sid} • TID ${x.tid} • NID ${x.nid}</small><small><code>${esc(x.service_reference)}</code></small></div>`).join('');results.style.display='block';[...results.querySelectorAll('.result')].forEach(el=>el.addEventListener('click',()=>{const x=data.results[Number(el.dataset.i)];existing.value='';document.querySelector('#channelName').value=x.name.replace(/\s+HD$/i,'');document.querySelector('#channelId').value=slugify(document.querySelector('#channelName').value);document.querySelector('#serviceRef').value=x.service_reference;document.querySelector('#lookupOrbit').value=x.orbit;saveBtn.textContent='Uložiť a publikovať';status.textContent='Vybrané: '+x.name+' ('+x.orbit+')'}))}catch(e){status.textContent='Chyba: '+e.message}});
document.querySelector('#previewBtn').addEventListener('click',async()=>{const file=document.querySelector('#logoFile').files[0],ps=document.querySelector('#previewStatus'),img=document.querySelector('#previewImage');if(!file){ps.textContent='Najprv vyber logo.';return}ps.textContent='Spracúvam náhľad…';const fd=new FormData();fd.append('logo',file);fd.append('background_removal',document.querySelector('#backgroundRemoval').value);fd.append('dark_to_white',document.querySelector('#darkToWhite').value);fd.append('optical_scale',document.querySelector('#opticalScale').value);try{const r=await fetch('/api/preview',{method:'POST',body:fd});if(!r.ok){const t=await r.text();throw new Error(t||'Náhľad zlyhal')}const blob=await r.blob();if(img.src)URL.revokeObjectURL(img.src);img.src=URL.createObjectURL(blob);img.style.display='block';ps.textContent='Pozadie: '+(r.headers.get('X-Background-Method')||'spracované')}catch(e){ps.textContent='Chyba: '+e.message}});
</script>
</body></html>
"""


def load_channels() -> list[dict]:
    cfg = yaml.safe_load(DB.read_text(encoding="utf-8")) or {}
    return cfg.get("channels", [])


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
    return f"1:0:{service_type:X}:{sid:X}:{tid:X}:{nid:X}:{orbit_to_namespace(orbit)}:0:0:0:"


def row_texts(tr):
    return [" ".join(td.stripped_strings) for td in tr.find_all(["td", "th"])]


def search_kingofsat(query: str, orbit_filter: str = "") -> list[dict]:
    params = {"aff": "list", "filtre": "no", "lim": "0", "ordre": "nom_ch", "question": query, "standard": "All"}
    headers = {"User-Agent": "Satellite-Picons-Admin/1.0 (+https://github.com/GrgoPitic/satellite-picons)"}
    r = requests.get(KINGOFSAT_SEARCH, params=params, headers=headers, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    wanted, current, results = normalize_orbit(orbit_filter), None, []
    for tr in soup.find_all("tr"):
        cells = row_texts(tr)
        if not cells:
            continue
        joined = " | ".join(cells)
        orbit_match = ORBIT_RE.search(joined)
        if orbit_match and re.search(r"\b\d{4,5}(?:\.\d+)?\b", joined):
            orbit = normalize_orbit(orbit_match.group(0))
            nums = [int(c) for c in cells[-4:] if re.fullmatch(r"\d+", c)]
            nid = tid = None
            if len(nums) >= 2:
                nid, tid = nums[-2], nums[-1]
            freq = next((c for c in cells if re.fullmatch(r"\d{4,5}(?:\.\d+)?", c)), "")
            pol = next((c for c in cells if c in {"H", "V", "L", "R"}), "")
            sat = next((c for c in cells if any(k in c.lower() for k in ("astra", "thor", "eutelsat", "hot bird", "hispa", "turksat", "amos", "intelsat"))), "")
            current = {"orbit": orbit, "frequency": freq, "polarization": pol, "satellite": sat, "nid": nid, "tid": tid}
            continue
        if not current or current["nid"] is None or current["tid"] is None or (wanted and current["orbit"] != wanted):
            continue
        if query.lower() not in joined.lower() or any(c.strip().upper() == "SID" for c in cells):
            continue
        name = next((c for c in cells if query.lower() in c.lower() and len(c) < 120), "")
        if not name:
            continue
        sid = None
        for c in cells[cells.index(name) + 1:]:
            if re.fullmatch(r"\d{1,5}", c) and 0 < int(c) <= 65535:
                sid = int(c)
                break
        if sid is None:
            continue
        try:
            service_ref = compose_service_reference(sid=sid, tid=current["tid"], nid=current["nid"], orbit=current["orbit"], name=name)
        except ValueError:
            continue
        item = {"name": html.unescape(name), "orbit": current["orbit"], "satellite": current["satellite"] or "Satellite", "frequency": current["frequency"], "polarization": current["polarization"], "sid": sid, "tid": current["tid"], "nid": current["nid"], "namespace": orbit_to_namespace(current["orbit"]), "service_reference": service_ref, "source": "KingOfSat"}
        if not any(x["service_reference"] == service_ref for x in results):
            results.append(item)
    return results[:30]


def image_from_upload(data: bytes, ext: str) -> Image.Image:
    if ext == ".svg":
        data = cairosvg.svg2png(bytestring=data)
    return Image.open(io.BytesIO(data)).convert("RGBA")


def has_transparency(im: Image.Image) -> bool:
    lo, _ = im.getchannel("A").getextrema()
    return lo < 245


def dominant_border_color(im: Image.Image) -> tuple[int, int, int] | None:
    im = im.convert("RGBA")
    w, h = im.size
    if not w or not h:
        return None
    samples = []
    step_x, step_y = max(1, w // 100), max(1, h // 100)
    for x in range(0, w, step_x):
        samples.extend([im.getpixel((x, 0)), im.getpixel((x, h - 1))])
    for y in range(0, h, step_y):
        samples.extend([im.getpixel((0, y)), im.getpixel((w - 1, y))])
    opaque = [(r, g, b) for r, g, b, a in samples if a > 200]
    if not opaque:
        return None
    quantized = [((r // 16) * 16, (g // 16) * 16, (b // 16) * 16) for r, g, b in opaque]
    return Counter(quantized).most_common(1)[0][0]


def remove_simple_background(im: Image.Image, tolerance: int = 42) -> tuple[Image.Image, float]:
    im = im.convert("RGBA")
    bg = dominant_border_color(im)
    if bg is None:
        return im, 0.0
    px = im.load()
    w, h = im.size
    seen, stack, removed = set(), [], 0
    for x in range(w):
        stack.extend(((x, 0), (x, h - 1)))
    for y in range(h):
        stack.extend(((0, y), (w - 1, y)))
    def close(c):
        r, g, b, a = c
        return a > 0 and max(abs(r-bg[0]), abs(g-bg[1]), abs(b-bg[2])) <= tolerance
    while stack:
        x, y = stack.pop()
        if (x, y) in seen or not (0 <= x < w and 0 <= y < h):
            continue
        seen.add((x, y))
        if not close(px[x, y]):
            continue
        r, g, b, _ = px[x, y]
        px[x, y] = (r, g, b, 0)
        removed += 1
        stack.extend(((x+1,y),(x-1,y),(x,y+1),(x,y-1)))
    return im, removed / max(1, w*h)


def remove_ai_background(im: Image.Image) -> Image.Image:
    global _REMBG_SESSION
    try:
        from rembg import new_session, remove
    except ImportError as exc:
        raise RuntimeError("AI odstránenie pozadia nie je nainštalované. Spusť admin.command, ktorý doinštaluje admin závislosti.") from exc
    if _REMBG_SESSION is None:
        _REMBG_SESSION = new_session("u2netp")
    return remove(im.convert("RGBA"), session=_REMBG_SESSION).convert("RGBA")


def process_background(im: Image.Image, mode: str) -> tuple[Image.Image, str]:
    mode = mode if mode in {"auto", "edge", "ai", "none"} else "auto"
    if mode == "none":
        return im.convert("RGBA"), "bez odstránenia"
    if mode == "ai":
        return remove_ai_background(im), "AI (u2netp)"
    if has_transparency(im):
        return im.convert("RGBA"), "transparentné logo – bez zásahu"
    simple, ratio = remove_simple_background(im)
    if mode == "edge":
        return simple, "jednoduché pozadie"
    if ratio >= 0.03:
        return simple, "automaticky – jednoduché pozadie"
    return remove_ai_background(im), "automaticky – AI (u2netp)"


def recolor_neutral_dark_to_white(im: Image.Image) -> Image.Image:
    im = im.convert("RGBA")
    out = []
    for r, g, b, a in list(im.getdata()):
        if a == 0:
            out.append((r, g, b, a)); continue
        mx, mn = max(r, g, b), min(r, g, b)
        if mx <= 105 and mx - mn <= 28:
            lum = (r + g + b) / 3
            v = max(230, min(255, int(230 + (105 - lum) / 105 * 25)))
            out.append((v, v, v, a))
        else:
            out.append((r, g, b, a))
    im.putdata(out)
    return im


def trim_alpha(im: Image.Image) -> Image.Image:
    bbox = im.getchannel("A").getbbox()
    if not bbox:
        raise ValueError("Po odstránení pozadia nezostal žiadny obsah loga.")
    return im.crop(bbox)


def fit_logo(im: Image.Image, optical_scale: float) -> Image.Image:
    im = trim_alpha(im)
    w, h = im.size
    optical_scale = max(0.50, min(1.50, optical_scale))
    scale = min(MAX_LOGO[0]/w, MAX_LOGO[1]/h) * optical_scale
    nw, nh = max(1, round(w*scale)), max(1, round(h*scale))
    if nw > MAX_LOGO[0] or nh > MAX_LOGO[1]:
        cap = min(MAX_LOGO[0]/nw, MAX_LOGO[1]/nh)
        nw, nh = max(1, round(nw*cap)), max(1, round(nh*cap))
    return im.resize((nw, nh), Image.Resampling.LANCZOS)


def render_picon(processed: Image.Image, dark_to_white: bool, optical_scale: float) -> Image.Image:
    logo = processed.convert("RGBA")
    if dark_to_white:
        logo = recolor_neutral_dark_to_white(logo)
    logo = fit_logo(logo, optical_scale)
    template = Image.open(TEMPLATE).convert("RGBA")
    out = template.copy()
    out.alpha_composite(logo, ((CANVAS[0]-logo.width)//2, (CANVAS[1]-logo.height)//2))
    return out


def run_git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=False)


@app.get("/api/lookup")
def api_lookup():
    q, orbit = request.args.get("q", "").strip(), request.args.get("orbit", "").strip()
    if len(q) < 2:
        return jsonify(error="Zadaj aspoň 2 znaky názvu kanála."), 400
    try:
        return jsonify(results=search_kingofsat(q, orbit))
    except requests.RequestException as exc:
        return jsonify(error=f"KingOfSat nie je dostupný: {exc}"), 502
    except Exception as exc:
        return jsonify(error=str(exc)), 500


@app.post("/api/preview")
def api_preview():
    try:
        upload = request.files["logo"]
        ext = Path(secure_filename(upload.filename or "")).suffix.lower()
        if ext not in SUPPORTED:
            raise ValueError("Nepodporovaný formát loga.")
        im = image_from_upload(upload.read(), ext)
        processed, method = process_background(im, request.form.get("background_removal", "auto"))
        picon = render_picon(processed, request.form.get("dark_to_white", "true") == "true", float(request.form.get("optical_scale", "1.0")))
        buf = io.BytesIO(); picon.save(buf, format="PNG", optimize=True); buf.seek(0)
        response = send_file(buf, mimetype="image/png", max_age=0)
        response.headers["X-Background-Method"] = method
        return response
    except Exception as exc:
        return str(exc), 400


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_template_string(PAGE, channels=load_channels())
    try:
        channel_id = request.form["channel_id"].strip().lower()
        name = request.form["name"].strip()
        ref = request.form.get("service_reference", "").strip()
        variants = [x.strip().upper() for x in request.form.get("variants", "1,16,19").split(",") if x.strip()]
        dark_to_white = request.form.get("dark_to_white", "true") == "true"
        optical_scale = float(request.form.get("optical_scale", "1.00"))
        background_mode = request.form.get("background_removal", "auto")
        publish = request.form.get("publish") == "on"
        upload = request.files["logo"]
        if not ID_RE.match(channel_id):
            raise ValueError("ID môže obsahovať iba malé písmená, čísla a pomlčky.")
        if not name:
            raise ValueError("Názov kanála je povinný.")
        if not 0.50 <= optical_scale <= 1.50:
            raise ValueError("Optická veľkosť musí byť medzi 0.50 a 1.50.")
        if not variants:
            raise ValueError("Musí byť zadaný aspoň jeden service type variant.")
        cfg = yaml.safe_load(DB.read_text(encoding="utf-8")) or {"channels": []}
        channels = cfg.setdefault("channels", [])
        existing = next((ch for ch in channels if ch.get("id") == channel_id), None)
        if not ref and existing:
            ref = existing.get("service_reference", "")
        if not ref:
            raise ValueError("Najprv vyhľadaj a vyber nový kanál z databázy, alebo zadaj service reference v Pokročilých nastaveniach.")
        validate_ref(ref)
        original_name = secure_filename(upload.filename or "")
        ext = Path(original_name).suffix.lower()
        if ext not in SUPPORTED:
            raise ValueError("Nepodporovaný formát loga.")
        raw = upload.read()
        if not raw:
            raise ValueError("Logo je prázdne.")
        im = image_from_upload(raw, ext)
        processed, background_method = process_background(im, background_mode)
        processed = trim_alpha(processed)
        LOGOS.mkdir(parents=True, exist_ok=True); SOURCE_LOGOS.mkdir(parents=True, exist_ok=True)
        for old in SOURCE_LOGOS.glob(channel_id + ".*"):
            if old.suffix.lower() in SUPPORTED:
                old.unlink()
        source_dest = SOURCE_LOGOS / f"{channel_id}{ext}"
        source_dest.write_bytes(raw)
        processed_dest = LOGOS / f"{channel_id}.png"
        processed.save(processed_dest, format="PNG", optimize=True)
        now = datetime.now(timezone.utc).isoformat()
        version = (int(existing.get("logo_version", 1)) + 1) if existing else 1
        entry = {
            "id": channel_id,
            "name": name,
            "logo": str(processed_dest.relative_to(ROOT)),
            "source_logo": str(source_dest.relative_to(ROOT)),
            "logo_version": version,
            "updated_at": now,
            "service_reference": ref,
            "variant_types": variants,
            "dark_to_white": dark_to_white,
            "optical_scale": optical_scale,
            "background_removal": background_mode,
            "background_method": background_method,
            "edge_cleanup": False,
        }
        if existing:
            channels[channels.index(existing)] = entry
        else:
            channels.append(entry)
        DB.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
        if publish:
            add = run_git("add", "-A", "assets/logos", "assets/source-logos", "channels.yml")
            if add.returncode != 0:
                raise RuntimeError(add.stderr.strip() or "git add zlyhal")
            message = f"Update {name} logo to v{version}" if existing else f"Add {name} picon"
            commit = run_git("commit", "-m", message)
            if commit.returncode != 0 and "nothing to commit" not in (commit.stdout + commit.stderr).lower():
                raise RuntimeError(commit.stderr.strip() or commit.stdout.strip() or "git commit zlyhal")
            push = run_git("push")
            if push.returncode != 0:
                raise RuntimeError(push.stderr.strip() or push.stdout.strip() or "git push zlyhal")
            flash(f"{name}: {'logo aktualizované' if existing else 'pridané'} · verzia {version} · publikované na GitHub.")
        else:
            flash(f"{name}: {'logo aktualizované' if existing else 'pridané'} lokálne · verzia {version}.")
    except Exception as exc:
        flash(f"Chyba: {exc}")
    return redirect(url_for("index"))


def main():
    url = "http://127.0.0.1:8765"
    print(f"Satellite Picons Admin: {url}")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    app.run(host="127.0.0.1", port=8765, debug=False)


if __name__ == "__main__":
    main()
