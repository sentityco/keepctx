#!/bin/sh
# ctx installer. Downloads a single Python file; no dependencies.
set -e

REPO="${CTX_REPO:-sentityco/ctx}"
REF="${CTX_REF:-main}"
PREFIX="${CTX_PREFIX:-$HOME/.local/bin}"
URL="https://raw.githubusercontent.com/$REPO/$REF/src/ctx.py"

command -v python3 >/dev/null 2>&1 || {
  echo "ctx needs python3 (3.9 or newer)." >&2
  exit 1
}

mkdir -p "$PREFIX"
echo "downloading ctx..."
curl -fsSL "$URL" -o "$PREFIX/ctx"
chmod +x "$PREFIX/ctx"

echo "ctx installed to $PREFIX/ctx"
case ":$PATH:" in
  *":$PREFIX:"*) ;;
  *)
    echo
    echo "$PREFIX is not on your PATH. Add this to your shell profile:"
    echo "  export PATH=\"$PREFIX:\$PATH\""
    ;;
esac
echo
echo "next:  cd your-project && ctx init"
