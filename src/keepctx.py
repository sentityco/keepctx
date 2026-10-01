#!/usr/bin/env python3
"""keepctx — keep your AI context across sessions, across AIs, across your team.

Installed as `keepctx`, with `ctx` as a short alias.

Local by default. A context is a list of facts, one line each, grouped by
category in one markdown file. The agent reads it with `ctx get` and changes it
with `ctx remember` and `ctx forget`; `ctx pull` and `ctx push` keep it in step
with a server when there is one.
"""
import getpass
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.request

VERSION = "0.2.0"
DEFAULT_REMOTE = os.environ.get("CTX_REMOTE", "https://keepctx.com")

CTXDIR = ".ctx"
CONFIG = "config.json"
FACTS = "facts.md"
BASE = ".base"           # the server's facts as of the last pull or push: the merge base
REMOTE_DIR = "remote"    # what each pull downloaded, by version
KEEP_REMOTE = 5
INSTRUCTIONS = "instructions.md"
AGENTS = "AGENTS.md"

BEGIN = "<!-- ctx -->"
END = "<!-- /ctx -->"

# a fact line: "- **key** — value"  or  "- **key** → value"
FACT_RE = re.compile(r"^\s*-\s+\*\*(?P<key>[^*]+)\*\*\s*(?P<rel>[—→-])\s*(?P<value>.*)$")
HEADING_RE = re.compile(r"^##\s+(?P<title>.+?)\s*$")
KEY_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")

# slug, heading, what belongs there. The order is the order of the file.
CATEGORIES = [
    ("overview", "Overview",
     "What this is, why it exists, who it's for, and what success looks like."),
    ("requirements", "Requirements",
     "What it must and must not do, and what is in and out of scope."),
    ("architecture", "Architecture",
     "Services, components, dependencies and data flows: what connects to what."),
    ("environments", "Environments",
     "Hosts, deployment environments, service names, versions and access. Never secrets."),
    ("decisions", "Decisions",
     "What was chosen and why, and what was considered and rejected."),
    ("questions", "Questions",
     "What is still undecided. Replaced by a decision once settled."),
    ("conventions", "Conventions",
     "Patterns future developers and agents should follow, and what not to touch."),
    ("operations", "Operations",
     "Build, deploy, runbooks, troubleshooting and recurring operational details."),
    ("testing", "Testing",
     "How to test, what passing means, and what is not covered."),
    ("knowledge", "Knowledge",
     "Gotchas, domain facts and vocabulary nobody outside would know."),
    ("people", "People",
     "Who owns what, who to ask, and how they like to work."),
]
CATEGORY = {slug: (title, desc) for slug, title, desc in CATEGORIES}

# Files from before categories: facts sit under no heading, and a few key
# prefixes say where they belong. Everything else lands in knowledge.
LEGACY = {"purpose": "overview", "goal": "overview", "req": "requirements",
          "decision": "decisions", "rejected": "decisions", "question": "questions"}
LEGACY_STRIP = {"decision", "question", "req"}

# Shapes that are only ever credentials. The server refuses them too; checking
# here keeps them out of the local file as well.
SECRETS = [
    ("an AWS access key", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("a private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("a GitHub token", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})")),
    ("a Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("an API key", re.compile(r"\bsk-(ant-|proj-|live-)?[A-Za-z0-9_-]{20,}")),
    ("a Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}")),
    ("a Stripe key", re.compile(r"\b(sk|rk)_live_[0-9A-Za-z]{20,}")),
]


def say(msg):
    """Everything an operator should see starts with KeepCTX:, and the
    instructions tell the agent to pass these lines on."""
    print(f"KeepCTX: {msg}")


def err(msg):
    """Errors go to stderr, so an agent piping stdout gets only real output."""
    print(msg, file=sys.stderr)


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
#
# A context is {full key: (rel, value)}, where the full key is
# `category.key` — `environments.server-a.ip`. The file is that, rendered:
# a heading per category, one line per fact. Continuation lines (indented
# sub-lists) stay part of the value.

