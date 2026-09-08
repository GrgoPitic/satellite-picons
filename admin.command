#!/bin/zsh
set -euo pipefail
cd "$(dirname "$0")"

# Finder/Dock launches apps with a minimal PATH. Make Homebrew and system
# binaries available before looking for brew/python.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

# Make Homebrew libraries (especially cairo) visible to Python/cairocffi on Apple Silicon.
if command -v brew >/dev/null 2>&1; then
  BREW_PREFIX="$(brew --prefix)"
  CAIRO_PREFIX="$(brew --prefix cairo 2>/dev/null || true)"
  export PATH="$BREW_PREFIX/bin:$PATH"
  if [ -n "$CAIRO_PREFIX" ]; then
    export DYLD_FALLBACK_LIBRARY_PATH="$CAIRO_PREFIX/lib:${DYLD_FALLBACK_LIBRARY_PATH:-}"
    export PKG_CONFIG_PATH="$CAIRO_PREFIX/lib/pkgconfig:${PKG_CONFIG_PATH:-}"
  fi
fi

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate

STAMP_FILE=".venv/.satellite-picons-admin-requirements.sha256"
REQ_HASH="$(
  cat requirements.txt requirements-admin.txt 2>/dev/null     | /usr/bin/shasum -a 256     | /usr/bin/awk '{print $1}'
)"

NEED_INSTALL=0
if [ ! -f "$STAMP_FILE" ] || [ "$(<"$STAMP_FILE")" != "$REQ_HASH" ]; then
  NEED_INSTALL=1
else
  python - <<'PY' >/dev/null 2>&1 || NEED_INSTALL=1
import flask
import requests
import bs4
import PIL
import yaml
PY
fi

if [ "$NEED_INSTALL" -eq 1 ]; then
  echo "Satellite Picons Admin: aktualizujem lokálne závislosti..."
  python -m pip install -q -r requirements-admin.txt
  print -r -- "$REQ_HASH" > "$STAMP_FILE"
fi

exec python scripts/admin.py
