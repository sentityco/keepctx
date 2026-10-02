#!/usr/bin/env python3
"""keepctx — keep one context. Every session, every AI, every teammate.

Installed as `keepctx`, with `ctx` as a short alias.

A directory holds one context: a set of facts in `.ctx/context.json`, each a
value with the time it was last changed. The agent starts with `ctx ai`, reads
with `ctx get`, and changes facts with `ctx remember` and `ctx forget`. With a
server, `ctx pull` and `ctx push` keep copies in step: for every fact, the most
recent change wins.
"""
import getpass
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

VERSION = "0.3.0"
DEFAULT_REMOTE = os.environ.get("CTX_REMOTE", "https://keepctx.com")

CTXDIR = ".ctx"
CONFIG = "config.json"      # where it syncs, and the sign-in
CONTEXT = "context.json"    # the facts: the only copy there is
AGENTS = "AGENTS.md"

BEGIN = "<!-- ctx -->"
END = "<!-- /ctx -->"

KEY_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")

# slug, heading, what belongs there. The order is the order they're shown in.
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
     "What is still undecided. Forgotten once a decision settles it."),
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
    """Everything an operator should see starts with KeepCTX:, and the rules
    tell the agent to pass these lines on."""
    print(f"KeepCTX: {msg}")


def err(msg):
    """Errors go to stderr, so an agent piping stdout gets only real output."""
    print(msg, file=sys.stderr)


def plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


# ---------------------------------------------------------------- filesystem

def find_root(start=None):
    """Nearest directory containing .ctx/. None if there isn't one."""
    d = pathlib.Path(start or os.getcwd()).resolve()
    return next((c for c in [d, *d.parents] if (c / CTXDIR).is_dir()), None)


def load_json(path):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def load_config(root):
    return load_json(root / CTXDIR / CONFIG)


def save_config(root, cfg):
    keep = {k: v for k, v in cfg.items() if not k.startswith("_")}
    (root / CTXDIR / CONFIG).write_text(json.dumps(keep, indent=2) + "\n")


def load_facts(root):
    return load_json(root / CTXDIR / CONTEXT).get("facts", {})


def save_facts(root, cfg, facts):
    data = {"name": cfg.get("name"), "facts": dict(sorted(facts.items()))}
    (root / CTXDIR / CONTEXT).write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")


def slugify(name):
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "context"


GENERIC = {
    "src", "app", "api", "web", "lib", "code", "work", "dev", "test", "tmp",
    "project", "repo", "main", "new", "my-project", "untitled", "workspace",
}


# -------------------------------------------------------------------- facts
#
# facts = {"category.key": {"value": str, "updated": str, "removed": bool}}
#
# `updated` is UTC, fixed width, so comparing the strings compares the times.
# A forgotten fact keeps its key, marked removed, so the removal reaches every
# other copy instead of the fact coming back from one that still has it.

def now():
    t = time.time()
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + f".{int(t % 1 * 1000):03d}Z"


def newer(a, b):
    """The more recent of two versions of one fact. Ties go the same way on
    every machine, so two copies always settle on the same answer."""
    if a is None or b is None:
        return a or b
    ka = (a.get("updated", ""), a.get("removed", False), a.get("value", ""))
    kb = (b.get("updated", ""), b.get("removed", False), b.get("value", ""))
    return a if ka >= kb else b


def merge(local, incoming):
    """-> (merged, counts of what incoming changed here)."""
    merged = dict(local)
    n = {"new": 0, "updated": 0, "removed": 0}
    for k, theirs in incoming.items():
        mine = local.get(k)
        win = newer(mine, theirs)
        if win is mine:
            continue
        merged[k] = theirs
        if theirs.get("removed"):
            if mine and not mine.get("removed"):
                n["removed"] += 1
        elif mine is None or mine.get("removed"):
            n["new"] += 1
        elif mine.get("value") != theirs.get("value"):
            n["updated"] += 1
    return merged, n


def live(facts):
    return {k: f for k, f in facts.items() if not f.get("removed")}


def render(facts):
    """The facts an agent reads: a heading per category, one line per fact."""
    by_cat = {}
    for full, f in sorted(live(facts).items()):
        cat, _, key = full.partition(".")
        by_cat.setdefault(cat, []).append(f"- **{key}** — {f['value']}")
    out = []
    for cat in [c for c, _, _ in CATEGORIES] + sorted(c for c in by_cat if c not in CATEGORY):
        if cat in by_cat:
            out += [f"## {CATEGORY.get(cat, (cat.title(),))[0]}", ""] + by_cat[cat] + [""]
    return "\n".join(out).rstrip()


