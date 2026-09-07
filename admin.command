#!/bin/zsh
set -e
cd "$(dirname "$0")"

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
python -m pip install -q -r requirements-admin.txt
exec python scripts/admin.py
