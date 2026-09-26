#!/usr/bin/env python3
"""ctx — a context manager for AI and people.

Contexts are plain markdown with frontmatter. The index is a plain file. Everything
works with no server; a hosted backend is an option, never a requirement.
"""
import argparse, datetime, json, os, pathlib, re, sys, textwrap

PUBLISHED = "ctx"      # committed: contexts this repo owns
WORKING   = ".ctx"     # gitignored: cache, proposals, session notes
AGENTS    = "AGENTS.md"
BEGIN, END = "<!-- ctx:begin -->", "<!-- ctx:end -->"
SUBS = "subscriptions.json"      # which contexts this workspace cares about
INDEX_BUDGET = 60                # contexts listed in full before the index collapses

STATES = ("verified", "confirmed", "proposed", "disputed", "stale")


# ---------- parsing ----------

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
    meta.setdefault("org", "")
    for key in ("requires", "related", "tags"):
        raw = meta.get(key, "")
        meta[key] = [x.strip() for x in raw.strip("[]").split(",") if x.strip()]
    meta["_path"], meta["_body"] = path, body
    meta.setdefault("id", path.stem)
    meta.setdefault("state", "proposed")
    return meta


def load_all(root):
    ctxs = {}
    for base in (root / PUBLISHED, root / WORKING / "cache",
                 root / WORKING / "proposed", root / WORKING / "inbox"):
        if not base.exists():
            continue
        for p in sorted(base.rglob("*.md")):
            c = parse(p)
            if c:
                ctxs[c["id"]] = c
    for c in ctxs.values():
        rb = c.get("review_by")
        if rb and rb < datetime.date.today().isoformat() and c["state"] == "verified":
            c["state"] = "stale"
    return ctxs


def tokens(c):
    """Rough token cost of a context's body."""
    return int(len(c["_body"].split()) * 1.4)


def qualify(ref, from_org):
    """`idcmt` inside comcast -> comcast:idcmt. `acme:sso` stays as it is."""
    return ref if ":" in ref else (f"{from_org}:{ref}" if from_org else ref)


def lookup(ctxs, ref, from_org=""):
    """Find a context by bare id or org/id."""
    if ref in ctxs:
        return ctxs[ref]
    if ":" in ref:
        org, _, bare = ref.partition(":")
        c = ctxs.get(bare)
        return c if c and c.get("org", "") == org else None
    for c in ctxs.values():
        if c["id"] == ref and (not from_org or c.get("org", "") == from_org):
            return c
    return None


def resolve(ctxs, ids, depth=2):
    """Requires-closure, breadth-first, cycle-safe. Returns (ordered ids, missing, cut)."""
    seen, order, missing, cut = set(), [], [], []
    frontier = [(i, 0) for i in ids]
    while frontier:
        cid, d = frontier.pop(0)
        if cid in seen:
            continue
        seen.add(cid)
        c = lookup(ctxs, cid)
        if not c:
            missing.append(cid)
            continue
        cid = c["id"]
        if cid in order:
            continue
        order.append(cid)
        if d >= depth:
            cut.extend(r for r in c["requires"] if r not in seen)
            continue
        frontier.extend((r, d + 1) for r in c["requires"] if r not in seen)
    return order, missing, sorted(set(cut))


def subs_path(root):
    return root / WORKING / SUBS


def load_subs(root):
    p = subs_path(root)
    d = json.loads(p.read_text()) if p.exists() else {}
    return {"org": d.get("org", ""), "subscribed": d.get("subscribed", []),
            "sources": d.get("sources", [])}


def save_subs(root, subs):
    subs_path(root).parent.mkdir(parents=True, exist_ok=True)
    subs_path(root).write_text(json.dumps(subs, indent=2) + "\n")


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
org: ""
owner: "{os.environ.get('USER', 'unknown')}"
state: verified
updated: {datetime.date.today()}
summary: What ctx is, when to read a context, and when to write one back.
tags: [meta, ctx]
---

Contexts live in `{PUBLISHED}/` as small markdown files, one topic each. `{WORKING}/` is a
working directory and is not committed.

Read one with `ctx get <id>`. The index in {AGENTS} lists what exists — that index is
the only thing loaded every session, so keep summaries to one line.

Write one back when, and only when, one of these happens:

- Someone corrects you about how something actually works.
- You establish something that took real digging.
- A decision gets made and the reasoning would otherwise be lost.