def find_secret(text):
    for what, rx in SECRETS:
        if rx.search(text or ""):
            return what
    return None


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
            raise SystemExit(f"ctx: {base} sent back something that isn't the KeepCTX API. "
                             "Check the server address, or try again in a minute.")
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            detail = json.loads(raw).get("error", raw)
        except json.JSONDecodeError:
            detail = raw
        if e.code == 401 and tok and not path.startswith("/v1/auth/"):
            # sign-ins last 30 days. a person can just sign in again; an agent
            # can't type a password, so it gets told who can.
            if not (sys.stdin.isatty() and sys.stdout.isatty()):
                raise SystemExit("ctx: the KeepCTX sign-in here has expired. "
                                 "Run `ctx pull` in a terminal to sign in again.")
            print("Your KeepCTX sign-in has expired. Sign in again:")
            cfg["token"] = login(cfg)[0]["token"]
            cfg["_signed_in"] = True          # caller saves it
            return api(cfg, method, path, body)
        raise SystemExit(f"ctx: {detail}" if e.code in (400, 401, 403, 404, 409)
                         else f"ctx: server said {e.code}: {detail}")
    except urllib.error.URLError as e:
        raise SystemExit(f"ctx: cannot reach {base} ({e.reason})")


# --------------------------------------------------------------------- rules

RULES = """# KeepCTX — how to work with this project's context

This project's context is kept in KeepCTX: what it is, why, how it is built and
run, what has been decided, and what is still open. It outlasts this session,
and every AI and every person on the project reads the same facts. Use it, and
keep it current as you work. The context itself is printed after these rules.

Work through the `ctx` command only. Never edit the files in `.ctx/` yourself.

## Every session
{session}

## Commands

| Command | When |
|---|---|
| `ctx ai` | the start of every session — you just ran it |
| `ctx get` | to read the whole context again |
| `ctx remember <category> <key> "<value>"` | the moment you learn something worth keeping |
| `ctx forget <category> <key>` | when a fact is wrong or gone, or a question is settled |
| `ctx pull` | now and then in a long session, to bring in what others learned |
| `ctx push` | before you finish; `remember` and `forget` already push |

## Tell the user

Every line `ctx` prints that starts with `KeepCTX:` is for the user too. Repeat
it in your reply, as it was printed, so they always see what is kept and synced:

    KeepCTX: remembered environments.server-a.ip — 10.0.4.12
    KeepCTX: pulled 45 facts from https://keepctx.com — 2 new, 1 updated

## Remember

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

**Leave existing facts alone** unless they are wrong, out of date, or the user
asks for a change. Remember a fact again only to change it; forget it only when
it is no longer true.

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

```sh
ctx remember architecture api.depends-on "auth-service, for session checks"
ctx remember decisions storage "SQLite: one file to back up, no database server"
ctx remember decisions rejected.postgres "a server to run for a few megabytes of text"
ctx remember questions tls "build TLS in, or leave it to a reverse proxy?"
```
"""

LOCAL_STEPS = """
1. **You just ran `ctx ai`.** Everything known about this project is printed
   below these rules. Read it before you start.
2. **`ctx remember` as you learn** (see below).

This context is local only, so there is nothing to pull or push. Once it is put
on a server with `ctx remote`, `ctx ai` adds the sync steps.
"""

REMOTE_STEPS = """
1. **You just ran `ctx ai`.** It pulled the latest from the server and printed
   it below these rules. Pass its `KeepCTX:` lines on to the user, then read the
   context before you start.
2. **`ctx remember` as you learn** (see below). Each one is pushed straight away.
3. **In a long session, `ctx pull` now and then** — after a break, or before a
   big change — to pick up what others have learned since. For every fact the
   most recent change wins, so there is never anything to merge by hand.
4. **Before you finish, `ctx push`.** It does nothing when there is nothing new.
"""

READONLY_STEPS = """
1. **You just ran `ctx ai`.** It pulled the latest version and printed it below
   these rules. Pass its `KeepCTX:` lines on to the user, then read it.
2. **Don't change it.** Its owner and org admins maintain this context; it is
   read-only for this account. When you learn something it should say, tell
   the user, so they can pass it on to whoever maintains it.

The rules below are how its maintainers keep it. They are here so you know what
the facts mean and what kind of thing is worth passing on.
"""


