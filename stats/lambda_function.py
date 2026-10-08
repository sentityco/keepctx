"""Download stats for keepctx.com. Runs in Lambda on an hourly EventBridge schedule.

Reads CloudFront access logs, keeps a permanent count of installer downloads per
day in the log bucket, and writes stats.html to the site bucket. A download is a
non-browser GET of /install.sh — every install and every update runs it once.
Bucket names and the distribution id come from the environment, not this file.
"""
import datetime
import gzip
import html
import json
import os

import boto3

s3 = boto3.client("s3")
cf = boto3.client("cloudfront")

LOG_BUCKET = os.environ["LOG_BUCKET"]
SITE_BUCKET = os.environ["SITE_BUCKET"]
DIST = os.environ["DIST"]
LOG_PREFIX = "raw/"
HISTORY_KEY = "downloads.json"


def is_download(p):
    # CloudFront standard log fields: 0 date, 5 method, 7 uri, 8 status, 10 user agent, 11 query
    return (len(p) > 11 and p[5] == "GET" and p[7] == "/install.sh"
            and p[8] in ("200", "304") and "Mozilla" not in p[10]
            and "deploy-check" not in p[11])


def load_history():
    try:
        return json.loads(s3.get_object(Bucket=LOG_BUCKET, Key=HISTORY_KEY)["Body"].read())
    except s3.exceptions.NoSuchKey:
        return {"since": datetime.date.today().isoformat(), "days": {}, "seen": []}


def ingest(hist):
    seen, present = set(hist["seen"]), set()
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=LOG_BUCKET, Prefix=LOG_PREFIX):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            present.add(key)
            if not key.endswith(".gz") or key in seen:
                continue
            body = gzip.decompress(s3.get_object(Bucket=LOG_BUCKET, Key=key)["Body"].read())
            for line in body.decode("utf-8", "replace").splitlines():
                if not line.startswith("#"):
                    p = line.split("\t")
                    if is_download(p):
                        hist["days"][p[0]] = hist["days"].get(p[0], 0) + 1
            seen.add(key)
    # raw logs expire after 90 days; forget keys that are gone so this list stays small
    hist["seen"] = sorted(seen & present)
    return hist


# ---- page ------------------------------------------------------------------

W, H = 760, 260
PL, PR, PT, PB = 40, 8, 12, 28
PW, PH = W - PL - PR, H - PT - PB
ACC, GRID, MUTED = "#1f6feb", "#e2e5ea", "#5b6470"


