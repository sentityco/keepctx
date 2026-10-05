#!/usr/bin/env bash
# Deploy the site and installer. Run after any change to web/ or install.sh —
# the site is a separate artifact from the repo, and forgetting this is how the
# published installer ends up pointing at a path that no longer exists.
set -euo pipefail

cd "$(dirname "$0")"

# Bucket and distribution live in deploy.env (gitignored), or in the environment.
[ -f deploy.env ] && . ./deploy.env
BUCKET="${KEEPCTX_BUCKET:?set KEEPCTX_BUCKET (S3 bucket) in deploy.env or the environment}"
DIST="${KEEPCTX_DIST:?set KEEPCTX_DIST (CloudFront distribution id) in deploy.env or the environment}"
export AWS_PAGER=""

put() {  # put <local> <key> <content-type>
  aws s3 cp "$1" "s3://$BUCKET/$2" \
    --content-type "$3" --cache-control "public,max-age=300" >/dev/null
  echo "  $2"
}

echo "uploading:"
put web/index.html index.html  "text/html; charset=utf-8"
put web/style.css  style.css   "text/css; charset=utf-8"
put web/logo.png   logo.png    "image/png"
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

