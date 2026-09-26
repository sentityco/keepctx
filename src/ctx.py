#!/usr/bin/env python3
"""keepctx — context management for AI and people.

Local by default. A context is a list of facts in markdown; the agent reads and
edits facts.md directly, and ctx is called only for network work.
"""
import json
import os
import getpass
import pathlib
import re
import sys
import urllib.error
import urllib.request

VERSION = "0.1.0"
DEFAULT_REMOTE = os.environ.get("CTX_REMOTE", "https://lrtkepaox4.execute-api.us-east-1.amazonaws.com")

CTXDIR = ".ctx"
CONFIG = "config.json"
FACTS = "facts.md"
BASE = ".base"           # last-synced copy, for diffing
INSTRUCTIONS = "instructions.md"
AGENTS = "AGENTS.md"

BEGIN = "<!-- ctx -->"
END = "<!-- /ctx -->"

# a fact line: "- **key** — value"  or  "- **key** → value"
FACT_RE = re.compile(r"^\s*-\s+\*\*(?P<key>[^*]+)\*\*\s*(?P<rel>[—→-])\s*(?P<value>.*)$")


# ---------------------------------------------------------------- filesystem

def find_root(start=None):
    """Walk up for a directory containing .ctx/. None if there isn't one."""
    d = pathlib.Path(start or os.getcwd()).resolve()
    for candidate in [d, *d.parents]:
        if (candidate / CTXDIR).is_dir():
            return candidate
    return None


def load_config(root):
    path = root / CTXDIR / CONFIG
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def save_config(root, cfg):
    (root / CTXDIR / CONFIG).write_text(json.dumps(cfg, indent=2) + "\n")


def slugify(name):
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "context"


GENERIC = {
    "src", "app", "api", "web", "lib", "code", "work", "dev", "test", "tmp",
    "project", "repo", "main", "new", "my-project", "untitled", "workspace",
}


# -------------------------------------------------------------------- facts

def parse_facts(text):
    """-> ({key: block}, [key, ...]) where a block is the fact line plus any
    more-indented continuation lines beneath it (sub-lists, multi-step values)."""
    facts, order, key, block = {}, [], None, []

    def flush():
        if key is not None:
            if key not in facts:
                order.append(key)
            facts[key] = "\n".join(block).rstrip()

    for line in text.splitlines():
        m = FACT_RE.match(line)
        if m:
            flush()
            key, block = m.group("key").strip(), [line.rstrip()]
        elif key is not None and line.strip() and line[:1].isspace():
            block.append(line.rstrip())      # continuation of the current fact
        else:
            flush()
            key, block = None, []
    flush()
    return facts, order


def diff_facts(base_text, now_text):
    """What changed locally since the last sync, keyed."""
    base, _ = parse_facts(base_text)
    now, order = parse_facts(now_text)
    changes = []
    for key in order:
        if key not in base:
            changes.append({"key": key, "block": now[key], "op": "add"})
        elif base[key] != now[key]:
            changes.append({"key": key, "block": now[key], "op": "update"})
    for key in base:
        if key not in now:
            changes.append({"key": key, "block": "", "op": "delete"})
    return changes


def merge_facts(local_text, incoming):
    """Apply server blocks onto the local file. Later wins, per key."""
    local, _ = parse_facts(local_text)
    text = local_text
    for key, block in incoming.items():
        if key in local:
            text = text.replace(local[key], block, 1)   # whole block, not one line
        else:
            text = text.rstrip() + "\n" + block + "\n"
    return text.rstrip() + "\n"


# --------------------------------------------------------------------- http

def api(cfg, method, path, body=None, token=None):
    base = cfg.get("remote") or DEFAULT_REMOTE
    url = base.rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    tok = token or cfg.get("token")
    if tok:
        req.add_header("Authorization", "Bearer " + tok)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode()
        try:
            detail = json.loads(detail).get("error", detail)
        except json.JSONDecodeError:
            pass
        raise SystemExit(f"ctx: server said {e.code}: {detail}")
    except urllib.error.URLError as e:
        raise SystemExit(f"ctx: cannot reach {base} ({e.reason})")


# ----------------------------------------------------------------- commands

