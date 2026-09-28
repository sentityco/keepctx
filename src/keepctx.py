#!/usr/bin/env python3
"""keepctx — context management for AI and people.

Installed as `keepctx`, with `ctx` as a short alias.

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
DEFAULT_REMOTE = os.environ.get("CTX_REMOTE", "https://keepctx.com")

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
    """Nearest directory containing .ctx/. None if there isn't one.

    Only the nearest: contexts are independent, and which one applies is
    decided by where the agent was started. Nothing stacks or inherits.
    """
    d = pathlib.Path(start or os.getcwd()).resolve()
    return next((c for c in [d, *d.parents] if (c / CTXDIR).is_dir()), None)


def contexts_in_scope(start=None):
    """-> [(root, name, kind)] for the nearest context and its clones.

      "own"       the context here. the one the agent writes to.
      "readonly"  the context here, but someone else maintains it.
      "clone"     another context brought in beside it. read-only.
    """
    root = find_root(start)
    if not root:
        return []
    cfg = load_config(root)
    name = cfg.get("name")
    out = []
    if name and (root / CTXDIR / name / FACTS).exists():
        out.append((root, name, "readonly" if cfg.get("readonly") else "own"))
    for d in sorted((root / CTXDIR).iterdir()):
        if d.is_dir() and d.name != name and (d / FACTS).exists():
            out.append((root, d.name, "clone"))
    return out


def load_config(root):
    path = root / CTXDIR / CONFIG
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def save_config(root, cfg):
    keep = {k: v for k, v in cfg.items() if not k.startswith("_")}
    (root / CTXDIR / CONFIG).write_text(json.dumps(keep, indent=2) + "\n")


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


def remove_facts(text, keys):
    """Drop whole blocks by key — for facts deleted in another copy."""
    facts, _ = parse_facts(text)
    for key in keys:
        if key in facts:
            text = text.replace(facts[key] + "\n", "", 1).replace(facts[key], "", 1)
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
        try:
            return json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            # something between us and the API answered instead (a proxy, a CDN
            # error page) — say so, rather than dying on a parse error
            raise SystemExit(f"ctx: {base} sent back something that isn't the keepctx API. "
                             "Check the server address, or try again in a minute.")
    except urllib.error.HTTPError as e:
        detail = e.read().decode()
        try:
            detail = json.loads(detail).get("error", detail)
        except json.JSONDecodeError:
            pass
        if e.code == 401 and tok and not path.startswith("/v1/auth/"):
            # sign-ins last 30 days. a person can just sign in again; an agent
            # can't type a password, so it gets told who can.
            if not (sys.stdin.isatty() and sys.stdout.isatty()):
                raise SystemExit("ctx: the keepctx sign-in here has expired. "
                                 "Run `ctx sync` in a terminal to sign in again.")
            print("Your keepctx sign-in has expired. Sign in again:")
            cfg["token"] = login(cfg)[0]["token"]
            cfg["_signed_in"] = True          # caller saves it
            return api(cfg, method, path, body)
        raise SystemExit(f"ctx: {detail}" if e.code in (401, 403, 404, 409)
                         else f"ctx: server said {e.code}: {detail}")
    except urllib.error.URLError as e:
        raise SystemExit(f"ctx: cannot reach {base} ({e.reason})")


# ----------------------------------------------------------------- commands

INSTRUCTIONS_TEXT = """# keepctx — instructions for the agent

Context for this project lives here. Read it, keep it current.

## Every session
{session}

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

## What a context covers

The rules above decide *when* to write. This decides *what*. The short version:
**anything that would belong in an `AGENTS.md` belongs here instead.** `AGENTS.md`
is written once by hand and goes stale; this file is where that same knowledge is
kept current. So never write facts into `AGENTS.md` itself — it holds the pointer
and whatever a human wrote there, nothing more.

For software or anything else (investing, a book, a business), a good context
ends up answering:

What it is
- **Purpose** — why this exists, what value it gives, and who it is for.
- **Parts** — what it is made of: components, stack, tools.
- **Relationships** — what depends on what.
- **Design** — the intended shape and principles; for writing, the voice and style.
- **Vocabulary** — internal names nobody outside would know.