Not for anything task-specific, anything you inferred rather than verified, or anything
an existing context already covers — update that one instead.
""")

    write_index(root)
    print(f"initialised ctx in {root}")
    print(f"  {PUBLISHED}/       contexts this repo owns (commit these)")
    print(f"  {WORKING}/      working dir (gitignored)")
    print(f"  {AGENTS}      index + write-back instructions")
    print(f"\nnext: ctx new <id>   ·   ctx status")


def index_lines(ctxs):
    orgs = {c.get("org", "") for c in ctxs.values()}
    show_org = len([o for o in orgs if o]) > 1
    out = []
    for c in sorted(ctxs.values(), key=lambda c: c["id"]):
        mark = {"verified": "", "confirmed": " ~confirmed", "proposed": " ~unverified",
                "disputed": " ~disputed", "stale": " ~stale"}.get(c["state"], "")
        where = f"{c['org']}:{c['id']}" if (show_org and c.get("org")) else c["id"]
        out.append(f"- `{where}` — {c.get('summary','(no summary)')} "
                   f"({c.get('updated','?')}{mark})")
    return out


def working_set(root, ctxs):
    """What you subscribed to, plus everything it requires. Nothing else."""
    subs = load_subs(root)["subscribed"]
    if not subs:
        return list(ctxs.values())
    ids, _, _ = resolve(ctxs, subs, depth=99)
    return [ctxs[i] for i in ids if i in ctxs]


def write_index(root):
    ctxs = load_all(root)
    shown = working_set(root, ctxs)
    hidden = len(ctxs) - len(shown)
    block = "\n".join([
        BEGIN,
        "## Contexts available to you",
        "",
        "Fetch with `ctx get <id>` — do not guess at these topics. Contexts marked",
        "`~unverified` were written by an agent and not yet reviewed; `~stale` means the",
        "owner has not confirmed it recently. Weight them accordingly.",
        "",
        *index_lines({c["id"]: c for c in shown}),
        *([f"", f"{hidden} more contexts exist outside your subscriptions — find them with "
                f"`ctx search <query>`, load them with `ctx get <id>`."] if hidden else []),
        "",
        "Write context back with `ctx propose <id>` when someone corrects you, when you",
        "establish something that took real digging, or when a decision is made whose",
        "reasoning would otherwise be lost. Not for task-specific detail, not for things",
        "you inferred rather than verified, and not when an existing context covers it.",
        END,
    ])
    p = root / AGENTS
    text = p.read_text() if p.exists() else "# Agent instructions\n\n"
    if BEGIN in text and END in text:
        text = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END), block, text, flags=re.S)
    else:
        text = text.rstrip() + "\n\n" + block + "\n"
    p.write_text(text)
    return len(ctxs)


def cmd_use(args):
    root = root_dir()
    if not (root / WORKING).exists():
        (root / WORKING / "cache").mkdir(parents=True, exist_ok=True)
    subs = load_subs(root)
    for target in args.targets:
        src = pathlib.Path(target).expanduser()
        if src.is_dir():
            dest = root / WORKING / "cache" / src.name
            dest.mkdir(parents=True, exist_ok=True)
            n = 0
            for f in src.rglob("*.md"):
                (dest / f.name).write_text(f.read_text()); n += 1
            if target not in subs["sources"]:
                subs["sources"].append(str(src))
            print(f"synced {n} contexts from {src}")
        else:
            if ":" in target:
                org, scope = target.split(":", 1)
            else:
                org, scope = subs["org"], target
            if org and not subs["org"]:
                subs["org"] = org
                print(f"organization set to `{org}`")
            if scope not in subs["subscribed"]:
                subs["subscribed"].append(scope)
            print(f"subscribed to `{scope}`" + (f" in `{subs['org']}`" if subs["org"] else ""))
    save_subs(root, subs)

    ctxs = load_all(root)
    for sc in subs["subscribed"]:
        if not lookup(ctxs, sc, subs["org"]):
            print(f"  note: no context named `{sc}` yet")
    write_index(root)
    cmd_status(args)


def cmd_index(args):
    root = root_dir()
    n = write_index(root) if args.write else None
    ctxs = load_all(root)
    if args.write:
        print(f"wrote {n} contexts into {AGENTS}")
    else:
        print("\n".join(index_lines(ctxs)) or "no contexts yet — try: ctx new <id>")


def cmd_new(args):
    root = root_dir()
    org = load_subs(root)["org"]
    path = root / PUBLISHED / f"{args.id}.md"
    if path.exists():
        sys.exit(f"{path} already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today()
    path.write_text(f"""---
