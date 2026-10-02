#!/usr/bin/env python3
"""keepctx — keep one context. Every session, every AI, every teammate.

Installed as `keepctx`, with `ctx` as a short alias.

A project's context is one file in git, `.ctx/context.jsonl`: one fact per
line, sorted by key. The agent starts with `ctx ai`, reads with `ctx get`, and
changes facts with `ctx remember` and `ctx forget`. Git does the rest — the
file travels with the code, teammates get it when they pull, history is the
log, and two people changing different facts merge cleanly.
"""
import json
import os
import pathlib
import re
import subprocess
import sys

VERSION = "0.4.0"

CTXDIR = ".ctx"
CONTEXT = "context.jsonl"   # one fact per line, so git merges it fact by fact
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

# Shapes that are only ever credentials. The context is committed to git, so
# keeping these out of it matters more, not less.
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


# -------------------------------------------------------------------- facts

def find_root(start=None):
    """Nearest directory containing .ctx/. None if there isn't one."""
    d = pathlib.Path(start or os.getcwd()).resolve()
    return next((c for c in [d, *d.parents] if (c / CTXDIR).is_dir()), None)


def load(root):
    """-> {"category.key": value}. A line that won't parse — half of a git
    conflict, say — is reported, never silently dropped."""
    path = root / CTXDIR / CONTEXT
    facts, bad = {}, []
    if path.exists():
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if not line.strip():
                continue
            try:
                f = json.loads(line)
                facts[f["key"]] = f["value"]
            except (json.JSONDecodeError, KeyError, TypeError):
                bad.append(n)
    if bad:
        err(f"warning: {CTXDIR}/{CONTEXT} has {plural(len(bad), 'line')} that "
            f"isn't a fact ({', '.join(map(str, bad))}) — a git conflict left in it?")
    return facts


def save(root, facts):
    """One fact per line, sorted by key: two people adding or changing different
    facts touch different lines, so git merges them without a conflict."""
    lines = [json.dumps({"key": k, "value": facts[k]}, ensure_ascii=False) for k in sorted(facts)]
    (root / CTXDIR / CONTEXT).write_text("".join(line + "\n" for line in lines))


# ------------------------------------------------------------- git merging
#
# Git's own merge works line by line and calls two changes on neighbouring
# lines a conflict — and in a small sorted file, nearly every fact is a
# neighbour. So the file gets its own merge driver: fact by fact, against the
# version both sides started from. `.ctx/.gitattributes` (committed) names the
# driver; each clone's git config says how to run it, which `ctx init` and
# `ctx ai` set. Without ctx, git falls back to its normal merge.

ATTRIBUTES = f"{CONTEXT} merge=keepctx\n"


def read_lines(path):
    facts = {}
    for line in pathlib.Path(path).read_text().splitlines() if pathlib.Path(path).exists() else []:
        try:
            f = json.loads(line)
            facts[f["key"]] = f["value"]
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
    return facts


def merge3(base, ours, theirs):
    """-> (merged, conflicts). A fact changed or removed on one side only is
    taken from that side; changed differently on both, it's a conflict."""
    merged, conflicts = {}, []
    for k in sorted(set(base) | set(ours) | set(theirs)):
        b, o, t = base.get(k), ours.get(k), theirs.get(k)
        pick = o if o == t else t if o == b else o if t == b else None
        if o != t and o != b and t != b:
            conflicts.append(k)
        elif pick is not None:
            merged[k] = pick
    return merged, conflicts


def cmd_git_merge(argv):
    """Called by git as the merge driver: `%O %A %B`. Writes the result to %A,
    and exits 1 if a fact needs a person (or an agent) to choose."""
    base, ours, theirs = (read_lines(p) for p in argv[:3])
    merged, conflicts = merge3(base, ours, theirs)
    line = lambda k, v: json.dumps({"key": k, "value": v}, ensure_ascii=False) + "\n"
    out = [line(k, v) for k, v in sorted(merged.items())]
    for k in conflicts:          # only the facts both sides changed, marked the git way
        out += ["<<<<<<< ours\n"] + ([line(k, ours[k])] if k in ours else []) + ["=======\n"] \
            + ([line(k, theirs[k])] if k in theirs else []) + [">>>>>>> theirs\n"]
    pathlib.Path(argv[1]).write_text("".join(out))
    return 1 if conflicts else 0