How to work in it
- **Conventions** — naming, structure, the idioms this place uses.
- **Workflow** — how changes are made: branches, commits, review.
- **Build and run** — the exact commands.
- **Testing** — how to test, what counts as passing, what is not covered.
- **Operating** — deploy, release, monitor, maintain, done the way this place does it.
- **Environment** — where things live and run, required tools and versions,
  variable names (never values), and where to look: logs, dashboards, files.
- **Access** — how to get into things. Never the credentials themselves.

Constraints
- **Rules** — standards, compliance, budgets, never-do-X.
- **Boundaries** — what not to touch: generated, vendored, or owned elsewhere.

Hard-won knowledge
- **Decisions** — what was chosen, why, and what was ruled out.
- **Gotchas** — what looks wrong but is intentional, or looks right but breaks.
- **Failure modes** — how it usually breaks, and the first thing to check.
- **Sources of truth** — which doc or dashboard wins when two disagree.

People
- **Ownership** — who owns what, and who to ask.
- **Preferences** — how the people here like to work.

Leave out what the files already say (listings, signatures, anything one read
answers) — it only goes stale — and anything that matters to this task alone.

Keys stay `thing.property` (`api.runs-on`, `logs.location`). When a fact is not
about one thing, the topic is the thing: `purpose.users`, `vocab.orion`,
`gotcha.staging-db`, `decision.no-kafka`. This is a map, not a form: never fill
a gap by guessing. A missing topic is better than an invented one.

**Record relationships, not just properties.** `gateway.depends-on → example-platform`
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
- **logging.index** — `app_prod_v2`, not what the docs say  `[verified]`
- **gateway.depends-on** → example-platform, for session validation
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



def err(msg):
    """Errors go to stderr, so an agent piping stdout gets only real output."""
    print(msg, file=sys.stderr)


def reread(tty=None):
    """One line. The rules live in AGENTS.md -> instructions.md; duplicating them
    in command output only creates a second copy to keep in step."""
    tty = sys.stdout.isatty() if tty is None else tty
    if tty:
        return "Tell your AI to re-read AGENTS.md."
    # the agent already read AGENTS.md at session start, so say why to read it
    # again — otherwise the instruction looks like a no-op.
    return "AGENTS.md changed — re-read it."


LOCAL_STEPS = """
1. **Read `{facts_path}`** for what is known about this project.
2. **Write facts back as you learn them** (see below).

This context is local only, so there is nothing to sync. If it is ever put on a
remote with `ctx remote`, these instructions gain two sync steps.
"""

REMOTE_STEPS = """
1. **Before reading context, run `ctx sync`.** Starts you from what your
   teammates have learned.
2. **Read `{facts_path}`** for what is known about this project.
3. **Write facts back as you learn them** (see below).
4. **After writing facts, run `ctx sync`.** A session that ends without this
   takes its findings with it.
"""

READONLY_STEPS = """
1. **Before reading context, run `ctx sync`.** Brings in the latest version.
2. **Read `{facts_path}`** for what is known about this project.
3. **Don't edit it.** Its owner and org admins maintain this context; it is
   read-only for this account, and `ctx sync` replaces local edits with the
   latest version. When you learn something it should say, tell the user, so
   they can pass it on to whoever maintains it.

The rules below are how its maintainers keep it. They are here so you know what
the facts mean and what kind of thing is worth passing on.
"""


def write_instructions(root, name, has_remote, readonly=False):
    """ctx owns this file and the agent never writes it, so ctx keeps it current
    — including on a later run, so an old setup does not keep stale rules."""
    facts_path = f"{CTXDIR}/{name}/{FACTS}"
    template = READONLY_STEPS if readonly else REMOTE_STEPS if has_remote else LOCAL_STEPS
    steps = template.format(facts_path=facts_path).rstrip()
    text = INSTRUCTIONS_TEXT.format(facts_path=facts_path, session=steps)
    path = root / CTXDIR / INSTRUCTIONS
    if path.exists() and path.read_text() == text:
        return False
    path.write_text(text)
    return True