def rules(cfg):
    """The agent's instructions, made fresh on every `ctx ai` from the installed
    CLI — so they can never go stale, and upgrading is just reinstalling."""
    steps = (READONLY_STEPS if cfg.get("readonly") else
             REMOTE_STEPS if cfg.get("org") else LOCAL_STEPS)
    cats = "\n".join(f"- **{slug}** — {desc}" for slug, _, desc in CATEGORIES)
    return RULES.format(session=steps.rstrip(), categories=cats)


def reread(tty=None):
    """One line, after AGENTS.md gains or changes its pointer."""
    tty = sys.stdout.isatty() if tty is None else tty
    if tty:
        return "Tell your AI to re-read AGENTS.md."
    return "AGENTS.md changed — re-read it."


POINTER = (
    f"{BEGIN}\n"
    f"This project's AI context is kept in KeepCTX. Start every session by running `ctx ai`:\n"
    f"it prints how to work with the context, then everything in it.\n"
    f"No `ctx` command, or no `{CTXDIR}/` here? Carry on without it, and don't flag it — it may\n"
    f"not be set up on this machine. To set it up, install ctx (https://keepctx.com), then\n"
    f"`ctx clone <org>:<name>`, or `ctx init` for a new one.\n"
    f"{END}\n"
)


def write_pointer(root):
    """The pointer goes at the top of AGENTS.md, and nothing else in the file is
    touched. An older pointer is replaced. -> True if the file changed."""
    agents = root / AGENTS
    existing = agents.read_text() if agents.exists() else ""
    if BEGIN in existing and END in existing:
        start = existing.index(BEGIN)
        end = existing.index(END, start) + len(END)
        updated = existing[:start] + POINTER.rstrip("\n") + existing[end:]
    else:
        updated = POINTER + ("\n" + existing if existing else "")
    if updated == existing:
        return False
    agents.write_text(updated)
    return True


# ------------------------------------------------------------------ commands

def here_or_fail():
    root = find_root()
    cfg = load_config(root) if root else {}
    if not cfg.get("name"):
        err("error: no context here. Run `ctx init`, or `ctx clone <org>:<name>`.")
        return None, None
    return root, cfg


def make_context(root, name):
    """A new, empty context in root/.ctx — which ignores itself in git."""
    (root / CTXDIR).mkdir(exist_ok=True)
    (root / CTXDIR / ".gitignore").write_text("*\n")
    cfg = {"name": name, "org": None, "remote": None, "token": None}
    save_config(root, cfg)
    save_facts(root, cfg, {})
    return cfg


def cmd_init(argv):
    here = pathlib.Path.cwd().resolve()
    if CTXDIR in here.parts:
        err(f"error: {here} is inside KeepCTX's own {CTXDIR}/ directory.")
        return 1
    if (here / CTXDIR).is_dir():          # one context per directory
        cmd_status()
        if write_pointer(here):
            print()
            print(reread())
        return 0
    name = slugify(argv[0]) if argv else slugify(here.name)
    make_context(here, name)
    write_pointer(here)
    print(f"Initialized `{name}`")
    print(f"  {CTXDIR}/      the context — ignored by git")
    print(f"  {AGENTS}  pointer at the top: your AI starts with `ctx ai`")
    print()
    print(reread())
    return 0


def cmd_ai(argv):
    """Where an agent starts, named in AGENTS.md: pull when there is a server,
    then the rules, then the whole context — one command for the whole start."""
    root = find_root()
    cfg = load_config(root) if root else {}
    if not cfg.get("name"):
        say("no context here — carry on without it.")
        return 0
    if cfg.get("org"):
        try:
            pull(root, cfg)
        except SystemExit as e:           # offline, or signed out: work from what's here
            say(f"couldn't pull ({str(e).removeprefix('ctx: ')}) — working from the local copy")
        save_config(root, cfg)
    print()
    print(rules(cfg))
    return cmd_get([])


def cmd_get(argv):
    root, cfg = here_or_fail()
    if not root:
        return 1
    facts = live(load_facts(root))
    name = cfg["name"]
    where = f"{cfg['org']}:{name} on {cfg['remote']}" if cfg.get("org") else "local only"
    ro = ", read-only" if cfg.get("readonly") else ""
    print(f"# {name} — {plural(len(facts), 'fact')} ({where}{ro})")
    print()
    print(render(facts) or "(nothing remembered yet)")
    print()
    print("Categories: " + ", ".join(c for c, _, _ in CATEGORIES))
    return 0