id: {args.id}
title: {args.title or args.id.replace('-', ' ').capitalize()}
org: {org}
owner: "{os.environ.get('USER','unknown')}"
state: verified
updated: {today}
review_by: {today.replace(year=today.year + 1) if today.month != 2 or today.day != 29 else today}
summary: {args.summary or 'ONE LINE — this is what every session pays for.'}
requires: [{args.requires or ''}]
related: [{args.related or ''}]
tags: []
---

Body. If this needs three thousand words it is two contexts.
""")
    write_index(root)
    print(f"created {path.relative_to(root)}")


def cmd_get(args):
    ctxs = load_all(root_dir())
    if args.no_deps:
        order, missing, cut = [i for i in args.ids if i in ctxs], \
                              [i for i in args.ids if i not in ctxs], []
    else:
        order, missing, cut = resolve(ctxs, args.ids, args.depth)

    for cid in order:
        c = ctxs[cid]
        why = "" if cid in args.ids else "  (required by a context you asked for)"
        print(f"# {c.get('title', cid)}{why}")
        where = f"{c['org']}:{c['id']}" if c.get("org") else c["id"]
        print(f"<!-- {where} · {c['state']} · owner {c.get('owner')} · "
              f"updated {c.get('updated')} -->\n")
        print(c["_body"] + "\n")
        if c["related"]:
            print(f"Related, not loaded: {', '.join('`'+r+'`' for r in c['related'])}\n")

    for cid in missing:
        print(f"# {cid}\n\nno such context. `ctx index` lists what exists.\n")
    if cut:
        print(f"<!-- depth {args.depth} reached; not loaded: {', '.join(cut)} -->")
    if len(order) > 1:
        total = sum(tokens(ctxs[c]) for c in order)
        print(f"<!-- {len(order)} contexts, roughly {total} tokens -->")


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
org: {load_subs(root)["org"]}
owner: "unassigned"
author: "{os.environ.get('USER','unknown')}"
state: proposed
updated: {datetime.date.today()}
summary: {args.summary or 'proposed by an agent — needs a one-line summary'}
source: agent
requires: [{args.requires or ''}]
related: [{args.related or ''}]
tags: []
---

{body.strip() or '(no body provided)'}
""")
    write_index(root)
    print(f"proposed {args.id} — review with: ctx review")


def cmd_push(args):
    """Send local proposals to the sources they belong to."""
    root = root_dir()
    subs = load_subs(root)
    pending = sorted((root / WORKING / "proposed").glob("*.md"))
    if not pending:
        print("nothing to push")
        return
    if not subs["sources"]:
        print("no upstream source configured — ctx use <path-or-url> first")
        print(f"{len(pending)} proposals are waiting in {WORKING}/proposed/")
        return

    dest = pathlib.Path(subs["sources"][0]).expanduser()
    inbox = dest.parent / ".ctx" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    for f in pending:
        (inbox / f.name).write_text(f.read_text())
        if not args.keep:
            f.unlink()
    print(f"pushed {len(pending)} proposal(s) to {inbox}")
    print("the owner sees them with: ctx review")
    write_index(root)


def cmd_review(args):
    ctxs = load_all(root_dir())
    queue = [c for c in ctxs.values() if c["state"] in ("proposed", "disputed", "stale")]
    if not queue:
        print("nothing awaiting review")
        return
    for c in sorted(queue, key=lambda c: c["state"]):
        who = f"  from {c['author']}" if c.get("author") else ""
        print(f"  [{c['state']:9}] {c['id']:26} {c.get('summary','')[:52]}{who}")
    print(f"\n{len(queue)} awaiting review · promote with: ctx verify <id>")


def cmd_verify(args):
    root = root_dir()
    ctxs = load_all(root)
    c = ctxs.get(args.id)
    if not c:
        sys.exit(f"no context {args.id}")
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


def cmd_deps(args):
    ctxs = load_all(root_dir())
    if not lookup(ctxs, args.id):
        sys.exit(f"no context {args.id}")

    def walk(cid, prefix="", seen=()):
        c = lookup(ctxs, cid)
        if not c:
            print(f"{prefix}{cid}  (missing)")
            return
        label = f"{c['org']}:{c['id']}" if c.get("org") else c["id"]
        cid = c["id"]
        loop = " ↺ cycle" if cid in seen else ""
        print(f"{prefix}{label}  — {c.get('summary','')[:50]} [{tokens(c)}t]{loop}")
        if loop:
            return
        kids = c["requires"]
        for i, k in enumerate(kids):
            last = i == len(kids) - 1
            walk(k, prefix[:-2].replace("└", " ").replace("├", "│") +
                 ("  " if prefix else "") + ("└ " if last else "├ "), seen + (cid,))

    walk(args.id)
    order, missing, _ = resolve(ctxs, [args.id], depth=99)
    total = sum(tokens(ctxs[c]) for c in order if c in ctxs)
    print(f"\n{len(order)} contexts in the closure, roughly {total} tokens")
    if missing:
        print(f"missing: {', '.join(missing)}")


