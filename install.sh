#!/bin/sh
# keepctx installer. Downloads a single Python file; no dependencies.
#
# The executable is `keepctx`. It also installs `ctx` as a short alias, which is
# what you'll actually type — unless another project's `ctx` is already on your
# PATH, in which case the alias is skipped and keepctx still works.
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

# `ctx` is the short name. Don't clobber someone else's.
if [ -e "$PREFIX/ctx" ] && [ ! -L "$PREFIX/ctx" ]; then
  echo "note: $PREFIX/ctx already exists and isn't ours — leaving it alone."
  SHORT=""
elif EXISTING="$(command -v ctx 2>/dev/null)" && \
     [ -n "$EXISTING" ] && [ "$EXISTING" != "$PREFIX/ctx" ]; then
  echo "note: another \`ctx\` is on your PATH at $EXISTING."
  echo "      installing as \`keepctx\` only, so nothing of yours breaks."
  SHORT=""
else
  ln -sf "$PREFIX/keepctx" "$PREFIX/ctx"
  SHORT="yes"
fi

echo
echo "Installed: $PREFIX/keepctx"
if [ -n "$SHORT" ]; then
  echo "  with the short alias \`ctx\` — use that day to day."
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
if [ -n "$SHORT" ]; then
  echo "Next: cd your-project && ctx init"
else
  echo "Next: cd your-project && keepctx init"
fi
