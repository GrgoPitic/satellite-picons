#!/bin/zsh
set -euo pipefail

cd "$(dirname "$0")"
REPO_DIR="$(pwd)"
APP_NAME="Satellite Picons Admin"
APP_DIR="$HOME/Applications/$APP_NAME.app"
APP_CONTENTS="$APP_DIR/Contents"
APP_MACOS="$APP_CONTENTS/MacOS"
APP_RESOURCES="$APP_CONTENTS/Resources"
SWIFT_SOURCE="$REPO_DIR/macos/SatellitePiconsAdmin.swift"
ICON_SVG="$REPO_DIR/assets/app-icon.svg"
ICON_WORK="$(mktemp -d -t satellite-picons-icon.XXXXXX)"
ICONSET="$ICON_WORK/AppIcon.iconset"
ICON_PNG="$ICON_WORK/AppIcon-1024.png"
ICON_ICNS="$ICON_WORK/AppIcon.icns"

cleanup() {
  rm -rf "$ICON_WORK"
}
trap cleanup EXIT

if ! command -v swiftc >/dev/null 2>&1; then
  echo "CHYBA: swiftc sa nenašiel."
  echo "Nainštaluj Xcode Command Line Tools: xcode-select --install"
  exit 1
fi

mkdir -p "$HOME/Applications"
rm -rf "$APP_DIR"
mkdir -p "$APP_MACOS" "$APP_RESOURCES"

echo "===== 1. KOMPILUJEM NATÍVNU MACOS APLIKÁCIU ====="

/usr/bin/xcrun swiftc   -O   -framework AppKit   -framework Foundation   "$SWIFT_SOURCE"   -o "$APP_MACOS/SatellitePiconsAdmin.bin"

cat > "$APP_MACOS/SatellitePiconsAdmin" <<EOF
#!/bin/zsh
exec "$(dirname "$0")/SatellitePiconsAdmin.bin" "$REPO_DIR"
EOF
chmod +x "$APP_MACOS/SatellitePiconsAdmin"

cat > "$APP_CONTENTS/Info.plist" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key>
  <string>sk</string>
  <key>CFBundleDisplayName</key>
  <string>Satellite Picons Admin</string>
  <key>CFBundleExecutable</key>
  <string>SatellitePiconsAdmin</string>
  <key>CFBundleIdentifier</key>
  <string>io.github.grgopitic.satellitepicons.admin</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleName</key>
  <string>Satellite Picons Admin</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>2.0</string>
  <key>CFBundleVersion</key>
  <string>2</string>
  <key>LSMinimumSystemVersion</key>
  <string>14.0</string>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
EOF

echo "===== 2. PRIPRAVUJEM IKONU ====="

if [ -f "$ICON_SVG" ]; then
  if [ ! -d "$REPO_DIR/.venv" ]; then
    /usr/bin/python3 -m venv "$REPO_DIR/.venv"
  fi

  source "$REPO_DIR/.venv/bin/activate"

  STAMP_FILE="$REPO_DIR/.venv/.satellite-picons-icon-requirements.sha256"
  REQ_HASH="$(
    cat "$REPO_DIR/requirements.txt"       | /usr/bin/shasum -a 256       | /usr/bin/awk '{print $1}'
  )"

  if [ ! -f "$STAMP_FILE" ] || [ "$(<"$STAMP_FILE")" != "$REQ_HASH" ]; then
    python -m pip install -q -r "$REPO_DIR/requirements.txt"
    print -r -- "$REQ_HASH" > "$STAMP_FILE"
  fi

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
  /bin/cp "$ICON_PNG" "$ICONSET/icon_512x512@2x.png"

  /usr/bin/iconutil -c icns "$ICONSET" -o "$ICON_ICNS"
  /bin/cp "$ICON_ICNS" "$APP_RESOURCES/AppIcon.icns"

  /usr/libexec/PlistBuddy     -c "Add :CFBundleIconFile string AppIcon.icns"     "$APP_CONTENTS/Info.plist"
fi

echo "===== 3. PODPISUJEM APLIKÁCIU ====="

/usr/bin/codesign   --force   --deep   --sign -   --timestamp=none   "$APP_DIR"

echo "===== 4. OVERUJEM ====="

/usr/bin/codesign   --verify   --deep   --strict   --verbose=2   "$APP_DIR"

echo
echo "=========================================="
echo "HOTOVO"
echo "=========================================="
echo "Aplikácia: $APP_DIR"
echo
echo "Nová verzia:"
echo "  - nezamŕza počas štartu"
echo "  - závislosti neinštaluje pri každom kliknutí"
echo "  - má vlastné menu v hornej lište"
echo "  - Zastaviť Admin korektne ukončí lokálny server"
echo "  - Ukončiť aplikáciu ukončí aj admin server"
echo

/usr/bin/open -R "$APP_DIR"