def setup_git(root):
    """Make git merge the context fact by fact in this clone. Quiet, and a no-op
    outside a git repo or when it's already set."""
    attrs = root / CTXDIR / ".gitattributes"
    if not attrs.exists() or attrs.read_text() != ATTRIBUTES:
        attrs.write_text(ATTRIBUTES)
    driver = f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}" git-merge %O %A %B'
    try:
        have = subprocess.run(["git", "config", "--local", "merge.keepctx.driver"], cwd=root,
                              capture_output=True, text=True)
        if have.returncode not in (0, 1) or have.stdout.strip() == driver:
            return                       # not a git repo (or no git), or already set
        subprocess.run(["git", "config", "--local", "merge.keepctx.name", "KeepCTX facts"],
                       cwd=root, capture_output=True)
        subprocess.run(["git", "config", "--local", "merge.keepctx.driver", driver],
                       cwd=root, capture_output=True)
    except OSError:
        pass                             # no git installed: nothing to set up


def render(facts):
    """The facts an agent reads: a heading per category, one line per fact."""
    by_cat = {}
    for full, value in sorted(facts.items()):
        cat, _, key = full.partition(".")
        by_cat.setdefault(cat, []).append(f"- **{key}** — {value}")
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


# --------------------------------------------------------------------- rules