INSTRUCTIONS_TEXT = """# ctx — instructions for the agent

Context for this project lives here. Read it, keep it current.

## Every session

1. **Before reading context, run `ctx sync`.** Starts you from what your
   teammates have learned.
2. **Read `{facts_path}`** for what is known about this project.
3. **Write facts back as you learn them** (see below).
4. **After writing facts, run `ctx sync`.** A session that ends without this
   takes its findings with it.

## What to write down

Only three things are worth recording:

- **A human corrected you.** The strongest signal there is — the context was
  wrong or missing and the right answer is in hand.
- **Something cost real effort to establish.** Expensive once means expensive
  again.
- **A decision and its reasoning.** Decisions decay fastest, because the *why*
  never gets written down.

Never record task-specific detail, and never record something you inferred
rather than verified.

**Record relationships, not just properties.** `spacaptive.depends-on → idcmt`
is worth more than three facts about its configuration, because it is what
nobody writes down and everybody needs.

**Write as you learn, not at the end.** Sessions get truncated. A fact learned
at minute five and written at minute ninety may never get written at all.

**Reuse an existing key rather than adding a second line.** If `deploy.command`
is already there and now wrong, edit that line.

## Format

One fact per line. The bolded lead is the key.

```markdown
- **deploy.command** — `make ship` from the repo root
- **splunk.index** — `ace_prod_v2`, not what the docs say  `[verified]`
- **spacaptive.depends-on** → idcmt, for session validation
- **deploy.process** — three steps:
    - build with `make`
    - push, then verify the health endpoint
```

- `—` marks an attribute, `→` marks a relationship.
- `` `[verified]` `` means a human settled it. Do not remove it; if the fact is
  now wrong, correct the value and leave the marker for a human to re-confirm.
- Dotted keys group automatically. Prefer `thing.property` over `thingProperty`.

Do not record who wrote a fact or when. That is kept for you in version history.
"""


def cmd_init(argv):
    if find_root():
        root = find_root()
        print(f"ctx: already set up in {root}")
        return 1

    root = pathlib.Path.cwd()
    name = slugify(argv[0]) if argv else slugify(root.name)

    ctxdir = root / CTXDIR
    (ctxdir / name).mkdir(parents=True, exist_ok=True)

    # the directory ignores its own contents, whether or not git exists yet
    (ctxdir / ".gitignore").write_text("*\n")

    facts_rel = f"{CTXDIR}/{name}/{FACTS}"
    (ctxdir / INSTRUCTIONS).write_text(
        INSTRUCTIONS_TEXT.format(facts_path=facts_rel))

    facts = ctxdir / name / FACTS
    if not facts.exists():
        facts.write_text(f"# {name}\n\n")
    (ctxdir / name / BASE).write_text("")

    save_config(root, {"name": name, "org": None, "remote": None,
                       "token": None, "version": 0})

    pointer = (
        f"{BEGIN}\n"
        f"AI context for this project lives in `{CTXDIR}/{INSTRUCTIONS}` — read it first.\n"
        f"Missing? It is gitignored by design. Install ctx (https://keepctx.com), then\n"
        f"`ctx clone <org>:<name>` — or `ctx init` if this project has no context yet.\n"
        f"{END}\n"
    )
    agents = root / AGENTS
    if agents.exists():
        existing = agents.read_text()
        if BEGIN not in existing:
            agents.write_text(pointer + "\n" + existing)
    else:
        agents.write_text(pointer)

    print(f"ctx: initialised `{name}`")
    w = max(len(facts_rel), len(f"{CTXDIR}/{INSTRUCTIONS}"), len(AGENTS))
    print(f"  {facts_rel:<{w}}  your facts")
    print(f"  {CTXDIR}/{INSTRUCTIONS:<{w - len(CTXDIR) - 1}}  how the agent maintains them")
    print(f"  {AGENTS:<{w}}  pointer added at the top")
    print()
    print("all local. `ctx remote` when you want to share it.")
    return 0


def cmd_remote(argv):
    root = find_root()
    if not root:
        print("ctx: nothing here yet — `ctx init` first")
        return 1
    cfg = load_config(root)
    if cfg.get("org"):
        print(f"ctx: already on a remote as {cfg['org']}:{cfg['name']}")
        return 1

    name = cfg.get("name") or slugify(root.name)
    if name in GENERIC:
        print(f"ctx: `{name}` is too generic to claim on a remote.")
        print("     pick a name: ctx remote --name <name>")
        return 1
    if "--name" in argv:
        name = slugify(argv[argv.index("--name") + 1])

    remote = os.environ.get("CTX_REMOTE", DEFAULT_REMOTE)
    print(f"remote: {remote}")
    email = input("email: ").strip()
    password = getpass.getpass("password: ")
    org = input("org (new or existing): ").strip().lower()

    cfg["remote"] = remote
    out = api(cfg, "POST", "/v1/auth/login",
              {"email": email, "password": password, "org": org})
    cfg["token"] = out["token"]
    cfg["org"] = out["org"]
    cfg["name"] = name

    facts = (root / CTXDIR / name / FACTS).read_text()
    made = api(cfg, "POST", "/v1/contexts", {"name": name, "facts": facts})
    cfg["version"] = made["version"]
    save_config(root, cfg)
    (root / CTXDIR / name / BASE).write_text(facts)

    print(f"ctx: {cfg['org']}:{name} is live. others can `ctx clone {cfg['org']}:{name}`")
    return 0


