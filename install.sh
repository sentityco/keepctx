#!/bin/sh
# keepctx installer. Downloads a single Python file; no dependencies.
#
# Installs two names for the same program: `ctx` (what you'll type) and
# `keepctx` (an escape hatch — several unrelated projects also ship a `ctx`,
# so if one is already on your PATH, use keepctx and nothing is blocked).
set -e

REPO="${CTX_REPO:-sentityco/keepctx}"
REF="${CTX_REF:-main}"
PREFIX="${CTX_PREFIX:-$HOME/.local/bin}"
URL="https://raw.githubusercontent.com/$REPO/$REF/src/ctx.py"

command -v python3 >/dev/null 2>&1 || {
  echo "keepctx needs python3 (3.9 or newer)." >&2
  exit 1
}

mkdir -p "$PREFIX"
echo "downloading keepctx..."
curl -fsSL "$URL" -o "$PREFIX/keepctx"
chmod +x "$PREFIX/keepctx"

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
if [ -n "$SHORT" ]; then
  echo "installed: $PREFIX/ctx (and keepctx)"
else
  echo "installed: $PREFIX/keepctx"
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
  echo "next:  cd your-project && ctx init"
else
  echo "next:  cd your-project && keepctx init"
fi
