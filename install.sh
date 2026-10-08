#!/bin/sh
# keepctx installer. Downloads a single Python file; no dependencies.
# The command is `keepctx`.
set -e

REPO="${KEEPCTX_REPO:-sentityco/keepctx}"
PREFIX="${KEEPCTX_PREFIX:-$HOME/.local/bin}"

# Fetch main's exact commit, not `main`: GitHub caches raw files by URL for a few
# minutes, so right after a release `main` can still serve the previous version.
REF="${KEEPCTX_REF:-}"
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
# What's installed now, if anything — so we can say "installing" or "updating from".
OLD=""
if [ -x "$PREFIX/keepctx" ]; then
  OLD=$("$PREFIX/keepctx" --version 2>/dev/null | awk '{print $2}') || OLD=""
  [ -n "$OLD" ] || OLD="an unknown version"
fi
echo "Downloading keepctx..."
# Download beside the target, then move it into place. Writing straight to
# $PREFIX/keepctx would follow a symlink there (a dev checkout, say) and
# overwrite whatever it points at; a move replaces the link itself.
TMP="$PREFIX/.keepctx.$$"
trap 'rm -f "$TMP"' EXIT
curl -fsSL "$URL" -o "$TMP"
chmod +x "$TMP"
NEW=$(python3 "$TMP" --version 2>/dev/null | awk '{print $2}')
[ -n "$NEW" ] || { echo "error: the download isn't a working keepctx." >&2; exit 1; }
if [ -L "$PREFIX/keepctx" ]; then
  echo "note: $PREFIX/keepctx was a link to $(readlink "$PREFIX/keepctx") — replacing the link"
  echo "      with the downloaded copy. The file it pointed at is untouched."
fi
mv -f "$TMP" "$PREFIX/keepctx"

echo
if [ -z "$OLD" ]; then
  echo "Installed keepctx $NEW: $PREFIX/keepctx"
elif [ "$OLD" = "$NEW" ]; then
  echo "keepctx $NEW is already the latest version: $PREFIX/keepctx"
else
  echo "Updated keepctx from $OLD to $NEW: $PREFIX/keepctx"
fi

case ":$PATH:" in
  *":$PREFIX:"*) ;;
  *)
    echo
    echo "$PREFIX is not on your PATH. Add this to your shell profile:"
    echo "  export PATH=\"$PREFIX:\$PATH\""
    ;;
esac

echo
if [ -z "$OLD" ] || [ "$OLD" = "$NEW" ]; then
  echo "Next: cd your-project && keepctx init"
else
  echo "To finish updating, re-run keepctx init in each project that uses KeepCTX:"
  echo "  cd your-project && keepctx init"
  echo "It brings the rules in KEEPCTX.md up to $NEW and never touches your facts."
fi
