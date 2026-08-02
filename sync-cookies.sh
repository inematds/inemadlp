#!/usr/bin/env bash
# Extrai os cookies do Firefox local e envia para o inemadlp.
# Uso: DLP_URL=https://dlp.exemplo DLP_UPLOAD_TOKEN=... ./sync-cookies.sh
set -euo pipefail

PERFIL="${FIREFOX_PROFILE:-$HOME/snap/firefox/common/.mozilla/firefox/kklk8j7a.default}"
: "${DLP_URL:?defina DLP_URL}"
: "${DLP_UPLOAD_TOKEN:?defina DLP_UPLOAD_TOKEN}"

TEMP="$(mktemp -d)"
trap 'rm -rf "$TEMP"' EXIT

# Os cookies recentes vivem no WAL: copiar só o .sqlite traz dados velhos.
for sufixo in "" "-wal" "-shm"; do
  [ -f "$PERFIL/cookies.sqlite$sufixo" ] && cp "$PERFIL/cookies.sqlite$sufixo" "$TEMP/"
done

python3 - "$TEMP/cookies.sqlite" > "$TEMP/cookies.txt" <<'PY'
import sqlite3, sys

DOMINIOS = ("youtube.com", "google.com", "instagram.com", "tiktok.com",
            "twitter.com", "x.com", "vimeo.com", "facebook.com")

conn = sqlite3.connect(sys.argv[1])
print("# Netscape HTTP Cookie File")
for host, name, value, path, expiry, secure, http_only in conn.execute(
    "SELECT host, name, value, path, expiry, isSecure, isHttpOnly FROM moz_cookies"
):
    if not any(dominio in host for dominio in DOMINIOS):
        continue
    prefixo = "#HttpOnly_" if http_only else ""
    inclui_sub = "TRUE" if host.startswith(".") else "FALSE"
    print("\t".join([
        prefixo + host, inclui_sub, path or "/",
        "TRUE" if secure else "FALSE", str(int(expiry or 0)), name, value,
    ]))
PY

linhas="$(grep -vc '^#' "$TEMP/cookies.txt" || true)"
if [ "${linhas:-0}" -eq 0 ]; then
  echo "nenhum cookie encontrado em $PERFIL — o Firefox está logado nas fontes?" >&2
  exit 1
fi

curl --fail-with-body -sS -X POST "$DLP_URL/api/cookies" \
  -H "X-Upload-Token: $DLP_UPLOAD_TOKEN" \
  -F "arquivo=@$TEMP/cookies.txt"
echo
