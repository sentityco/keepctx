#!/usr/bin/env python3
"""ctx — a context manager for AI and people.

Cards are plain markdown with frontmatter. The index is a plain file. Everything
works with no server; a hosted backend is an option, never a requirement.
"""
import argparse, datetime, json, os, pathlib, re, sys, textwrap

PUBLISHED = "ctx"      # committed: cards this repo owns
WORKING   = ".ctx"     # gitignored: cache, proposals, session notes
AGENTS    = "AGENTS.md"
BEGIN, END = "<!-- ctx:begin -->", "<!-- ctx:end -->"

STATES = ("verified", "confirmed", "proposed", "disputed", "stale")


# ---------- card parsing ----------

def parse(path):
    text = path.read_text()
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        return None
    meta, body = {}, m.group(2).strip()
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        meta[k.strip()] = v.strip().strip('"').strip("'")
    meta["_path"], meta["_body"] = path, body
    meta.setdefault("id", path.stem)
    meta.setdefault("state", "proposed")
    meta.setdefault("scope", "team")
    return meta


def load_all(root):
    cards = {}
    for base in (root / PUBLISHED, root / WORKING / "cache", root / WORKING / "proposed"):
        if not base.exists():
            continue
        for p in sorted(base.rglob("*.md")):
            c = parse(p)
            if c:
                cards[c["id"]] = c
    for c in cards.values():
        rb = c.get("review_by")
        if rb and rb < datetime.date.today().isoformat() and c["state"] == "verified":
            c["state"] = "stale"
    return cards


def root_dir():
    d = pathlib.Path.cwd()
    for p in (d, *d.parents):
        if (p / PUBLISHED).is_dir() or (p / WORKING).is_dir():
            return p
    return d


# ---------- commands ----------

def cmd_init(args):
    root = pathlib.Path.cwd()
    (root / PUBLISHED).mkdir(exist_ok=True)
    for sub in ("cache", "proposed", "sessions"):
        (root / WORKING / sub).mkdir(parents=True, exist_ok=True)

    gi = root / ".gitignore"
    lines = gi.read_text().splitlines() if gi.exists() else []
    if WORKING + "/" not in lines:
        lines.append(WORKING + "/")
        gi.write_text("\n".join(lines) + "\n")

    seed = root / PUBLISHED / "how-ctx-works.md"
    if not seed.exists():
        seed.write_text(f"""---
id: how-ctx-works
title: How context works in this repo
scope: team
owner: "{os.environ.get('USER', 'unknown')}"
state: verified
updated: {datetime.date.today()}
summary: What ctx is, when to read a card, and when to write one back.
tags: [meta, ctx]
---

Context lives in `{PUBLISHED}/` as small markdown cards, one topic each. `{WORKING}/` is a
working directory and is not committed.

Read a card with `ctx get <id>`. The index in {AGENTS} lists what exists — that index is
the only thing loaded every session, so keep summaries to one line.

Write a card back when, and only when, one of these happens:

- Someone corrects you about how something actually works.
- You establish something that took real digging.
- A decision gets made and the reasoning would otherwise be lost.

Not for anything task-specific, anything you inferred rather than verified, or anything
an existing card already covers — update that one instead.
""")

    write_index(root)
    print(f"initialised ctx in {root}")
    print(f"  {PUBLISHED}/       cards this repo owns (commit these)")
    print(f"  {WORKING}/      working dir (gitignored)")
    print(f"  {AGENTS}      index + write-back instructions")
    print(f"\nnext: ctx new <id>   ·   ctx status")


def index_lines(cards):
    out = []
    for c in sorted(cards.values(), key=lambda c: (c.get("scope", ""), c["id"])):
        mark = {"verified": "", "confirmed": " ~confirmed", "proposed": " ~unverified",
                "disputed": " ~disputed", "stale": " ~stale"}.get(c["state"], "")
        out.append(f"- `{c['id']}` — {c.get('summary','(no summary)')} "
                   f"({c.get('scope','team')}, {c.get('updated','?')}{mark})")
    return out


def write_index(root):
    cards = load_all(root)
    block = "\n".join([
        BEGIN,
        "## Context available to you",
        "",
        "Fetch with `ctx get <id>` — do not guess at these topics. Cards marked",
        "`~unverified` were written by an agent and not yet reviewed; `~stale` means the",
        "owner has not confirmed it recently. Weight them accordingly.",
        "",
        *index_lines(cards),
        "",
        "Write context back with `ctx propose <id>` when someone corrects you, when you",
        "establish something that took real digging, or when a decision is made whose",
        "reasoning would otherwise be lost. Not for task-specific detail, not for things",
        "you inferred rather than verified, and not when an existing card covers it.",
        END,
    ])
    p = root / AGENTS
    text = p.read_text() if p.exists() else "# Agent instructions\n\n"
    if BEGIN in text and END in text:
        text = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END), block, text, flags=re.S)
    else:
        text = text.rstrip() + "\n\n" + block + "\n"
    p.write_text(text)
    return len(cards)


def cmd_index(args):
    root = root_dir()
    n = write_index(root) if args.write else None
    cards = load_all(root)
    if args.write:
        print(f"wrote {n} cards into {AGENTS}")
    else:
        print("\n".join(index_lines(cards)) or "no cards yet — try: ctx new <id>")


