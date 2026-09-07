#!/usr/bin/env python3
from __future__ import annotations

import re
import shutil
import subprocess
import webbrowser
from pathlib import Path

import yaml
from flask import Flask, flash, redirect, render_template_string, request, url_for
from werkzeug.utils import secure_filename

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "channels.yml"
LOGOS = ROOT / "assets" / "logos"
SUPPORTED = {".png", ".svg", ".jpg", ".jpeg", ".webp"}
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")

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
main{width:min(780px,calc(100% - 32px));margin:40px auto 80px}
.card{background:#0d131b;border:1px solid #202a36;border-radius:18px;padding:22px}
h1{margin:0 0 8px;font-size:34px}.sub{color:#93a1b3;margin:0 0 24px}
label{display:block;font-size:13px;color:#a9b6c6;margin:16px 0 7px}
input,select{width:100%;padding:13px 14px;border-radius:11px;border:1px solid #2a3543;background:#090e14;color:#fff;font-size:15px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.check{display:flex;align-items:center;gap:9px;margin-top:16px}.check input{width:auto}
button{margin-top:22px;width:100%;padding:14px;border:0;border-radius:12px;font-weight:700;font-size:15px;cursor:pointer}
.note{margin-top:18px;color:#8290a1;font-size:13px;line-height:1.5}
.msg{padding:12px 14px;border:1px solid #35506b;background:#102033;border-radius:10px;margin-bottom:14px}
code{color:#d3deea}
@media(max-width:640px){.grid{grid-template-columns:1fr}}
</style>
</head>
<body>
<main>
  <div class="card">
    <h1>Satellite Picons Admin</h1>
    <p class="sub">Lokálny admin iba pre teba. Logo sa uloží, channels.yml sa upraví a voliteľne sa všetko publikuje na GitHub.</p>

    {% with messages = get_flashed_messages() %}
      {% for m in messages %}<div class="msg">{{ m }}</div>{% endfor %}
    {% endwith %}

    <form method="post" enctype="multipart/form-data">
      <div class="grid">
        <div>
          <label>ID kanála</label>
          <input name="channel_id" placeholder="joj-sport-2" required>
        </div>
        <div>
          <label>Názov kanála</label>
          <input name="name" placeholder="JOJ ŠPORT 2" required>
        </div>
      </div>

      <label>Originálne logo</label>
      <input name="logo" type="file" accept=".png,.svg,.jpg,.jpeg,.webp" required>

      <label>Enigma2 service reference</label>
      <input name="service_reference" placeholder="1:0:19:30C:C94:3:EB0000:0:0:0:" required>

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

    <p class="note">
      Podporované: <code>PNG, SVG, JPG, JPEG, WEBP</code>. Server počúva iba na <code>127.0.0.1</code>, takže nie je verejne dostupný.
    </p>
  </div>
</main>
</body>
</html>
"""

def validate_ref(ref: str) -> None:
    parts = [p for p in ref.strip().strip(":").split(":")]
    if len(parts) != 10:
        raise ValueError("Service reference musí mať presne 10 polí oddelených dvojbodkou.")

def run_git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

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

        # Remove previous asset for the same channel ID if its extension changed.
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
            add = run_git("add", str(dest.relative_to(ROOT)), "channels.yml")
            if add.returncode != 0:
                raise RuntimeError(add.stderr.strip() or "git add zlyhal")

            commit = run_git("commit", "-m", f"Add/update {name} picon")
            if commit.returncode != 0 and "nothing to commit" not in (commit.stdout + commit.stderr).lower():
                raise RuntimeError(commit.stderr.strip() or commit.stdout.strip() or "git commit zlyhal")

            push = run_git("push")
            if push.returncode != 0:
                raise RuntimeError(push.stderr.strip() or push.stdout.strip() or "git push zlyhal")

            flash(f"{name}: uložené a publikované na GitHub.")
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