def parse(text):
    facts, cat, last = {}, None, None
    for line in (text or "").splitlines():
        h = HEADING_RE.match(line)
        if h:
            cat, last = slugify(h.group("title")), None
            continue
        m = FACT_RE.match(line)
        if m:
            key, rel = m.group("key").strip(), "→" if m.group("rel") == "→" else "—"
            if cat is None:                               # a file from before categories
                prefix = key.split(".")[0]
                c = LEGACY.get(prefix, "knowledge")
                if prefix in LEGACY_STRIP and "." in key:
                    key = key.split(".", 1)[1]
                full = f"{c}.{key}"
            else:
                full = f"{cat}.{key}"
            facts[full] = (rel, m.group("value").strip())
            last = full
        elif last and line.strip() and line[:1].isspace():
            rel, value = facts[last]
            facts[last] = (rel, value + "\n" + line.rstrip())
        else:
            last = None
    return facts


def split_key(full):
    cat, _, key = full.partition(".")
    return cat, key


def fact_line(full, fact):
    rel, value = fact
    return f"- **{split_key(full)[1]}** {rel} {value}"


def render(facts, template=True):
    """The whole file. With template, every category heading appears with its
    description even when empty, so a person opening it sees the shape."""
    by_cat = {}
    for full, fact in facts.items():
        by_cat.setdefault(split_key(full)[0], []).append(fact_line(full, fact))
    out = ["# Project Context", ""]
    order = [c for c, _, _ in CATEGORIES] + sorted(c for c in by_cat if c not in CATEGORY)
    for c in order:
        lines = by_cat.get(c, [])
        if not lines and not template:
            continue
        title, desc = CATEGORY.get(c, (c.replace("-", " ").title(), ""))
        out.append(f"## {title}")
        if desc and template:
            out.append(f"_{desc}_")
        out.append("")
        if lines:
            out += lines + [""]
    return "\n".join(out).rstrip() + "\n"


def body(facts):
    """The facts without the file's title and empty headings — what an agent reads."""
    return render(facts, template=False).partition("\n\n")[2].rstrip()


def read_file(path):
    return parse(path.read_text()) if path.exists() else {}


def find_secret(text):
    for what, rx in SECRETS:
        if rx.search(text or ""):
            return what
    return None


def merge3(base, local, remote):
    """Fact by fact, against the copy both sides started from. A fact changed
    on one side only is taken from that side; changed differently on both is
    a conflict, and the local value stays until the agent settles it.
    -> (merged, counts, conflicts)"""
    merged, conflicts = {}, []
    n = {"added": 0, "changed": 0, "removed": 0, "kept": 0}
    for k in list(local) + [k for k in remote if k not in local]:
        b, l, r = base.get(k), local.get(k), remote.get(k)
        if l == r:
            pick = l
        elif l == b:                               # only the remote changed it
            pick = r
            n["added" if b is None else "removed" if r is None else "changed"] += 1
        elif r == b:                               # only this copy changed it
            pick = l
            n["kept"] += 1
        else:
            pick = l
            conflicts.append(k)
        if pick is not None:
            merged[k] = pick
    return merged, n, conflicts


# --------------------------------------------------------------------- http

