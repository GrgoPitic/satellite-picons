#!/bin/zsh
set -e
cd "$(dirname "$0")"

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git pull --ff-only || echo "Upozornenie: git pull sa nepodaril; spúšťam lokálnu verziu."
fi

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install -q -r requirements-admin.txt
exec python scripts/admin.py