def cmd_list(args):
    ctxs = load_all(root_dir())
    rows = [c for c in ctxs.values()
            if (not args.state or c["state"] == args.state)
            and (not args.tag or args.tag in c["tags"])]
    if not rows:
        print("no contexts match")
        return
    for c in sorted(rows, key=lambda c: c["id"]):
        dep = f"  →{len(c['requires'])}" if c["requires"] else ""
        print(f"  {c['state']:9} {c['id']:26} {c.get('summary','')[:52]}{dep}")
    print(f"\n{len(rows)} of {len(ctxs)} contexts")


def md_to_html(md):
    """Enough markdown for a context body. No dependencies."""
    out, in_list = [], False
    for line in md.splitlines():
        line = (line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
        line = re.sub(r"`(.+?)`", r"<code>\1</code>", line)
        line = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', line)
        if line.startswith("- "):
            if not in_list: out.append("<ul>"); in_list = True
            out.append(f"<li>{line[2:]}</li>"); continue
        if in_list: out.append("</ul>"); in_list = False
        if line.startswith("### "):   out.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("## "):  out.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("# "):   out.append(f"<h1>{line[2:]}</h1>")
        elif line.strip():            out.append(f"<p>{line}</p>")
    if in_list: out.append("</ul>")
    return "\n".join(out)


CSS = """*{box-sizing:border-box}body{margin:0;padding:24px 18px 64px;background:#fcfcfa;
color:#111;font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,sans-serif}
main,header{max-width:760px;margin:0 auto}a{color:#14396b}
header{border-bottom:2px solid #111;padding-bottom:10px;margin-bottom:26px}
h1{font-size:22px;margin:0 0 6px}h2{font-size:17px;margin:28px 0 8px;
padding-bottom:4px;border-bottom:1px solid #ddd}h3{font-size:15px;margin:18px 0 4px}
.meta{font-size:13px;color:#555;margin:0 0 22px}
.s{font-size:11px;letter-spacing:.06em;text-transform:uppercase;padding:2px 7px;
border-radius:3px;border:1px solid #ccc;color:#555}
.s.verified{border-color:#1a7f4b;color:#1a7f4b}.s.proposed{border-color:#a86a00;color:#a86a00}
.s.stale,.s.disputed{border-color:#a12; color:#a12}
table{border-collapse:collapse;width:100%;font-size:15px}
td,th{text-align:left;padding:7px 10px 7px 0;border-bottom:1px solid #e2e2e0;vertical-align:top}
code{background:#f0f0ec;padding:1px 4px;border-radius:3px;font-size:.92em}
footer{border-top:1px solid #ddd;margin-top:40px;padding-top:12px;font-size:13px;color:#666}"""


def page(title, body, up=""):
    return (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{title}</title><style>{CSS}</style></head><body>'
            f'<header><h1><a href="{up}index.html" style="color:inherit;text-decoration:none">ctx</a></h1>'
            f'<p class="meta">context management — AI first, readable by humans</p></header>'
            f'<main>{body}</main><footer>generated by <code>ctx render</code></footer></body></html>')


def cmd_render(args):
    root = root_dir()
    ctxs = load_all(root)
    out = pathlib.Path(args.out or (root / WORKING / "html"))
    out.mkdir(parents=True, exist_ok=True)

    rows = []
    for c in sorted(ctxs.values(), key=lambda c: c["id"]):
        name = f"{c['org']}:{c['id']}" if c.get("org") else c["id"]
        rows.append(f'<tr><td><a href="{c["id"]}.html">{name}</a></td>'
                    f'<td>{c.get("summary","")}</td>'
                    f'<td><span class="s {c["state"]}">{c["state"]}</span></td></tr>')
        req = "".join(f'<li><a href="{r.split(":")[-1]}.html">{r}</a></li>' for r in c["requires"])
        rel = "".join(f'<li><a href="{r.split(":")[-1]}.html">{r}</a></li>' for r in c["related"])
        body = (f'<h1>{c.get("title", c["id"])}</h1>'
                f'<p class="meta"><span class="s {c["state"]}">{c["state"]}</span> · '
                f'<code>{name}</code> · owner {c.get("owner","?")} · updated {c.get("updated","?")}</p>'
                + md_to_html(c["_body"])
                + (f"<h2>Requires</h2><ul>{req}</ul>" if req else "")
                + (f"<h2>Related</h2><ul>{rel}</ul>" if rel else ""))
        (out / f"{c['id']}.html").write_text(page(c.get("title", c["id"]), body))

    idx = (f"<h1>{len(ctxs)} contexts</h1>"
           f"<p class=\"meta\">The same files an agent reads with <code>ctx get</code>.</p>"
           f"<table><tr><th>Context</th><th>Summary</th><th>State</th></tr>"
           + "".join(rows) + "</table>")
    (out / "index.html").write_text(page("ctx", idx))
    print(f"rendered {len(ctxs)} contexts to {out}")
    print(f"  open {out}/index.html")


def cmd_status(args):
    root = root_dir()
    ctxs = load_all(root)
    if not ctxs:
        print("no contexts yet. run: ctx init")
        return
    counts = {s: sum(1 for c in ctxs.values() if c["state"] == s) for s in STATES}
    idx_tokens = sum(len(l.split()) for l in index_lines(ctxs)) * 1.4
    subs = load_subs(root)
    print(f"{root}")
    if subs["org"]:
        print(f"  organization: {subs['org']}")
    if subs["subscribed"]:
        print(f"  subscribed: {', '.join(subs['subscribed'])}")
    print(f"  {len(ctxs)} contexts · " + " · ".join(f"{n} {s}" for s, n in counts.items() if n))
    print(f"  index costs roughly {int(idx_tokens)} tokens per session")
    q = counts["proposed"] + counts["disputed"] + counts["stale"]
    if q:
        print(f"  {q} awaiting review — ctx review")


def main():
    ap = argparse.ArgumentParser(prog="ctx", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("init", help="scaffold ctx in this repo").set_defaults(fn=cmd_init)
    sub.add_parser("status", help="what exists and what it costs").set_defaults(fn=cmd_status)
    sub.add_parser("review", help="contexts awaiting a human").set_defaults(fn=cmd_review)

    p = sub.add_parser("render", help="static HTML of every context, for humans")
    p.add_argument("--out"); p.set_defaults(fn=cmd_render)

    p = sub.add_parser("push", help="send your proposals upstream")
    p.add_argument("--keep", action="store_true", help="do not clear them locally")
    p.set_defaults(fn=cmd_push)

    p = sub.add_parser("use", help="subscribe to a context, or sync a source directory")
    p.add_argument("targets", nargs="+", metavar="CONTEXT|PATH")
    p.set_defaults(fn=cmd_use)

    p = sub.add_parser("index", help="print the index");  p.add_argument("--write", action="store_true"); p.set_defaults(fn=cmd_index)
    p = sub.add_parser("get", help="print a context and what it requires")
    p.add_argument("ids", nargs="+")
    p.add_argument("--depth", type=int, default=1, help="how far to follow requires (default 1)")
    p.add_argument("--no-deps", action="store_true", help="just the contexts named")
    p.set_defaults(fn=cmd_get)

    p = sub.add_parser("deps", help="show what a context requires, and the total cost")
    p.add_argument("id"); p.set_defaults(fn=cmd_deps)

    p = sub.add_parser("list", help="list contexts, filtered")
    p.add_argument("--state"); p.add_argument("--tag")
    p.set_defaults(fn=cmd_list)
    p = sub.add_parser("search", help="find contexts");      p.add_argument("query"); p.set_defaults(fn=cmd_search)
    p = sub.add_parser("verify", help="owner signs off"); p.add_argument("id"); p.set_defaults(fn=cmd_verify)

    for name, fn in (("new", cmd_new), ("propose", cmd_propose)):
        p = sub.add_parser(name, help=f"{name} a context")
        p.add_argument("id"); p.add_argument("--title"); p.add_argument("--summary")
        p.add_argument("--requires", help="ids this context cannot be understood without")
        p.add_argument("--related", help="comma-separated ids worth knowing about, not auto-loaded")
        if name == "propose":
            p.add_argument("--body")
        p.set_defaults(fn=fn)

    a = ap.parse_args()
    (a.fn if a.cmd else cmd_status)(a)


if __name__ == "__main__":
    main()