def cmd_new(args):
    root = root_dir()
    path = root / PUBLISHED / f"{args.id}.md"
    if path.exists():
        sys.exit(f"{path} already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today()
    path.write_text(f"""---
id: {args.id}
title: {args.title or args.id.replace('-', ' ').capitalize()}
scope: {args.scope}
owner: "{os.environ.get('USER','unknown')}"
state: verified
updated: {today}
review_by: {today.replace(year=today.year + 1) if today.month != 2 or today.day != 29 else today}
summary: {args.summary or 'ONE LINE — this is what every session pays for.'}
tags: []
---

Body. If this needs three thousand words it is two cards.
""")
    write_index(root)
    print(f"created {path.relative_to(root)}")


def cmd_get(args):
    cards = load_all(root_dir())
    for cid in args.ids:
        c = cards.get(cid)
        if not c:
            print(f"# {cid}\n\nno such card. `ctx index` lists what exists.\n")
            continue
        print(f"# {c.get('title', cid)}")
        print(f"<!-- {c['state']} · {c.get('scope')} · owner {c.get('owner')} · "
              f"updated {c.get('updated')} -->\n")
        print(c["_body"] + "\n")


def cmd_search(args):
    q = args.query.lower()
    hits = [c for c in load_all(root_dir()).values()
            if q in c["id"].lower() or q in c.get("summary", "").lower()
            or q in c.get("tags", "").lower() or q in c["_body"].lower()]
    if not hits:
        print("no matches")
        return
    for c in sorted(hits, key=lambda c: c["id"]):
        print(f"  {c['id']:28} {c.get('summary','')[:70]}")


def cmd_propose(args):
    root = root_dir()
    path = root / WORKING / "proposed" / f"{args.id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = args.body or sys.stdin.read() if not sys.stdin.isatty() else (args.body or "")
    path.write_text(f"""---
id: {args.id}
title: {args.title or args.id.replace('-', ' ').capitalize()}
scope: {args.scope}
owner: "unassigned"
state: proposed
updated: {datetime.date.today()}
summary: {args.summary or 'proposed by an agent — needs a one-line summary'}
source: agent
tags: []
---

{body.strip() or '(no body provided)'}
""")
    write_index(root)
    print(f"proposed {args.id} — review with: ctx review")


def cmd_review(args):
    cards = load_all(root_dir())
    queue = [c for c in cards.values() if c["state"] in ("proposed", "disputed", "stale")]
    if not queue:
        print("nothing awaiting review")
        return
    for c in sorted(queue, key=lambda c: c["state"]):
        print(f"  [{c['state']:9}] {c['id']:26} {c.get('summary','')[:60]}")
    print(f"\n{len(queue)} awaiting review · promote with: ctx verify <id>")


def cmd_verify(args):
    root = root_dir()
    cards = load_all(root)
    c = cards.get(args.id)
    if not c:
        sys.exit(f"no card {args.id}")
    src = c["_path"]
    text = src.read_text()
    text = re.sub(r"^state:.*$", "state: verified", text, count=1, flags=re.M)
    text = re.sub(r'^owner:.*$', f'owner: "{os.environ.get("USER","unknown")}"', text, count=1, flags=re.M)
    text = re.sub(r"^updated:.*$", f"updated: {datetime.date.today()}", text, count=1, flags=re.M)
    dest = root / PUBLISHED / f"{args.id}.md"
    dest.write_text(text)
    if src != dest:
        src.unlink()
    write_index(root)
    print(f"verified {args.id} → {dest.relative_to(root)}")


def cmd_status(args):
    root = root_dir()
    cards = load_all(root)
    if not cards:
        print("no cards yet. run: ctx init")
        return
    counts = {s: sum(1 for c in cards.values() if c["state"] == s) for s in STATES}
    idx_tokens = sum(len(l.split()) for l in index_lines(cards)) * 1.4
    print(f"{root}")
    print(f"  {len(cards)} cards · " + " · ".join(f"{n} {s}" for s, n in counts.items() if n))
    print(f"  index costs roughly {int(idx_tokens)} tokens per session")
    q = counts["proposed"] + counts["disputed"] + counts["stale"]
    if q:
        print(f"  {q} awaiting review — ctx review")


def main():
    ap = argparse.ArgumentParser(prog="ctx", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("init", help="scaffold ctx in this repo").set_defaults(fn=cmd_init)
    sub.add_parser("status", help="what exists and what it costs").set_defaults(fn=cmd_status)
    sub.add_parser("review", help="cards awaiting a human").set_defaults(fn=cmd_review)

    p = sub.add_parser("index", help="print the index");  p.add_argument("--write", action="store_true"); p.set_defaults(fn=cmd_index)
    p = sub.add_parser("get", help="print cards");        p.add_argument("ids", nargs="+"); p.set_defaults(fn=cmd_get)
    p = sub.add_parser("search", help="find cards");      p.add_argument("query"); p.set_defaults(fn=cmd_search)
    p = sub.add_parser("verify", help="owner signs off"); p.add_argument("id"); p.set_defaults(fn=cmd_verify)

    for name, fn in (("new", cmd_new), ("propose", cmd_propose)):
        p = sub.add_parser(name, help=f"{name} a card")
        p.add_argument("id"); p.add_argument("--title"); p.add_argument("--summary")
        p.add_argument("--scope", default="team")
        if name == "propose":
            p.add_argument("--body")
        p.set_defaults(fn=fn)

    a = ap.parse_args()
    (a.fn if a.cmd else cmd_status)(a)


if __name__ == "__main__":
    main()