def refresh_instructions():
    """Every command brings instructions.md up to date, so upgrading keepctx is
    just reinstalling it. Safe to do unasked: the file is gitignored and ctx owns
    all of it. AGENTS.md is the opposite on both counts, so it is never touched."""
    root = find_root()
    if not root:
        return False
    cfg = load_config(root)
    if not cfg.get("name"):
        return False
    return write_instructions(root, cfg["name"], has_remote=bool(cfg.get("org")),
                              readonly=bool(cfg.get("readonly")))


POINTER = (
    f"{BEGIN}\n"
    f"AI context for this project lives in `{CTXDIR}/{INSTRUCTIONS}` — read it first.\n"
    f"No `{CTXDIR}/`? Carry on without it, and don't flag it: it is gitignored, so it may not\n"
    f"be cloned here yet, or it was removed on purpose. To set it up, install ctx\n"
    f"(https://keepctx.com), then `ctx clone <org>:<name>` — or `ctx init` for a new one.\n"
    f"{END}\n"
)


def write_pointer(root):
    """Written once, at the top, and never again. AGENTS.md is the developer's
    file and it is in git: rewriting it later is a diff nobody asked for, and a
    teammate on an older ctx would write the old wording straight back."""
    agents = root / AGENTS
    existing = agents.read_text() if agents.exists() else ""
    if BEGIN not in existing:
        agents.write_text(POINTER + ("\n" + existing if existing else ""))


def cmd_init(argv, refreshed=False):
    here = pathlib.Path.cwd().resolve()
    if CTXDIR in here.parts:
        err(f"error: {here} is inside keepctx's own {CTXDIR}/ directory.")
        err("       Run `ctx init` from the project directory instead.")
        return 1
    found = find_root()

    # Already initialised is not a failure. `ctx init` is what people will be
    # told to run, so it must orient the agent every time — not only the first.
    if found == here:
        cfg = load_config(found)
        if sys.stdout.isatty():   # a person ran init again; say nothing was reset
            print(f"Already initialized `{cfg.get('name', '?')}` here.")
            print()
        cmd_status()
        # nothing an agent reads changed, unless the rules just got updated
        if refreshed:
            print()
            tty = sys.stdout.isatty()
            print(("keepctx's rules for your agent were updated. " if tty else "") + reread())
        return 0

    # A context further up is no obstacle: contexts are independent, so this
    # one simply starts here.
    root = here
    name = slugify(argv[0]) if argv else slugify(root.name)

    ctxdir = root / CTXDIR
    (ctxdir / name).mkdir(parents=True, exist_ok=True)

    # the directory ignores its own contents, whether or not git exists yet
    (ctxdir / ".gitignore").write_text("*\n")

    facts_rel = f"{CTXDIR}/{name}/{FACTS}"
    write_instructions(root, name, has_remote=False)

    facts = ctxdir / name / FACTS
    if not facts.exists():
        facts.write_text(f"# {name}\n\n")
    (ctxdir / name / BASE).write_text("")

    save_config(root, {"name": name, "org": None, "remote": None,
                       "token": None, "version": 0})

    write_pointer(root)

    print(f"Initialized `{name}`")
    w = max(len(facts_rel), len(f"{CTXDIR}/{INSTRUCTIONS}"), len(AGENTS))
    print(f"  {facts_rel:<{w}}  your facts")
    print(f"  {CTXDIR}/{INSTRUCTIONS:<{w - len(CTXDIR) - 1}}  how the agent maintains them")
    print(f"  {AGENTS:<{w}}  pointer added at the top")
    print()
    print(reread())
    return 0


def app_url(cfg):
    """The console lives on the same server as the API, hosted or self-hosted."""
    return (cfg.get("remote") or DEFAULT_REMOTE).rstrip("/") + "/app.html"