def parse_fact_args(argv, need_value):
    """`<category> <key> [value…]`, or `<category>.<key> [value…]`.
    -> (category, key, value), None for a usage error, False for a bad one."""
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
    full = f"{cat}.{key}"
    facts = load_facts(root)
    before = facts.get(full)
    if before and not before.get("removed") and before.get("value") == value:
        say(f"already remembered {full} — {value}")
        return 0
    facts[full] = {"value": value, "updated": now(), "removed": False}
    save_facts(root, cfg, facts)
    verb = "updated" if before and not before.get("removed") else "remembered"
    say(f"{verb} {full} — {value}")
    return after_write(root, cfg)


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
    facts = load_facts(root)
    if full not in facts or facts[full].get("removed"):
        say(f"nothing to forget — no {full}")
        return 0
    facts[full] = {**facts[full], "updated": now(), "removed": True}
    save_facts(root, cfg, facts)
    say(f"forgot {full}")
    return after_write(root, cfg)


def after_write(root, cfg):
    """With a server, every change is pushed the moment it's made, so the team
    has it now and a session that ends abruptly loses nothing."""
    if cfg.get("org"):
        try:
            push(root, cfg)
        except SystemExit as e:
            say(f"kept here, not pushed ({str(e).removeprefix('ctx: ')}) — `ctx push` later")
        save_config(root, cfg)
    return 0


def pull(root, cfg):
    got = api(cfg, "GET", f"/v1/contexts/{cfg['org']}/{cfg['name']}")
    cfg["readonly"] = not got.get("can_write")
    facts, n = merge(load_facts(root), got.get("facts") or {})
    save_facts(root, cfg, facts)
    changes = [f"{n[k]} {k}" for k in ("new", "updated", "removed") if n[k]]
    say(f"pulled {plural(len(live(got.get('facts') or {})), 'fact')} from {cfg['remote']}"
        + (" — " + ", ".join(changes) if changes else " — nothing new"))


def push(root, cfg):
    """Send every fact; the server keeps the most recent version of each and
    sends back the result, so a push also brings in what others changed."""
    facts = load_facts(root)
    got = api(cfg, "POST", f"/v1/contexts/{cfg['org']}/{cfg['name']}/push", {"facts": facts})
    merged, n = merge(facts, got.get("facts") or {})
    save_facts(root, cfg, merged)
    sent = got.get("accepted", 0)
    also = [f"{n[k]} {k}" for k in ("new", "updated", "removed") if n[k]]
    if sent or also:
        say(f"pushed {plural(sent, 'change')} to {cfg['remote']}"
            + (" — and pulled " + ", ".join(also) if also else ""))
    return got


def cmd_pull(argv):
    root, cfg = here_or_fail()
    if not root:
        return 1
    if not cfg.get("org"):
        return no_remote()
    pull(root, cfg)
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
    got = push(root, cfg)
    if not got.get("accepted"):
        say(f"nothing new to push — {cfg['org']}:{cfg['name']} is up to date")
    save_config(root, cfg)
    return 0