def api(cfg, method, path, body=None, token=None, allow=()):
    """JSON in, JSON out. A status in `allow` comes back as {"_status": code, ...}
    instead of ending the command."""
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
            raise SystemExit(f"ctx: {base} sent back something that isn't the KeepCTX API. "
                             "Check the server address, or try again in a minute.")
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            got = json.loads(raw)
        except json.JSONDecodeError:
            got = {"error": raw}
        if e.code in allow:
            return {"_status": e.code, **got}
        detail = got.get("error", raw)
        if e.code == 401 and tok and not path.startswith("/v1/auth/"):
            # sign-ins last 30 days. a person can just sign in again; an agent
            # can't type a password, so it gets told who can.
            if not (sys.stdin.isatty() and sys.stdout.isatty()):
                raise SystemExit("ctx: the KeepCTX sign-in here has expired. "
                                 "Run `ctx pull` in a terminal to sign in again.")
            print("Your KeepCTX sign-in has expired. Sign in again:")
            cfg["token"] = login(cfg)[0]["token"]
            cfg["_signed_in"] = True          # caller saves it
            return api(cfg, method, path, body, allow=allow)
        raise SystemExit(f"ctx: {detail}" if e.code in (400, 401, 403, 404, 409)
                         else f"ctx: server said {e.code}: {detail}")
    except urllib.error.URLError as e:
        raise SystemExit(f"ctx: cannot reach {base} ({e.reason})")


# -------------------------------------------------------------- instructions

INSTRUCTIONS_TEXT = """# KeepCTX — instructions for the agent

This project's context is kept in KeepCTX: what it is, why, how it is built and
run, what has been decided, and what is still open. It outlasts this session,
and every AI and every person on the project reads the same facts. Use it, and
keep it current as you work.

Work through the `ctx` command only. Never edit the files in `{ctxdir}/` yourself.

## Every session
{session}

## Tell the user

Every line `ctx` prints that starts with `KeepCTX:` is for the user too. Repeat
it in your reply, as it was printed, so they always see what is kept and synced:

    KeepCTX: remembered environments.server-a.ip — 10.0.4.12
    KeepCTX: pulled 45 facts from https://keepctx.com (v12)
    KeepCTX: pushed 48 facts to https://keepctx.com (v13)

## Remember

```sh
ctx remember <category> <key> "<value>"   # add a fact, or replace it
ctx forget <category> <key>                # remove one that is wrong or gone
```

Remember anything worth knowing next time — by you in another session, by
another AI, or by a teammate. Cast a wide net: not only how things run, but what
is being built and why. Remember it the moment you learn it; a session can end
at any time.

- **The user states a goal or a requirement.**
- **The user decides something** — once they commit ("let's do X", "go with Y"),
  with the reason. Musing is not deciding: "maybe Postgres?" is a question.
- **An option is turned down** — under decisions, with why, so it is not
  proposed again.
- **Something is still open** — under questions. Forget it once a decision
  settles it.
- **A human corrects you**, or **something took real effort to establish**.
- **How things are**: where they run, how to build, test, deploy and fix them,
  the conventions here, and who owns what.

Never remember:

- **Secrets** — passwords, tokens, keys, not even part of one. `ctx` refuses them.
- **Anything the user puts off the record**, and personal matters or opinions
  about people.
- **The conversation itself**, or detail that matters to this task alone.
- **What the files already say**, or anything you guessed.

## Categories

{categories}

## Keys and values

Keys are short and lowercase, `thing.property`: `server-a.ip`, `deploy.command`,
`storage`. Reuse a key to change a fact — never add a second one for the same
thing. Values are one line, written so a newcomer understands them.

A value starting with `→` is a relationship, and relationships draw the
architecture diagram people see:

```sh
ctx remember architecture api.depends-on "→ auth-service, for session checks"
ctx remember decisions storage "SQLite: one file to back up, no database server"
ctx remember decisions rejected.postgres "a server to run for a few megabytes of text"
ctx remember questions tls "build TLS in, or leave it to a reverse proxy?"
```
"""

LOCAL_STEPS = """
1. **`ctx get`** — read the whole context before you start.
2. **`ctx remember` as you learn** (see below).

This context is local only, so there is nothing to pull or push. Once it is put
on a server with `ctx remote`, these instructions gain the sync steps.
"""