def server_url(s):
    """`https://keepctx.example.com`, or just `keepctx.example.com` — HTTPS is
    assumed unless it's this machine, where a self-hosted server speaks HTTP."""
    s = s.strip().rstrip("/")
    if "://" not in s:
        host = s.split(":")[0]
        local = host in ("localhost", "127.0.0.1", "0.0.0.0") or host.endswith(".local")
        s = ("http://" if local else "https://") + s
    return s


def pick_server(cfg, arg):
    """The server for `remote` or `clone`: the one named on the command line,
    else the one this directory already uses, else CTX_REMOTE or keepctx.com.
    A directory talks to one server — its sign-in belongs to that server."""
    have = cfg.get("remote") if (cfg.get("org") or cfg.get("clones")) else None
    want = server_url(arg) if arg else None
    if want and have and want != have.rstrip("/"):
        err(f"error: this directory already syncs with {have}.")
        err(f"       One server per directory — clone {want} contexts somewhere else.")
        return None
    return want or have or DEFAULT_REMOTE


def login(cfg):
    """Accounts are made on the website; ctx only signs in to one."""
    email = input("email: ").strip()
    password = getpass.getpass("password: ")
    out = api(cfg, "POST", "/v1/auth/login", {"email": email, "password": password})
    return out, email


def choose_org(orgs, email, app):
    """Which org a new remote context goes in. Orgs are created and joined on the
    website, signed in — ctx only picks from the ones you're already in."""
    mine = [o["org"] for o in orgs]
    if not mine:
        err(f"error: {email} isn't in an org yet.")
        err(f"       Create one at {app}, or ask an org admin to add you.")
        return None
    print("Your orgs: " + ", ".join(mine))
    hint = f" [{mine[0]}]" if len(mine) == 1 else ""
    org = input(f"org{hint}: ").strip().lower() or (mine[0] if len(mine) == 1 else "")
    if org in mine:
        return org
    err(f"error: you're not in `{org or '?'}`.")
    err(f"       Ask one of its admins to add {email}, or create it at {app}.")
    return None


def cmd_remote(argv):
    root = find_root()
    if not root:
        err("error: no context here. Run `ctx init` first.")
        return 1
    cfg = load_config(root)
    if cfg.get("org"):
        print(f"Already on a remote as {cfg['org']}:{cfg['name']}")
        return 1

    name = cfg.get("name") or slugify(root.name)
    if name in GENERIC:
        err(f"error: `{name}` is too generic to claim.")
        err("       Pick a name: ctx remote --name <name>")
        return 1
    if "--name" in argv:
        i = argv.index("--name")
        name = slugify(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]

    remote = pick_server(cfg, argv[0] if argv else None)
    if not remote:
        return 1
    cfg["remote"] = remote
    print(f"Remote: {remote}")
    print(f"Sign in (no account? make one at {app_url(cfg)})")
    out, email = login(cfg)
    cfg["token"] = out["token"]
    org = choose_org(out.get("orgs") or [], email, app_url(cfg))
    if not org:
        return 1
    cfg["org"] = org
    cfg["name"] = name

    facts = (root / CTXDIR / name / FACTS).read_text()
    made = api(cfg, "POST", "/v1/contexts", {"name": name, "facts": facts, "org": org})
    cfg["version"] = made["version"]
    save_config(root, cfg)
    (root / CTXDIR / name / BASE).write_text(facts)
    write_instructions(root, name, has_remote=True)

    print(f"{cfg['org']}:{name} is live. Others can `ctx clone {cfg['org']}:{name}`")
    return 0


def cmd_sync(argv):
    root = find_root()
    if not root:
        err("error: no context here. Run `ctx init` first.")
        return 1
    cfg = load_config(root)
    if not cfg.get("org") and not cfg.get("clones"):
        print("No remote for this context — `ctx remote` to create one.")
        print("Everything local keeps working without it.")
        return 1

    if cfg.get("org"):
        (pull_context if cfg.get("readonly") else push_pull)(root, cfg)
    for name, org in sorted((cfg.get("clones") or {}).items()):
        pull_clone(root, cfg, org, name)

    save_config(root, cfg)
    return 0


