#!/bin/sh
# keepctx server installer. Your own keepctx: the same API and the same site as
# keepctx.com, on one port, stored in one SQLite file. Python 3.9+, nothing else.
#
#   curl -fsSL https://keepctx.com/server.sh | sh
#
# Reinstalling replaces the code and never touches the data.
set -e

REPO="${CTX_REPO:-sentityco/keepctx}"
PREFIX="${CTX_PREFIX:-$HOME/.local/bin}"
HOME_DIR="${CTX_SERVER_HOME:-$HOME/.local/share/keepctx-server}"

# main's exact commit, not `main`: raw files are cached by URL for a few minutes
REF="${CTX_REF:-}"
if [ -z "$REF" ]; then
  REF=$(curl -fsSL -H "Accept: application/vnd.github.sha" \
    "https://api.github.com/repos/$REPO/commits/main" 2>/dev/null) || REF=""
  case "$REF" in
    *[!0-9a-f]* | "") REF="main" ;;
  esac
fi
BASE="https://raw.githubusercontent.com/$REPO/$REF"

command -v python3 >/dev/null 2>&1 || {
  echo "keepctx-server needs python3 (3.9 or newer)." >&2
  exit 1
}

# Download everything first, then swap it in, so a failed download leaves a
# working install alone.
TMP="$HOME_DIR/.new.$$"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/web" "$PREFIX"
echo "Downloading keepctx server..."
for f in server/serve.py server/handler.py; do
  curl -fsSL "$BASE/$f" -o "$TMP/$(basename "$f")"
done
for f in index.html app.html app.js style.css; do
  curl -fsSL "$BASE/web/$f" -o "$TMP/web/$f"
done

rm -rf "$HOME_DIR/web"
mv -f "$TMP/serve.py" "$TMP/handler.py" "$HOME_DIR/"
mv "$TMP/web" "$HOME_DIR/web"

cat > "$PREFIX/keepctx-server" <<LAUNCH
#!/bin/sh
exec python3 "$HOME_DIR/serve.py" "\$@"
LAUNCH
chmod +x "$PREFIX/keepctx-server"

echo
echo "Installed: $PREFIX/keepctx-server"
echo "  code  $HOME_DIR"
echo "  data  $HOME_DIR/data  (kept across reinstalls)"
case ":$PATH:" in
  *":$PREFIX:"*) ;;
  *)
    echo
    echo "$PREFIX is not on your PATH. Add this to your shell profile:"
    echo "  export PATH=\"$PREFIX:\$PATH\""
    ;;
esac
echo
echo "Next:"
echo "  keepctx-server                 # http://127.0.0.1:8080"
echo "  put HTTPS in front, e.g.  caddy reverse-proxy --from keepctx.example.com --to :8080"
echo "  ctx remote https://keepctx.example.com"