def nice_top(peak):
    for step in (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 5000):
        if peak <= step * 5:
            return step, max(step, -(-peak // step) * step)
    step = 10 ** len(str(peak))
    return step, -(-peak // step) * step


def grid(top, step):
    y = lambda v: PT + PH - PH * v / top
    return "".join(
        f'<line x1="{PL}" x2="{W - PR}" y1="{y(g):.1f}" y2="{y(g):.1f}" stroke="{GRID}"/>'
        f'<text x="{PL - 8}" y="{y(g) + 4:.1f}" text-anchor="end">{g:,}</text>'
        for g in range(0, top + 1, step))


def started(x, since):
    return (f'<text x="{x:.1f}" y="{PT + PH / 2:.1f}" text-anchor="end">counting started '
            f'{datetime.date.fromisoformat(since).strftime("%b %-d")}</text>')


def fmt(d):
    return datetime.date.fromisoformat(d).strftime("%b %-d, %Y")


def label(n):
    return f"{n:,} download{'' if n == 1 else 's'}"


def bars(span, vals, since):
    step, top = nice_top(max(vals + [1]))
    slot = PW / len(span)
    out = [grid(top, step)]
    first = next((i for i, d in enumerate(span) if d >= since), 0)
    if first > 0:
        out.append(started(PL + first * slot - 6, since))
    for i, (d, v) in enumerate(zip(span, vals)):
        x = PL + i * slot
        tip = f"{fmt(d)}: {label(v)}" if d >= since else f"{fmt(d)}: before counting started"
        if v:
            h = PH * v / top
            r = min(4, h, (slot - 2) / 2)
            w = slot - 2
            yb = PT + PH
            out.append(f'<path fill="{ACC}" d="M{x + 1:.1f},{yb}V{yb - h + r:.1f}'
                       f'q0,-{r:.1f} {r:.1f},-{r:.1f}h{w - 2 * r:.1f}q{r:.1f},0 {r:.1f},{r:.1f}V{yb}Z"/>')
        out.append(f'<rect class="hit" x="{x:.1f}" y="{PT}" width="{slot:.1f}" height="{PH}">'
                   f'<title>{tip}</title></rect>')
        if i % 7 == 0:
            out.append(f'<text x="{x + slot / 2:.1f}" y="{H - 8}" text-anchor="middle">'
                       f'{datetime.date.fromisoformat(d).strftime("%b %-d")}</text>')
    return "".join(out)


def line(span, vals, since):
    step, top = nice_top(max(vals + [1]))
    n = len(span)
    x = lambda i: PL + PW * i / (n - 1)
    y = lambda v: PT + PH - PH * v / top
    out = [grid(top, step)]
    first = next((i for i, d in enumerate(span) if d >= since), n - 1)
    if first > 0:
        out.append(started(x(first) - 8, since))
    pts = " ".join(f"{x(i):.1f},{y(vals[i]):.1f}" for i in range(first, n))
    if first < n - 1:
        out.append(f'<polygon fill="{ACC}" fill-opacity=".10" points="{x(first):.1f},{y(0):.1f} {pts} '
                   f'{x(n - 1):.1f},{y(0):.1f}"/>')
        out.append(f'<polyline fill="none" stroke="{ACC}" stroke-width="2" stroke-linejoin="round" '
                   f'points="{pts}"/>')
    else:
        out.append(f'<circle cx="{x(n - 1):.1f}" cy="{y(vals[-1]):.1f}" r="4" fill="{ACC}"/>')
    slot = PW / (n - 1)
    for i in range(first, n):
        out.append(f'<rect class="hit" x="{x(i) - slot / 2:.1f}" y="{PT}" width="{slot:.1f}" '
                   f'height="{PH}"><title>{fmt(span[i])}: {label(vals[i])}</title></rect>')
    for i, d in enumerate(span):
        if d.endswith("-01"):
            out.append(f'<line x1="{x(i):.1f}" x2="{x(i):.1f}" y1="{PT + PH}" y2="{PT + PH + 4}" '
                       f'stroke="{MUTED}"/><text x="{x(i):.1f}" y="{H - 8}" text-anchor="middle">'
                       f'{datetime.date.fromisoformat(d).strftime("%b")}</text>')
    return "".join(out)


def svg(body, desc):
    return (f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="{html.escape(desc)}">'
            f'{body}</svg>')


def render(hist):
    days, since = hist["days"], hist["since"]
    today = datetime.datetime.now(datetime.timezone.utc).date()
    span = lambda n: [(today - datetime.timedelta(days=i)).isoformat() for i in range(n - 1, -1, -1)]
    s30, s365 = span(30), span(365)
    v30 = [days.get(d, 0) for d in s30]
    v365 = [days.get(d, 0) for d in s365]
    total = sum(days.values())
    built = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    rows = "".join(f"<tr><td>{fmt(d)}</td><td class=\"num\">{v:,}</td></tr>"
                   for d, v in reversed(list(zip(s30, v30))) if d >= since)
    months = {}
    for d, v in zip(s365, v365):
        if d >= since[:7]:
            months[d[:7]] = months.get(d[:7], 0) + v
    mrows = "".join(f"<tr><td>{datetime.date.fromisoformat(m + '-01').strftime('%B %Y')}</td>"
                    f"<td class=\"num\">{v:,}</td></tr>" for m, v in reversed(months.items()))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>Download stats — KeepCTX</title>
<meta name="description" content="KeepCTX installer downloads per day, for the last 30 days and the last year." />
<link rel="stylesheet" href="style.css" />
<style>
.tiles{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:0 0 30px}}
.tile{{border:1px solid var(--line);border-radius:10px;padding:14px 16px}}
.tile b{{display:block;font-size:28px;letter-spacing:-.5px;line-height:1.2;font-variant-numeric:tabular-nums}}
.tile span{{color:var(--dim);font-size:14px}}
.range{{display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden;margin:0 0 14px}}
.range label{{padding:6px 14px;font-size:14px;cursor:pointer;color:var(--dim)}}
.range label+label{{border-left:1px solid var(--line)}}
#r30,#r365{{position:absolute;opacity:0;pointer-events:none}}
#r30:checked~.range label[for=r30],#r365:checked~.range label[for=r365]{{background:var(--soft);color:var(--ink);font-weight:600}}
#r30:focus-visible~.range label[for=r30],#r365:focus-visible~.range label[for=r365]{{outline:2px solid var(--acc);outline-offset:-2px}}
#r30:checked~.charts .c365,#r365:checked~.charts .c30{{display:none}}
.charts svg{{display:block;overflow:visible}}
.charts text{{font-size:11px;fill:{MUTED};font-variant-numeric:tabular-nums}}
.charts .hit{{fill:transparent}}
.charts .hit:hover{{fill:{ACC};fill-opacity:.08}}
.chart-title{{font-weight:600;margin:0 0 6px}}
details{{margin-top:26px}}
summary{{cursor:pointer;color:var(--acc)}}
table{{border-collapse:collapse;margin-top:10px;min-width:260px}}
td{{padding:4px 18px 4px 0;border-bottom:1px solid var(--line);font-size:14px}}
td.num{{text-align:right;font-variant-numeric:tabular-nums}}
.note{{color:var(--dim);font-size:14px;max-width:640px}}
@media(max-width:620px){{.tiles{{grid-template-columns:1fr}}header nav a:nth-child(-n+2){{display:none}}}}
</style>
</head>
<body>

<header><div class="wrap">
  <a class="logo" href="/"><img src="logo.png" alt="KeepCTX" width="148" height="36" /></a>
  <nav>
    <a href="/#how">How it works</a>
    <a href="/#quickstart">Quickstart</a>
    <a href="stats.html">Stats</a>
    <a href="https://github.com/sentityco/keepctx">GitHub</a>
  </nav>
</div></header>

<section><div class="wrap">
  <h2>Downloads</h2>
  <p class="sub">Installer downloads per day. Every install and every update is one download.</p>

  <div class="tiles">
    <div class="tile"><b>{sum(v30):,}</b><span>last 30 days</span></div>
    <div class="tile"><b>{sum(v365):,}</b><span>last 12 months</span></div>
    <div class="tile"><b>{total:,}</b><span>all time, since {fmt(since)}</span></div>
  </div>

  <input type="radio" name="range" id="r30" checked />
  <input type="radio" name="range" id="r365" />
  <div class="range" role="group" aria-label="Time range">
    <label for="r30">30 days</label><label for="r365">1 year</label>
  </div>
  <div class="charts">
    <div class="c30"><p class="chart-title">Downloads per day, last 30 days</p>
      {svg(bars(s30, v30, since), "Bar chart of installer downloads per day for the last 30 days")}</div>
    <div class="c365"><p class="chart-title">Downloads per day, last 12 months</p>
      {svg(line(s365, v365, since), "Line chart of installer downloads per day for the last 12 months")}</div>
  </div>

  <details><summary>Show the numbers</summary>
    <table><tr><td><b>Day</b></td><td class="num"><b>Downloads</b></td></tr>{rows}</table>
    <table style="margin-top:22px"><tr><td><b>Month</b></td><td class="num"><b>Downloads</b></td></tr>{mrows}</table>
  </details>

  <p class="note" style="margin-top:30px">Counted from keepctx.com's access logs: requests for
  <code>install.sh</code> from command-line tools like curl. Viewing the script in a browser isn't
  counted. No tracking, no cookies, nothing sent home by keepctx itself. Updated hourly; last built
  {built}. Days are in UTC.</p>
</div></section>

<footer><div class="wrap">
  <a href="https://github.com/sentityco/keepctx">GitHub</a> ·
  Apache-2.0 · free and open source
</div></footer>

</body>
</html>
"""


def lambda_handler(event=None, context=None):
    hist = ingest(load_history())
    s3.put_object(Bucket=LOG_BUCKET, Key=HISTORY_KEY, Body=json.dumps(hist).encode(),
                  ContentType="application/json")
    s3.put_object(Bucket=SITE_BUCKET, Key="stats.html", Body=render(hist).encode(),
                  ContentType="text/html; charset=utf-8", CacheControl="public,max-age=300")
    cf.create_invalidation(DistributionId=DIST, InvalidationBatch={
        "Paths": {"Quantity": 1, "Items": ["/stats.html"]},
        "CallerReference": datetime.datetime.now(datetime.timezone.utc).isoformat()})
    return {"days": len(hist["days"]), "total": sum(hist["days"].values())}