REMOTE_STEPS = """
1. **`ctx pull`, then `ctx get`.** Starts you from the latest the team knows.
2. **`ctx remember` as you learn** (see below). Each one is pushed to the
   server straight away; you don't push by hand.
3. **If `ctx pull` reports a conflict** — a fact changed differently here and on
   the server — compare `ctx get` with `ctx get --remote`, settle each listed
   fact with `ctx remember` or `ctx forget`, then `ctx push`. Change nothing
   else: every other fact was merged for you.
4. **Before you finish, `ctx push`.** It does nothing when there is nothing new.
"""

READONLY_STEPS = """
1. **`ctx pull`, then `ctx get`.** Brings in and reads the latest version.
2. **Don't change it.** Its owner and org admins maintain this context; it is
   read-only for this account. When you learn something it should say, tell
   the user, so they can pass it on to whoever maintains it.

The rules below are how its maintainers keep it. They are here so you know what
the facts mean and what kind of thing is worth passing on.
"""


def write_instructions(root, name, has_remote, readonly=False):
    """ctx owns this file and the agent never writes it, so ctx keeps it current
    — including on a later run, so an old setup does not keep stale rules."""
    template = READONLY_STEPS if readonly else REMOTE_STEPS if has_remote else LOCAL_STEPS
    cats = "\n".join(f"- **{slug}** — {desc}" for slug, _, desc in CATEGORIES)
    text = INSTRUCTIONS_TEXT.format(session=template.rstrip(), categories=cats, ctxdir=CTXDIR)
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


def reread(tty=None):
    """One line. The rules live in AGENTS.md -> instructions.md; duplicating them
    in command output only creates a second copy to keep in step."""
    tty = sys.stdout.isatty() if tty is None else tty
    if tty:
        return "Tell your AI to re-read AGENTS.md."
    # the agent already read AGENTS.md at session start, so say why to read it
    # again — otherwise the instruction looks like a no-op.
    return "AGENTS.md changed — re-read it."