RULES = """# KeepCTX — how to work with this project's context

This project's context is kept in KeepCTX: what it is, why, how it is built and
run, what has been decided, and what is still open. It outlasts this session,
and every AI and every person on the project reads the same facts. Use it, and
keep it current as you work. The context itself is printed after these rules.

## Every session

1. **You just ran `ctx ai`.** Everything known about this project is printed
   below these rules. Read it before you start.
2. **`ctx remember` the moment you learn something worth keeping** (see below).
3. **It lives in git.** The facts are in `{path}`, which is committed with the
   code, so teammates get them when they pull. When you commit your work,
   include changes to it like any other file.

Work through the `ctx` command, not the file. Git merges it fact by fact, so
different people changing different facts never conflict. The one exception:
if git reports a conflict in `{path}`, both sides changed the same fact. Keep
the line that is right, delete the markers, and commit as usual.

## Commands

| Command | When |
|---|---|
| `ctx ai` | the start of every session — you just ran it |
| `ctx get` | to read the whole context again |
| `ctx remember <category> <key> "<value>"` | the moment you learn something worth keeping |
| `ctx forget <category> <key>` | when a fact is wrong or gone, or a question is settled |

## Tell the user

Every line `ctx` prints that starts with `KeepCTX:` is for the user too. Repeat
it in your reply, as it was printed, so they always see what is kept:

    KeepCTX: remembered environments.server-a.ip — 10.0.4.12

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

- **Secrets** — passwords, tokens, keys, not even part of one. This file is
  committed to git. `ctx` refuses anything shaped like a credential.
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


def rules():
    """The agent's instructions, made fresh on every `ctx ai` from the installed
    CLI — so they can never go stale, and upgrading is just reinstalling."""
    cats = "\n".join(f"- **{slug}** — {desc}" for slug, _, desc in CATEGORIES)
    return RULES.format(categories=cats, path=f"{CTXDIR}/{CONTEXT}")


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
    f"No `ctx` command here? Carry on without it, and don't flag it — it may not be installed\n"
    f"on this machine. To set it up, install ctx from https://keepctx.com.\n"
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
    if not root:
        err("error: no context here. Run `ctx init` in your project first.")
    return root


def cmd_init(argv):
    here = pathlib.Path.cwd().resolve()
    if CTXDIR in here.parts:
        err(f"error: {here} is inside KeepCTX's own {CTXDIR}/ directory.")
        return 1
    ctxdir = here / CTXDIR
    fresh = not (ctxdir / CONTEXT).exists()
    ctxdir.mkdir(exist_ok=True)
    # earlier versions kept .ctx/ out of git; now it's meant to be committed
    stale = [p for p in (ctxdir / ".gitignore", ctxdir / "config.json") if p.exists()]
    for p in stale:
        p.unlink()
    if fresh:
        old = ctxdir / "context.json"      # 0.3 kept facts here, with times
        carried = {}
        if old.exists():
            try:
                carried = {k: f["value"] for k, f in json.loads(old.read_text())["facts"].items()
                           if not f.get("removed")}
                old.unlink()
                stale.append(old)
            except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
                carried = {}
        save(here, carried)
    changed = write_pointer(here)
    setup_git(here)
    if fresh:
        print(f"Initialized KeepCTX in {here.name}")
        print(f"  {CTXDIR}/{CONTEXT}  the context — commit it with your code")
        print(f"  {AGENTS}            pointer at the top: your AI starts with `ctx ai`")
    else:
        cmd_status()
    if stale:
        print(f"Removed {', '.join(p.name for p in stale)} from {CTXDIR}/ — it's committed now.")
    if fresh or changed:
        print()
        print(reread())
    return 0


def cmd_ai(argv):
    """Where an agent starts, named in AGENTS.md: the rules, then the whole
    context — the session start in one command."""
    root = find_root()
    if not root:
        say("no context here — carry on without it.")
        return 0
    setup_git(root)
    print(rules())
    return cmd_get([])


def cmd_get(argv):
    root = here_or_fail()
    if not root:
        return 1
    facts = load(root)
    print(f"# {root.name} — {plural(len(facts), 'fact')}")
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


def cmd_remember(argv):
    got = parse_fact_args(argv, need_value=True)
    if not got:
        if got is None:
            err('error: usage: ctx remember <category> <key> "<value>"')
        return 1
    cat, key, value = got
    root = here_or_fail()
    if not root:
        return 1
    what = find_secret(value)
    if what:
        err(f"error: not remembered — that looks like {what}. Secrets never go in a context:")
        err("       it's committed to git. Remember where the secret is kept instead.")
        return 1
    value = " ".join(value.split())        # one line, always
    full = f"{cat}.{key}"
    facts = load(root)
    before = facts.get(full)
    if before == value:
        say(f"already remembered {full} — {value}")
        return 0
    facts[full] = value
    save(root, facts)
    say(f"{'updated' if before is not None else 'remembered'} {full} — {value}")
    return 0


def cmd_forget(argv):
    got = parse_fact_args(argv, need_value=False)
    if not got:
        if got is None:
            err("error: usage: ctx forget <category> <key>")
        return 1
    cat, key, _ = got
    root = here_or_fail()
    if not root:
        return 1
    full = f"{cat}.{key}"
    facts = load(root)
    if full not in facts:
        say(f"nothing to forget — no {full}")
        return 0
    del facts[full]
    save(root, facts)
    say(f"forgot {full}")
    return 0


def cmd_status(with_usage=False):
    root = find_root()
    piped = not sys.stdout.isatty()   # a hook or an agent is reading, not a person
    if not root:
        return 0 if piped else usage()
    count = len(load(root))
    if piped:
        print(f"Context: {root.name} ({plural(count, 'fact')}). Start with `ctx ai`.")
        return 0
    print(f"KeepCTX {VERSION}")
    print(f"  context   {root / CTXDIR / CONTEXT}")
    print(f"  facts     {count}")
    if with_usage:
        print()
        usage()
    return 0


def usage():
    """For people. The agent's commands and rules come from `ctx ai`."""
    print("KeepCTX — keep one context. Every session, every AI, every teammate.")
    print()
    print("  ctx init    set up here; commit .ctx/ with your code to share it")
    print("  ctx get     see everything in it")
    print()
    print("Your AI starts with `ctx ai` — run it yourself to see what it's told.")
    return 0


COMMANDS = {"ai": cmd_ai, "get": cmd_get, "remember": cmd_remember, "forget": cmd_forget,
            "git-merge": cmd_git_merge}       # called by git, not by people


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
