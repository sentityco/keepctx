#!/usr/bin/env bash
# Deploy the site and installer. Run after any change to web/ or install.sh —
# the site is a separate artifact from the repo, and forgetting this is how the
# published installer ends up pointing at a path that no longer exists.
set -euo pipefail

BUCKET="${KEEPCTX_BUCKET:-ctxhub-site-975050072453}"
DIST="${KEEPCTX_DIST:-E1FU0K7RDCME20}"
export AWS_PAGER=""

cd "$(dirname "$0")"

put() {  # put <local> <key> <content-type>
  aws s3 cp "$1" "s3://$BUCKET/$2" \
    --content-type "$3" --cache-control "public,max-age=300" >/dev/null
  echo "  $2"
}

echo "uploading:"
put web/index.html index.html  "text/html; charset=utf-8"
put web/style.css  style.css   "text/css; charset=utf-8"
put install.sh     install.sh  "text/x-shellscript; charset=utf-8"

echo "invalidating..."
aws cloudfront create-invalidation --distribution-id "$DIST" \
  --paths "/*" --query 'Invalidation.Id' --output text

echo
echo "checking the installer points at a file that exists..."
sleep 12
src=$(curl -fsSL "https://keepctx.com/install.sh" | sed -n 's|^URL=".*\$REF/\(.*\)"|\1|p')
code=$(curl -s -o /dev/null -w '%{http_code}' \
  "https://raw.githubusercontent.com/sentityco/keepctx/main/$src")
if [ "$code" = "200" ]; then
  echo "  ok: install.sh -> $src ($code)"
else
  echo "  FAIL: install.sh points at $src which returns $code" >&2
  exit 1
fi