def cmd_sync(argv):
    root = find_root()
    if not root:
        print("ctx: nothing here yet — `ctx init` first")
        return 1
    cfg = load_config(root)
    if not cfg.get("org"):
        print("no remote for this context — `ctx remote` to create one")
        print("  (everything local keeps working without it)")
        return 1

    name = cfg["name"]
    facts_path = root / CTXDIR / name / FACTS
    base_path = root / CTXDIR / name / BASE
    local = facts_path.read_text()
    base = base_path.read_text() if base_path.exists() else ""

    changes = diff_facts(base, local)
    out = api(cfg, "POST", f"/v1/contexts/{cfg['org']}/{name}/sync",
              {"changes": changes, "version": cfg.get("version", 0)})

    incoming = out.get("facts", {})
    if incoming:
        merged = merge_facts(local, incoming)
        facts_path.write_text(merged)
        base_path.write_text(merged)
    else:
        base_path.write_text(local)

    cfg["version"] = out["version"]
    save_config(root, cfg)

    sent, got = len(changes), len(incoming)
    if sent or got:
        parts = []
        if sent:
            parts.append(f"{sent} up")
        if got:
            parts.append(f"{got} down")
        print(f"{name}  {', '.join(parts)}  (v{out['version']})")
    else:
        print(f"{name}  unchanged  (v{out['version']})")
    return 0


def cmd_clone(argv):
    if not argv or ":" not in argv[0]:
        print("ctx: usage — ctx clone <org>:<name>")
        return 1
    org, _, name = argv[0].partition(":")
    root = find_root() or pathlib.Path.cwd()
    if not (root / CTXDIR).exists():
        (root / CTXDIR).mkdir(parents=True)
        (root / CTXDIR / ".gitignore").write_text("*\n")

    cfg = load_config(root)
    cfg.setdefault("remote", os.environ.get("CTX_REMOTE", DEFAULT_REMOTE))
    got = api(cfg, "GET", f"/v1/contexts/{org}/{name}")

    d = root / CTXDIR / name
    d.mkdir(parents=True, exist_ok=True)
    (d / FACTS).write_text(got["facts"])
    (d / BASE).write_text(got["facts"])
    (d / ".readonly").write_text("cloned — edits here are not synced upstream\n")

    print(f"ctx: cloned {org}:{name} ({got.get('count', 0)} facts)")
    for dep in got.get("requires", []):
        print(f"  requires {dep} — `ctx clone {dep}`")
    return 0


def cmd_status():
    root = find_root()
    if not root:
        return usage()
    cfg = load_config(root)
    name = cfg.get("name", "?")
    facts_path = root / CTXDIR / name / FACTS
    facts, _ = parse_facts(facts_path.read_text() if facts_path.exists() else "")

    print(f"ctx {VERSION}")
    print(f"  root      {root}")
    print(f"  context   {name}")
    print(f"  facts     {len(facts)}")
    if cfg.get("org"):
        print(f"  remote    {cfg['org']}:{name} @ v{cfg.get('version', 0)}")
    else:
        print("  remote    none — `ctx remote` to share this")

    others = [p.name for p in (root / CTXDIR).iterdir()
              if p.is_dir() and p.name != name]
    if others:
        print(f"  cloned    {', '.join(others)}")
    return 0


def usage():
    print("ctx — context management for AI and people")
    print()
    print("  ctx                    status")
    print("  ctx init [name]        set up here. local, no account, no network.")
    print("  ctx remote             one-time. create this context on a remote.")
    print("  ctx clone <org>:<name> get a context you do not have.")
    print("  ctx sync               upload local changes, download remote ones.")
    print()
    print("everything works locally without an account.")
    return 0


def main():
    argv = sys.argv[1:]
    cmd = argv[0] if argv else ""
    if cmd in ("-h", "--help", "help"):
        return usage()
    if cmd in ("-v", "--version"):
        print(VERSION)
        return 0
    if cmd == "init":
        return cmd_init(argv[1:])
    if cmd == "remote":
        return cmd_remote(argv[1:])
    if cmd == "sync":
        return cmd_sync(argv[1:])
    if cmd == "clone":
        return cmd_clone(argv[1:])
    if cmd == "upgrade":
        print("ctx: install with brew or the install script; see https://keepctx.com")
        return 0
    if not argv:
        return cmd_status()
    print(f"ctx: unknown command `{cmd}`")
    return usage()


if __name__ == "__main__":
    sys.exit(main())