def push_pull(root, cfg):
    """A context you maintain: send what changed here, take what changed in
    your other copies. Merged per key; the later write of one key wins."""
    name = cfg["name"]
    facts_path = root / CTXDIR / name / FACTS
    base_path = root / CTXDIR / name / BASE
    local = facts_path.read_text()
    base = base_path.read_text() if base_path.exists() else ""

    changes = diff_facts(base, local)
    out = api(cfg, "POST", f"/v1/contexts/{cfg['org']}/{name}/sync",
              {"changes": changes, "version": cfg.get("version", 0)})

    incoming = out.get("facts", {})
    merged = merge_facts(local, incoming) if incoming else local
    gone = []
    if "keys" in out:              # deleted in another copy: drop them here too
        server = set(out["keys"])
        gone = [k for k in parse_facts(merged)[1] if k not in server]
        merged = remove_facts(merged, gone)
    facts_path.write_text(merged)
    base_path.write_text(merged)
    cfg["version"] = out["version"]

    sent, got = len(changes), len(incoming) + len(gone)
    parts = [f"{sent} up"] * bool(sent) + [f"{got} down"] * bool(got)
    print(f"{name}  {', '.join(parts) or 'unchanged'}  (v{out['version']})")


def pull_context(root, cfg):
    """A context this account reads but doesn't maintain: take the latest."""
    name = cfg["name"]
    got = api(cfg, "GET", f"/v1/contexts/{cfg['org']}/{name}")
    (root / CTXDIR / name / FACTS).write_text(got["facts"])
    (root / CTXDIR / name / BASE).write_text(got["facts"])
    was, cfg["version"] = cfg.get("version", 0), got["version"]
    state = "unchanged" if was == got["version"] else f"updated from v{was}"
    print(f"{name}  {state}  (v{got['version']}, read-only)")


def pull_clone(root, cfg, org, name):
    got = api(cfg, "GET", f"/v1/contexts/{org}/{name}")
    d = root / CTXDIR / name
    d.mkdir(parents=True, exist_ok=True)
    before = (d / FACTS).read_text() if (d / FACTS).exists() else None
    (d / FACTS).write_text(got["facts"])
    state = "unchanged" if before == got["facts"] else "updated"
    print(f"{name}  {state}  (v{got['version']}, from {org}, read-only)")


def cmd_clone(argv):
    """Bring a remote context here. In a directory with no context of its own it
    becomes this directory's context — writable if you maintain it (its owner or
    an org admin), read-only otherwise. Beside an existing context it's a
    read-only reference. Either way, `ctx sync` keeps it current."""
    if not argv or ":" not in argv[0]:
        err("error: usage: ctx clone <org>:<name> [server]")
        return 1
    org, _, name = argv[0].partition(":")
    here = pathlib.Path.cwd().resolve()
    if CTXDIR in here.parts:
        err(f"error: {here} is inside keepctx's own {CTXDIR}/ directory.")
        return 1
    root = find_root() or here
    cfg = load_config(root)
    own = cfg.get("name")
    if own == name and cfg.get("org") == org:
        print(f"{org}:{name} is already this directory's context — `ctx sync` to update it.")
        return 0

    remote = pick_server(cfg, argv[1] if len(argv) > 1 else None)
    if not remote:
        return 1
    if remote != cfg.get("remote"):
        cfg["remote"], cfg["token"] = remote, None     # a sign-in is only good on its own server
    if not cfg.get("token"):   # contexts are members-only, so reading one needs a sign-in
        print(f"Sign in to read {org}:{name} on {remote} (no account? make one at {app_url(cfg)})")
        cfg["token"] = login(cfg)[0]["token"]
    got = api(cfg, "GET", f"/v1/contexts/{org}/{name}")

    ctxdir = root / CTXDIR
    (ctxdir / name).mkdir(parents=True, exist_ok=True)
    (ctxdir / ".gitignore").write_text("*\n")
    (ctxdir / name / FACTS).write_text(got["facts"])

    if own:
        cfg.setdefault("clones", {})[name] = org
        save_config(root, cfg)
        print(f"Cloned {org}:{name} beside `{own}` ({got.get('count', 0)} facts, read-only)")
        print("`ctx sync` keeps it current.")
    else:
        readonly = not got.get("can_write")
        (ctxdir / name / BASE).write_text(got["facts"])
        cfg.update({"name": name, "org": org, "version": got["version"], "readonly": readonly})
        save_config(root, cfg)
        write_instructions(root, name, has_remote=True, readonly=readonly)
        write_pointer(root)
        print(f"Cloned {org}:{name} ({got.get('count', 0)} facts)")
        if readonly:
            print(f"Read-only: {got.get('owner') or 'its owner'} and {org}'s admins maintain it.")
            print("`ctx sync` brings in their updates.")
        else:
            print("You maintain it: edits here sync with your other copies on `ctx sync`.")
    for dep in got.get("requires", []):
        print(f"  requires {dep} — `ctx clone {dep}`")
    print()
    print(reread())
    return 0