POINTER = (
    f"{BEGIN}\n"
    f"This project's AI context is kept in KeepCTX: read `{CTXDIR}/{INSTRUCTIONS}` first.\n"
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


# ------------------------------------------------------------------ commands

def here_or_fail():
    root = find_root()
    if not root:
        err("error: no context here. Run `ctx init` first.")
        return None, None
    cfg = load_config(root)
    if not cfg.get("name"):
        err("error: no context here. Run `ctx init` or `ctx clone <org>:<name>` first.")
        return None, None
    return root, cfg


def cmd_init(argv, refreshed=False):
    here = pathlib.Path.cwd().resolve()
    if CTXDIR in here.parts:
        err(f"error: {here} is inside KeepCTX's own {CTXDIR}/ directory.")
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
            print(("KeepCTX's rules for your agent were updated. " if tty else "") + reread())
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
    facts.write_text(render(read_file(facts)))
    (ctxdir / name / BASE).write_text("")

    save_config(root, {"name": name, "org": None, "remote": None,
                       "token": None, "version": 0})

    write_pointer(root)

    print(f"Initialized `{name}`")
    w = max(len(facts_rel), len(f"{CTXDIR}/{INSTRUCTIONS}"), len(AGENTS))
    print(f"  {facts_rel:<{w}}  your facts")
    print(f"  {CTXDIR}/{INSTRUCTIONS:<{w - len(CTXDIR) - 1}}  how the agent keeps them")
    print(f"  {AGENTS:<{w}}  pointer added at the top")
    print()
    print(reread())
    return 0


def cmd_get(argv):
    """The whole context, for an agent to read: its own facts, then any
    contexts cloned beside it. `--remote` shows what the last pull downloaded."""
    root, cfg = here_or_fail()
    if not root:
        return 1
    name = cfg["name"]
    d = root / CTXDIR / name
    if "--remote" in argv:
        latest = remote_versions(d)
        if not latest:
            err("error: nothing pulled yet. Run `ctx pull` first.")
            return 1
        v, path = latest[-1]
        print(f"# {cfg.get('org')}:{name} on {cfg.get('remote')}, as pulled (v{v})")
        print()
        print(body(read_file(path)) or "(empty)")
        return 0

    facts = read_file(d / FACTS)
    where = f"{cfg['org']}:{name} @ v{cfg.get('version', 0)}" if cfg.get("org") else "local only"
    ro = ", read-only" if cfg.get("readonly") else ""
    print(f"# {name} — {len(facts)} facts ({where}{ro})")
    if cfg.get("conflicts"):
        print()
        print(f"Unsettled conflicts: {', '.join(cfg['conflicts'])}. Compare with "
              "`ctx get --remote`, settle each with `ctx remember` or `ctx forget`, then `ctx push`.")
    print()
    print(body(facts) or "(nothing remembered yet)")
    for n, org in sorted((cfg.get("clones") or {}).items()):
        ref = read_file(root / CTXDIR / n / FACTS)
        print()
        print(f"# {n} — {len(ref)} facts (from {org}, for reference, read-only)")
        print()
        print(body(ref) or "(empty)")
    print()
    print("Categories: " + ", ".join(c for c, _, _ in CATEGORIES))
    return 0


def parse_fact_args(argv, need_value):
    """`<category> <key> [value…]`, or `<category>.<key> [value…]`."""
    if argv and "." in argv[0] and argv[0].split(".")[0] in CATEGORY:
        cat, _, key = argv[0].partition(".")
        rest = argv[1:]
    elif len(argv) >= 2:
        cat, key, rest = argv[0].lower(), argv[1], argv[2:]
    else:
        return None
    key = re.sub(r"\s+", "-", key.strip().lower())
    value = " ".join(rest).strip()
    if cat not in CATEGORY:
        err(f"error: `{cat}` isn't a category. Use one of:")
        err("       " + ", ".join(CATEGORY))
        return False
    if not KEY_RE.match(key):
        err(f"error: `{key}` isn't a key. Keys are short and lowercase: server-a.ip, deploy.command")
        return False
    if need_value and not value:
        return None
    return cat, key, value


def writable(cfg):
    if cfg.get("readonly"):
        err(f"error: {cfg.get('org')}:{cfg['name']} is read-only for this account.")
        err("       Tell the user what you learned, so they can pass it on to its maintainers.")
        return False
    return True


def cmd_remember(argv):
    got = parse_fact_args(argv, need_value=True)
    if not got:
        if got is None:
            err('error: usage: ctx remember <category> <key> "<value>"')
        return 1
    cat, key, value = got
    root, cfg = here_or_fail()
    if not root or not writable(cfg):
        return 1
    what = find_secret(value)
    if what:
        err(f"error: not remembered — that looks like {what}. Secrets never go in a context;")
        err("       remember where it is kept instead.")
        return 1

    rel = "—"
    if value.startswith(("→", "->")):
        rel, value = "→", value.lstrip("→->").strip()
    full = f"{cat}.{key}"
    path = root / CTXDIR / cfg["name"] / FACTS
    facts = read_file(path)
    before = facts.get(full)
    facts[full] = (rel, value)
    path.write_text(render(facts))
    verb = "remembered" if before is None else "unchanged" if before == facts[full] else "updated"
    say(f"{verb} {full} {rel} {value}")
    settle(cfg, full)
    return finish_write(root, cfg)


def cmd_forget(argv):
    got = parse_fact_args(argv, need_value=False)
    if not got:
        if got is None:
            err("error: usage: ctx forget <category> <key>")
        return 1
    cat, key, _ = got
    root, cfg = here_or_fail()
    if not root or not writable(cfg):
        return 1
    full = f"{cat}.{key}"
    path = root / CTXDIR / cfg["name"] / FACTS
    facts = read_file(path)
    if full not in facts:
        say(f"nothing to forget — no {full}")
        settle(cfg, full)
        save_config(root, cfg)
        return 0
    del facts[full]
    path.write_text(render(facts))
    say(f"forgot {full}")
    settle(cfg, full)
    return finish_write(root, cfg)


def settle(cfg, full):
    """Remembering or forgetting a conflicted fact is how the agent settles it."""
    if full in (cfg.get("conflicts") or []):
        cfg["conflicts"] = [k for k in cfg["conflicts"] if k != full]


def finish_write(root, cfg):
    """After a remember or forget: push straight away when there's a server, so
    the team has it now and a session that ends abruptly loses nothing."""
    if cfg.get("org"):
        push(root, cfg)
    save_config(root, cfg)
    return 0


def remote_versions(d):
    p = d / REMOTE_DIR
    if not p.is_dir():
        return []
    found = []
    for f in p.glob("v*.md"):
        try:
            found.append((int(f.stem[1:]), f))
        except ValueError:
            pass
    return sorted(found)


def keep_remote(d, version, text):
    """Each pull is kept by version, so the agent can read exactly what the
    server said; only the last few, since the server keeps every version."""
    p = d / REMOTE_DIR
    p.mkdir(exist_ok=True)
    (p / f"v{version}.md").write_text(text)
    for _, f in remote_versions(d)[:-KEEP_REMOTE]:
        f.unlink()


def pull_own(root, cfg):
    """Download the latest, keep it, and merge it into the local facts. -> the
    conflicts still to settle."""
    name = cfg["name"]
    d = root / CTXDIR / name
    got = api(cfg, "GET", f"/v1/contexts/{cfg['org']}/{name}")
    remote = parse(got["facts"])
    keep_remote(d, got["version"], render(remote))
    say(f"pulled {len(remote)} facts from {cfg['remote']} (v{got['version']})")

    if cfg.get("readonly"):            # someone else maintains it: take theirs
        (d / FACTS).write_text(render(remote))
        (d / BASE).write_text(render(remote))
        cfg["version"] = got["version"]
        return []

    local = read_file(d / FACTS)
    base = read_file(d / BASE)
    merged, n, new = merge3(base, local, remote)
    # a conflict left unsettled from before is still one while the two differ
    old = [k for k in cfg.get("conflicts") or [] if merged.get(k) != remote.get(k)]
    conflicts = sorted(set(old) | set(new))
    (d / FACTS).write_text(render(merged))
    (d / BASE).write_text(render(remote))
    cfg["version"] = got["version"]
    cfg["conflicts"] = conflicts

    took = [f"{n[k]} {k}" for k in ("added", "changed", "removed") if n[k]]
    if took or n["kept"]:
        parts = ([", ".join(took) + " from the server"] if took else []) + \
                ([f"{n['kept']} local change{'s' * (n['kept'] != 1)} kept"] if n["kept"] else [])
        say("merged — " + "; ".join(parts))
    if conflicts:
        say(f"{len(conflicts)} conflict{'s' * (len(conflicts) != 1)} to settle: {', '.join(conflicts)}")
        say("compare `ctx get` with `ctx get --remote`, settle each with `ctx remember` "
            "or `ctx forget`, then `ctx push`")
    return conflicts


def push(root, cfg):
    """Send the local facts. If the server moved on since the last pull, pull
    and merge first; stop if that leaves a conflict for the agent to settle.
    -> True when the server has what's here."""
    name = cfg["name"]
    d = root / CTXDIR / name
    for _ in range(3):
        if cfg.get("conflicts"):
            say(f"not pushed — settle {', '.join(cfg['conflicts'])} first")
            return False
        local = read_file(d / FACTS)
        if local == read_file(d / BASE):
            return True
        out = api(cfg, "POST", f"/v1/contexts/{cfg['org']}/{name}/push",
                  {"facts": render(local), "version": cfg.get("version", 0)}, allow=(409,))
        if out.get("_status") == 409:
            say(f"the server moved on to v{out.get('version', '?')} — pulling first")
            if pull_own(root, cfg):
                return False
            continue
        (d / BASE).write_text(render(local))
        cfg["version"] = out["version"]
        say(f"pushed {len(local)} facts to {cfg['remote']} (v{out['version']})")
        return True
    say("not pushed — the server keeps changing; try `ctx push` again")
    return False


def pull_clone(root, cfg, org, name):
    got = api(cfg, "GET", f"/v1/contexts/{org}/{name}")
    d = root / CTXDIR / name
    d.mkdir(parents=True, exist_ok=True)
    facts = parse(got["facts"])
    (d / FACTS).write_text(render(facts))
    say(f"pulled {len(facts)} facts of {org}:{name} for reference (v{got['version']})")


def no_remote():
    say("this context is local only — nothing to sync. `ctx remote` puts it on a server.")
    return 0


def cmd_pull(argv):
    root, cfg = here_or_fail()
    if not root:
        return 1
    if not cfg.get("org") and not cfg.get("clones"):
        return no_remote()
    if cfg.get("org"):
        pull_own(root, cfg)
    for name, org in sorted((cfg.get("clones") or {}).items()):
        pull_clone(root, cfg, org, name)
    save_config(root, cfg)
    return 0


def cmd_push(argv):
    root, cfg = here_or_fail()
    if not root:
        return 1
    if not cfg.get("org"):
        return no_remote()
    if not writable(cfg):
        return 1
    d = root / CTXDIR / cfg["name"]
    if not cfg.get("conflicts") and read_file(d / FACTS) == read_file(d / BASE):
        say(f"nothing new to push — {cfg['org']}:{cfg['name']} is at v{cfg.get('version', 0)}")
        save_config(root, cfg)
        return 0
    ok = push(root, cfg)
    save_config(root, cfg)
    return 0 if ok else 1


# -------------------------------------------------------- remote and clone

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

    facts = render(read_file(root / CTXDIR / name / FACTS))
    made = api(cfg, "POST", "/v1/contexts", {"name": name, "facts": facts, "org": org})
    cfg["version"] = made["version"]
    cfg["conflicts"] = []
    save_config(root, cfg)
    (root / CTXDIR / name / FACTS).write_text(facts)
    (root / CTXDIR / name / BASE).write_text(facts)
    write_instructions(root, name, has_remote=True)

    say(f"pushed {len(parse(facts))} facts to {remote} (v{made['version']})")
    print(f"{org}:{name} is live. Others can `ctx clone {org}:{name}`")
    return 0


def cmd_clone(argv):
    """Bring a remote context here. In a directory with no context of its own it
    becomes this directory's context — writable if you maintain it (its owner or
    an org admin), read-only otherwise. Beside an existing context it's a
    read-only reference. Either way, `ctx pull` keeps it current."""
    if not argv or ":" not in argv[0]:
        err("error: usage: ctx clone <org>:<name> [server]")
        return 1
    org, _, name = argv[0].partition(":")
    here = pathlib.Path.cwd().resolve()
    if CTXDIR in here.parts:
        err(f"error: {here} is inside KeepCTX's own {CTXDIR}/ directory.")
        return 1
    root = find_root() or here
    cfg = load_config(root)
    own = cfg.get("name")
    if own == name and cfg.get("org") == org:
        print(f"{org}:{name} is already this directory's context — `ctx pull` to update it.")
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
    facts = render(parse(got["facts"]))

    ctxdir = root / CTXDIR
    (ctxdir / name).mkdir(parents=True, exist_ok=True)
    (ctxdir / ".gitignore").write_text("*\n")
    (ctxdir / name / FACTS).write_text(facts)

    if own:
        cfg.setdefault("clones", {})[name] = org
        save_config(root, cfg)
        print(f"Cloned {org}:{name} beside `{own}` ({len(parse(facts))} facts, read-only)")
        print("`ctx get` shows it after this context's own facts; `ctx pull` keeps it current.")
    else:
        readonly = not got.get("can_write")
        (ctxdir / name / BASE).write_text(facts)
        keep_remote(ctxdir / name, got["version"], facts)
        cfg.update({"name": name, "org": org, "version": got["version"], "readonly": readonly,
                    "conflicts": []})
        save_config(root, cfg)
        write_instructions(root, name, has_remote=True, readonly=readonly)
        write_pointer(root)
        print(f"Cloned {org}:{name} ({len(parse(facts))} facts)")
        if readonly:
            print(f"Read-only: {got.get('owner') or 'its owner'} and {org}'s admins maintain it.")
            print("`ctx pull` brings in their updates.")
        else:
            print("You maintain it: `ctx remember` here is pushed to the server and your other copies.")
    print()
    print(reread())
    return 0


# -------------------------------------------------------------------- status

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
    facts = read_file(root / CTXDIR / name / FACTS)

    print(f"KeepCTX {VERSION}")
    print(f"  root      {root}")
    print(f"  context   {name}")
    print(f"  facts     {len(facts)}")
    if cfg.get("org"):
        ro = ", read-only" if cfg.get("readonly") else ""
        print(f"  remote    {cfg['org']}:{name} @ v{cfg.get('version', 0)} on {cfg.get('remote')}{ro}")
    else:
        print("  remote    none — `ctx remote` to share this")
    if cfg.get("conflicts"):
        print(f"  conflicts {', '.join(cfg['conflicts'])}")

    clones = cfg.get("clones") or {}
    if clones:
        print(f"  cloned    {', '.join(f'{o}:{n}' for n, o in sorted(clones.items()))}")
    if with_usage:            # plain `ctx`: a person asking what this is and what it does
        print()
        usage()
    return 0


def agent_index(root):
    """One line per context. The facts themselves come from `ctx get`."""
    scope = contexts_in_scope()
    if not scope:
        return 0
    bits = []
    for r, n, kind in scope:
        count = len(read_file(r / CTXDIR / n / FACTS))
        tag = "" if kind == "own" else ", read-only"
        bits.append(f"{n} ({count} facts{tag})")
    print("Contexts: " + ", ".join(bits) + ". Read them with `ctx get`.")
    return 0


def usage():
    print("KeepCTX — keep your AI context across sessions, across AIs, across your team")
    print()
    print("  ctx                              Show status")
    print("  ctx init [name]                  Set up here — local, no account, no network")
    print("  ctx get [--remote]               Print the whole context (or the last pulled copy)")
    print('  ctx remember <category> <key> "<value>"')
    print("                                   Add or replace a fact")
    print("  ctx forget <category> <key>      Remove a fact")
    print("  ctx remote [server]              Put this on a server — shares it and backs it up")
    print("  ctx clone <org>:<name> [server]  Bring a context here from a server")
    print("  ctx pull                         Bring in the latest and merge it, fact by fact")
    print("  ctx push                         Send what's here")
    print()
    print("Categories: " + ", ".join(CATEGORY))
    print()
    print("Everything works locally without an account. The server is keepctx.com")
    print("unless you name your own: ctx remote https://keepctx.example.com")
    return 0


COMMANDS = {
    "get": cmd_get, "remember": cmd_remember, "forget": cmd_forget,
    "pull": cmd_pull, "push": cmd_push, "remote": cmd_remote, "clone": cmd_clone,
}


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
    if cmd in COMMANDS:
        return COMMANDS[cmd](argv[1:])
    if cmd == "sync":
        err("error: `ctx sync` is now `ctx pull` and `ctx push` — and `ctx remember`")
        err("       pushes by itself. Re-read AGENTS.md for the new steps.")
        return 1
    if not argv:
        return cmd_status(with_usage=True)
    err(f"error: unknown command `{cmd}`")
    return usage()


if __name__ == "__main__":
    sys.exit(main())
