#!/bin/zsh
set -e

cd "$(dirname "$0")"
REPO_DIR="$(pwd)"
APP_NAME="Satellite Picons Admin"
APP_DIR="$HOME/Applications/$APP_NAME.app"
TMP_SCRIPT="$(mktemp -t satellite-picons-admin.XXXXXX.applescript)"

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

    repeat with i from 1 to 120
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
rm -f "$TMP_SCRIPT"

echo
echo "Hotovo:"
echo "$APP_DIR"
echo
echo "Aplikáciu môžeš spustiť z Finder → Applications alebo ju potiahnuť do Docku."
echo "Pri kliknutí spustí admin na pozadí a otvorí http://127.0.0.1:8765"
echo
/usr/bin/open -R "$APP_DIR"