def no_remote():
    say("this context is local only — nothing to sync. `ctx remote` puts it on a server.")
    return 0


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
    root, cfg = here_or_fail()
    if not root:
        return 1
    if cfg.get("org"):
        print(f"Already shared as {cfg['org']}:{cfg['name']} on {cfg['remote']}")
        return 1
    name = cfg["name"]
    if "--name" in argv:
        i = argv.index("--name")
        name = slugify(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    if name in GENERIC:
        err(f"error: `{name}` is too generic to claim.")
        err("       Pick a name: ctx remote --name <name>")
        return 1

    cfg["remote"] = server_url(argv[0]) if argv else DEFAULT_REMOTE
    print(f"Server: {cfg['remote']}")
    print(f"Sign in (no account? make one at {app_url(cfg)})")
    out, email = login(cfg)
    cfg["token"] = out["token"]
    org = choose_org(out.get("orgs") or [], email, app_url(cfg))
    if not org:
        return 1
    facts = load_facts(root)
    api(cfg, "POST", "/v1/contexts", {"name": name, "org": org, "facts": facts})
    cfg.update({"org": org, "name": name, "readonly": False})
    save_facts(root, cfg, facts)
    save_config(root, cfg)
    say(f"pushed {plural(len(live(facts)), 'fact')} to {cfg['remote']}")
    print(f"{org}:{name} is live. Others can `ctx clone {org}:{name}`")
    return 0


def cmd_clone(argv):
    """Bring a shared context here. A directory holds one context: into an empty
    one it's set up fresh; into one whose local context has the same name, the
    two are joined and merged, newest change winning; anything else is refused."""
    if not argv or ":" not in argv[0]:
        err("error: usage: ctx clone <org>:<name> [server]")
        return 1
    org, _, name = argv[0].partition(":")
    remote = server_url(argv[1]) if len(argv) > 1 else DEFAULT_REMOTE
    here = pathlib.Path.cwd().resolve()
    if CTXDIR in here.parts:
        err(f"error: {here} is inside KeepCTX's own {CTXDIR}/ directory.")
        return 1

    existing = load_config(here) if (here / CTXDIR).is_dir() else {}
    if existing.get("org"):
        if (existing["org"], existing["name"]) == (org, name):
            print(f"{org}:{name} is already here — `ctx pull` brings in the latest.")
            return 0
        err(f"error: this directory already holds {existing['org']}:{existing['name']}.")
        err("       One context per directory — clone it somewhere else.")
        return 1
    if existing.get("name") and existing["name"] != name:
        err(f"error: this directory already holds a local context, `{existing['name']}`.")
        err("       One context per directory — clone it somewhere else, or share this one")
        err("       with `ctx remote`.")
        return 1

    cfg = existing or {"name": name}
    cfg.update({"remote": remote, "org": org, "name": name})
    print(f"Sign in to {remote} (no account? make one at {app_url(cfg)})")
    cfg["token"] = login(cfg)[0]["token"]
    got = api(cfg, "GET", f"/v1/contexts/{org}/{name}")

    joined = bool(existing)
    if not joined:
        make_context(here, name)
    local = load_facts(here)
    facts, n = merge(local, got.get("facts") or {})
    cfg["readonly"] = not got.get("can_write")
    save_facts(here, cfg, facts)
    save_config(here, cfg)
    write_pointer(here)

    count = plural(len(live(got.get("facts") or {})), "fact")
    if joined:
        say(f"joined your local `{name}` to {org}:{name} — pulled {count}, "
            f"{n['new']} new here; for each fact the newest change wins")
        if live(local) and not cfg["readonly"]:
            try:
                push(here, cfg)
            except SystemExit as e:
                say(f"your local facts weren't pushed ({str(e).removeprefix('ctx: ')})")
    else:
        say(f"cloned {org}:{name} from {remote} — {count}")
    if cfg["readonly"]:
        print(f"Read-only: {got.get('owner') or 'its owner'} and {org}'s admins maintain it.")
    print()
    print(reread())
    return 0


# -------------------------------------------------------------------- status

def cmd_status(with_usage=False):
    root = find_root()
    piped = not sys.stdout.isatty()   # a hook or an agent is reading, not a person
    if not root:
        return 0 if piped else usage()
    cfg = load_config(root)
    count = len(live(load_facts(root)))
    if piped:
        print(f"Context: {cfg.get('name')} ({plural(count, 'fact')}). Start with `ctx ai`.")
        return 0
    print(f"KeepCTX {VERSION}")
    print(f"  root      {root}")
    print(f"  context   {cfg.get('name')}")
    print(f"  facts     {count}")
    if cfg.get("org"):
        ro = ", read-only" if cfg.get("readonly") else ""
        print(f"  shared    {cfg['org']}:{cfg['name']} on {cfg.get('remote')}{ro}")
    else:
        print("  shared    no — `ctx remote` to share it")
    if with_usage:
        print()
        usage()
    return 0


def usage():
    """For people. The agent's commands and rules come from `ctx ai`."""
    print("KeepCTX — keep one context. Every session, every AI, every teammate.")
    print()
    print("  ctx init [name]                  set up here — local, no account, no network")
    print("  ctx remote [server]              share it on a server (keepctx.com unless you name one)")
    print("  ctx clone <org>:<name> [server]  bring a shared context here")
    print("  ctx get                          see everything in it")
    print()
    print("Your AI starts with `ctx ai` — run it yourself to see what it's told.")
    return 0


COMMANDS = {
    "ai": cmd_ai, "get": cmd_get, "remember": cmd_remember, "forget": cmd_forget,
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
    if cmd == "init":
        return cmd_init(argv[1:])
    if cmd in COMMANDS:
        return COMMANDS[cmd](argv[1:])
    if not argv:
        return cmd_status(with_usage=True)
    err(f"error: unknown command `{cmd}`")
    return usage()


if __name__ == "__main__":
    sys.exit(main())
