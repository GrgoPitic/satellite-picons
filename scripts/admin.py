#!/usr/bin/env python3
from __future__ import annotations

import html
import re
import shutil
import subprocess
import urllib.parse
import webbrowser
from pathlib import Path

import requests
import yaml
from bs4 import BeautifulSoup
from flask import Flask, flash, jsonify, redirect, render_template_string, request, url_for
from werkzeug.utils import secure_filename

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "channels.yml"
LOGOS = ROOT / "assets" / "logos"
SUPPORTED = {".png", ".svg", ".jpg", ".jpeg", ".webp"}
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
ORBIT_RE = re.compile(r"(?P<deg>\d+(?:\.\d+)?)\s*°?\s*(?P<dir>[EW])", re.I)
KINGOFSAT_SEARCH = "https://en.kingofsat.net/find.php"

app = Flask(__name__)
app.secret_key = "satellite-picons-local-admin"

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
main{width:min(900px,calc(100% - 32px));margin:40px auto 80px}
.card{background:#0d131b;border:1px solid #202a36;border-radius:18px;padding:22px}
h1{margin:0 0 8px;font-size:34px}.sub{color:#93a1b3;margin:0 0 24px}
label{display:block;font-size:13px;color:#a9b6c6;margin:16px 0 7px}
input,select{width:100%;padding:13px 14px;border-radius:11px;border:1px solid #2a3543;background:#090e14;color:#fff;font-size:15px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.lookup{display:grid;grid-template-columns:1fr 170px 150px;gap:10px;align-items:end}
.check{display:flex;align-items:center;gap:9px;margin-top:16px}.check input{width:auto}
button{margin-top:22px;width:100%;padding:14px;border:0;border-radius:12px;font-weight:700;font-size:15px;cursor:pointer}
button.secondary{margin-top:0;background:#182332;color:#fff;border:1px solid #304052}
.note{margin-top:18px;color:#8290a1;font-size:13px;line-height:1.5}
.msg{padding:12px 14px;border:1px solid #35506b;background:#102033;border-radius:10px;margin-bottom:14px}
code{color:#d3deea}
.results{margin-top:12px;display:none;border:1px solid #273342;border-radius:12px;overflow:hidden}
.result{padding:12px 14px;border-bottom:1px solid #202a36;cursor:pointer;background:#0a1017}
.result:last-child{border-bottom:0}.result:hover{background:#111b27}
.result strong{display:block}.result small{color:#93a1b3;display:block;margin-top:4px}
.badge{display:inline-block;font-size:11px;padding:3px 7px;border:1px solid #33465c;border-radius:999px;margin-left:6px;color:#b9c8da}
.status{font-size:13px;color:#93a1b3;margin-top:8px}
@media(max-width:700px){.grid,.lookup{grid-template-columns:1fr}}
</style>
</head>
<body>
<main>
  <div class="card">
    <h1>Satellite Picons Admin</h1>
    <p class="sub">Logo + automatické vyhľadanie Enigma2 service reference z KingOfSat.</p>

    {% with messages = get_flashed_messages() %}
      {% for m in messages %}<div class="msg">{{ m }}</div>{% endfor %}
    {% endwith %}

    <div class="lookup">
      <div>
        <label>Vyhľadať kanál v databáze</label>
        <input id="lookupName" placeholder="napr. JOJ KRIMI">
      </div>
      <div>
        <label>Orbita (voliteľné)</label>
        <input id="lookupOrbit" placeholder="23.5E">
      </div>
      <div><button type="button" class="secondary" id="lookupBtn">Nájsť</button></div>
    </div>
    <div id="lookupStatus" class="status"></div>
    <div id="results" class="results"></div>

    <form method="post" enctype="multipart/form-data">
      <div class="grid">
        <div>
          <label>ID kanála</label>
          <input id="channelId" name="channel_id" placeholder="joj-krimi" required>
        </div>
        <div>
          <label>Názov kanála</label>
          <input id="channelName" name="name" placeholder="JOJ KRIMI" required>
        </div>
      </div>

      <label>Originálne logo</label>
      <input name="logo" type="file" accept=".png,.svg,.jpg,.jpeg,.webp" required>

      <label>Enigma2 service reference</label>
      <input id="serviceRef" name="service_reference" placeholder="1:0:19:334F:C93:3:EB0000:0:0:0:" required>

      <div class="grid">
        <div>
          <label>Varianty service type</label>
          <input name="variants" value="1,16,19">
        </div>
        <div>
          <label>Čierny/tmavý text → biely</label>
          <select name="dark_to_white">
            <option value="true" selected>Áno</option>
            <option value="false">Nie</option>
          </select>
        </div>
      </div>

      <label class="check">
        <input type="checkbox" name="publish" checked>
        Po uložení automaticky commitnúť a pushnúť na GitHub
      </label>

      <button type="submit">Uložiť a publikovať</button>
    </form>

    <form method="post" action="/publish">
      <button type="submit" class="secondary">Publikovať už uložené lokálne zmeny</button>
    </form>

    <p class="note">
      Zdroj satelitných údajov: KingOfSat. Pred publikovaním sa vybraná reference zobrazí v poli a môžeš ju ručne skontrolovať/upraviť.
      Admin počúva iba na <code>127.0.0.1</code>.
    </p>
  </div>
</main>
<script>
const btn=document.querySelector('#lookupBtn');
const results=document.querySelector('#results');
const status=document.querySelector('#lookupStatus');

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
</body>
</html>
"""

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

def run_git(*args: str, timeout: int = 45) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Git operácia prekročila časový limit.") from exc

def publish_pending_changes() -> str:
    fetch = run_git("fetch", "origin", "main")
    if fetch.returncode != 0:
        raise RuntimeError(fetch.stderr.strip() or fetch.stdout.strip() or "Načítanie origin/main zlyhalo.")

    rebase = run_git("rebase", "--autostash", "FETCH_HEAD")
    if rebase.returncode != 0:
        run_git("rebase", "--abort")
        raise RuntimeError(rebase.stderr.strip() or rebase.stdout.strip() or "Synchronizácia s origin/main zlyhala.")

    add = run_git("add", "channels.yml", "assets/logos")
    if add.returncode != 0:
        raise RuntimeError(add.stderr.strip() or "git add zlyhal")

    diff = run_git("diff", "--cached", "--quiet")
    if diff.returncode not in (0, 1):
        raise RuntimeError(diff.stderr.strip() or "Kontrola zmien zlyhala.")

    if diff.returncode == 1:
        commit = run_git("commit", "-m", "Update satellite picons")
        if commit.returncode != 0:
            raise RuntimeError(commit.stderr.strip() or commit.stdout.strip() or "git commit zlyhal")

    ahead = run_git("rev-list", "--count", "FETCH_HEAD..HEAD")
    if ahead.returncode != 0:
        raise RuntimeError(ahead.stderr.strip() or "Kontrola lokálnych commitov zlyhala.")

    try:
        ahead_count = int(ahead.stdout.strip() or "0")
    except ValueError:
        ahead_count = 0

    if ahead_count == 0:
        return "Nie sú žiadne lokálne zmeny ani čakajúce commity na publikovanie."

    push = run_git("push", "origin", "HEAD:main", timeout=120)
    if push.returncode != 0:
        raise RuntimeError(push.stderr.strip() or push.stdout.strip() or "git push zlyhal")

    return f"Publikované na GitHub: {ahead_count} lokálny commit."

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
        return render_template_string(PAGE)

    try:
        channel_id = request.form["channel_id"].strip().lower()
        name = request.form["name"].strip()
        ref = request.form["service_reference"].strip()
        variants = [x.strip().upper() for x in request.form.get("variants", "1,16,19").split(",") if x.strip()]
        dark_to_white = request.form.get("dark_to_white", "true") == "true"
        publish = request.form.get("publish") == "on"
        upload = request.files["logo"]

        if not ID_RE.match(channel_id):
            raise ValueError("ID môže obsahovať iba malé písmená, čísla a pomlčky.")
        if not name:
            raise ValueError("Názov kanála je povinný.")
        validate_ref(ref)
        if not variants:
            raise ValueError("Musí byť zadaný aspoň jeden service type variant.")

        original_name = secure_filename(upload.filename or "")
        ext = Path(original_name).suffix.lower()
        if ext not in SUPPORTED:
            raise ValueError("Nepodporovaný formát loga.")

        LOGOS.mkdir(parents=True, exist_ok=True)

        for old in LOGOS.glob(channel_id + ".*"):
            if old.suffix.lower() in SUPPORTED:
                old.unlink()

        dest = LOGOS / f"{channel_id}{ext}"
        upload.save(dest)

        cfg = yaml.safe_load(DB.read_text(encoding="utf-8"))
        entry = {
            "id": channel_id,
            "name": name,
            "logo": str(dest.relative_to(ROOT)),
            "service_reference": ref,
            "variant_types": variants,
            "dark_to_white": dark_to_white,
        }

        channels = cfg.setdefault("channels", [])
        for i, ch in enumerate(channels):
            if ch.get("id") == channel_id:
                channels[i] = entry
                break
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
    print(f"Satellite Picons Admin: {url}")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    app.run(host="127.0.0.1", port=8765, debug=False)

if __name__ == "__main__":
    main()
