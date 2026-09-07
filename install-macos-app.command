#!/bin/zsh
set -e

cd "$(dirname "$0")"
REPO_DIR="$(pwd)"
APP_NAME="Satellite Picons Admin"
APP_DIR="$HOME/Applications/$APP_NAME.app"
TMP_SCRIPT="$(mktemp -t satellite-picons-admin.XXXXXX.applescript)"
ICON_SVG="$REPO_DIR/assets/app-icon.svg"
ICON_WORK="$(mktemp -d -t satellite-picons-icon.XXXXXX)"
ICONSET="$ICON_WORK/AppIcon.iconset"
ICON_PNG="$ICON_WORK/AppIcon-1024.png"
ICON_ICNS="$ICON_WORK/AppIcon.icns"

mkdir -p "$HOME/Applications"

cat > "$TMP_SCRIPT" <<EOF
on run
    set repoPath to "$REPO_DIR"
    set adminURL to "http://127.0.0.1:8765"

    try
        do shell script "/usr/bin/curl -fsS --max-time 1 " & quoted form of adminURL & " >/dev/null 2>&1"
        do shell script "/usr/bin/open " & quoted form of adminURL
        return
    end try

    do shell script "/usr/bin/nohup /bin/zsh " & quoted form of (repoPath & "/admin.command") & " >/tmp/satellite-picons-admin.log 2>&1 &"

    repeat with i from 1 to 300
        delay 1
        try
            do shell script "/usr/bin/curl -fsS --max-time 1 " & quoted form of adminURL & " >/dev/null 2>&1"
            do shell script "/usr/bin/open " & quoted form of adminURL
            return
        end try
    end repeat

    display dialog "Satellite Picons Admin sa nepodarilo spustiť. Skontroluj /tmp/satellite-picons-admin.log" buttons {"OK"} default button "OK" with icon stop
end run
EOF

rm -rf "$APP_DIR"
/usr/bin/osacompile -o "$APP_DIR" "$TMP_SCRIPT"

if [ -f "$ICON_SVG" ]; then
  if [ ! -d "$REPO_DIR/.venv" ]; then
    /usr/bin/python3 -m venv "$REPO_DIR/.venv"
  fi

  source "$REPO_DIR/.venv/bin/activate"
  python -m pip install -q -r "$REPO_DIR/requirements.txt"

  python - "$ICON_SVG" "$ICON_PNG" <<'PY'
import sys
import cairosvg
cairosvg.svg2png(
    url=sys.argv[1],
    write_to=sys.argv[2],
    output_width=1024,
    output_height=1024,
)
PY

  mkdir -p "$ICONSET"
  /usr/bin/sips -z 16 16 "$ICON_PNG" --out "$ICONSET/icon_16x16.png" >/dev/null
  /usr/bin/sips -z 32 32 "$ICON_PNG" --out "$ICONSET/icon_16x16@2x.png" >/dev/null
  /usr/bin/sips -z 32 32 "$ICON_PNG" --out "$ICONSET/icon_32x32.png" >/dev/null
  /usr/bin/sips -z 64 64 "$ICON_PNG" --out "$ICONSET/icon_32x32@2x.png" >/dev/null
  /usr/bin/sips -z 128 128 "$ICON_PNG" --out "$ICONSET/icon_128x128.png" >/dev/null
  /usr/bin/sips -z 256 256 "$ICON_PNG" --out "$ICONSET/icon_128x128@2x.png" >/dev/null
  /usr/bin/sips -z 256 256 "$ICON_PNG" --out "$ICONSET/icon_256x256.png" >/dev/null
  /usr/bin/sips -z 512 512 "$ICON_PNG" --out "$ICONSET/icon_256x256@2x.png" >/dev/null
  /usr/bin/sips -z 512 512 "$ICON_PNG" --out "$ICONSET/icon_512x512.png" >/dev/null
  /usr/bin/cp "$ICON_PNG" "$ICONSET/icon_512x512@2x.png"

  /usr/bin/iconutil -c icns "$ICONSET" -o "$ICON_ICNS"
  /bin/cp "$ICON_ICNS" "$APP_DIR/Contents/Resources/AppIcon.icns"

  /usr/libexec/PlistBuddy -c "Delete :CFBundleIconFile" "$APP_DIR/Contents/Info.plist" >/dev/null 2>&1 || true
  /usr/libexec/PlistBuddy -c "Add :CFBundleIconFile string AppIcon.icns" "$APP_DIR/Contents/Info.plist"
  /usr/libexec/PlistBuddy -c "Delete :CFBundleDisplayName" "$APP_DIR/Contents/Info.plist" >/dev/null 2>&1 || true
  /usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string Satellite Picons Admin" "$APP_DIR/Contents/Info.plist"

  /usr/bin/codesign --force --deep --sign - "$APP_DIR" >/dev/null 2>&1 || true
  /usr/bin/touch "$APP_DIR"
fi

rm -f "$TMP_SCRIPT"
rm -rf "$ICON_WORK"

/usr/bin/open -R "$APP_DIR"
