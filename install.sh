#!/bin/sh
# keepctx installer. Downloads a single Python file; no dependencies.
# The command is `keepctx`.
set -e

REPO="${CTX_REPO:-sentityco/keepctx}"
PREFIX="${CTX_PREFIX:-$HOME/.local/bin}"

# Fetch main's exact commit, not `main`: GitHub caches raw files by URL for a few
# minutes, so right after a release `main` can still serve the previous version.
REF="${CTX_REF:-}"
if [ -z "$REF" ]; then
  REF=$(curl -fsSL -H "Accept: application/vnd.github.sha" \
    "https://api.github.com/repos/$REPO/commits/main" 2>/dev/null) || REF=""
  case "$REF" in
    *[!0-9a-f]* | "") REF="main" ;;   # API unreachable or rate-limited
  esac
fi
URL="https://raw.githubusercontent.com/$REPO/$REF/src/keepctx.py"

command -v python3 >/dev/null 2>&1 || {
  echo "keepctx needs python3 (3.9 or newer)." >&2
  exit 1
}

mkdir -p "$PREFIX"
echo "Downloading keepctx..."
# Download beside the target, then move it into place. Writing straight to
# $PREFIX/keepctx would follow a symlink there (a dev checkout, say) and
# overwrite whatever it points at; a move replaces the link itself.
TMP="$PREFIX/.keepctx.$$"
trap 'rm -f "$TMP"' EXIT
curl -fsSL "$URL" -o "$TMP"
chmod +x "$TMP"
if [ -L "$PREFIX/keepctx" ]; then
  echo "note: $PREFIX/keepctx was a link to $(readlink "$PREFIX/keepctx") — replacing the link"
  echo "      with the downloaded copy. The file it pointed at is untouched."
fi
mv -f "$TMP" "$PREFIX/keepctx"

# Earlier versions also installed a `ctx` alias. Remove it — but only if it's
# our own link; anything else called ctx is left alone.
if [ -L "$PREFIX/ctx" ] && [ "$(readlink "$PREFIX/ctx")" = "$PREFIX/keepctx" ]; then
  rm -f "$PREFIX/ctx"
fi

echo
echo "Installed: $PREFIX/keepctx"

case ":$PATH:" in
  *":$PREFIX:"*) ;;
  *)
    echo
    echo "$PREFIX is not on your PATH. Add this to your shell profile:"
    echo "  export PATH=\"$PREFIX:\$PATH\""
    ;;
esac

echo
echo "Next: cd your-project && keepctx init"