def cmd_status(with_usage=False):
    root = find_root()
    piped = not sys.stdout.isatty()   # a hook or an agent is reading, not a person

    if not root:
        if piped:
            return 0          # silent: a session-start hook runs everywhere
        return usage()

    if piped:
        return agent_index(root)

    cfg = load_config(root)
    name = cfg.get("name", "?")
    facts_path = root / CTXDIR / name / FACTS
    facts, _ = parse_facts(facts_path.read_text() if facts_path.exists() else "")

    print(f"keepctx {VERSION}")
    print(f"  root      {root}")
    print(f"  context   {name}")
    print(f"  facts     {len(facts)}")
    if cfg.get("org"):
        ro = ", read-only" if cfg.get("readonly") else ""
        print(f"  remote    {cfg['org']}:{name} @ v{cfg.get('version', 0)}{ro}")
    else:
        print("  remote    none — `ctx remote` to share this")

    clones = cfg.get("clones") or {}
    if clones:
        print(f"  cloned    {', '.join(f'{o}:{n}' for n, o in sorted(clones.items()))}")
    if with_usage:            # plain `ctx`: a person asking what this is and what it does
        print()
        usage()
    return 0


def agent_index(root):
    """One line per context. Keys live in the files; listing them here is
    preloading by another name, and it grows without bound."""
    scope = contexts_in_scope()
    if not scope:
        return 0
    bits = []
    for r, n, kind in scope:
        _, order = read_facts(r, n)
        tag = "" if kind == "own" else ", read-only"
        bits.append(f"{n} ({len(order)} facts{tag})")
    print("Contexts: " + ", ".join(bits))
    return 0


def read_facts(root, name):
    p = root / CTXDIR / name / FACTS
    return parse_facts(p.read_text() if p.exists() else "")


def usage():
    print("keepctx — context management for AI and people")
    print()
    print("  ctx                    Show status")
    print("  ctx init [name]        Set up here — local, no account, no network")
    print("  ctx remote [server]    Put this on a remote — shares it and backs it up")
    print("  ctx clone <org>:<name> [server]")
    print("                         Bring a context here from the remote")
    print("  ctx sync               Send your changes, bring in the latest")
    print()
    print("Everything works locally without an account. The server is keepctx.com")
    print("unless you name your own: ctx remote https://keepctx.example.com")
    return 0


def main():
    argv = sys.argv[1:]
    cmd = argv[0] if argv else ""
    if cmd in ("-h", "--help", "help"):
        return usage()
    if cmd in ("-v", "--version"):
        print(f"keepctx {VERSION}")
        return 0
    refreshed = refresh_instructions()
    if cmd == "init":
        return cmd_init(argv[1:], refreshed)
    if cmd == "remote":
        return cmd_remote(argv[1:])
    if cmd == "sync":
        return cmd_sync(argv[1:])
    if cmd == "clone":
        return cmd_clone(argv[1:])
    if not argv:
        return cmd_status(with_usage=True)
    err(f"error: unknown command `{cmd}`")
    return usage()


if __name__ == "__main__":
    sys.exit(main())
