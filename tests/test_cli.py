"""The CLI end to end: a context in one file in git.

Covers init and the AGENTS.md pointer, remember / forget / get / ai, the
secret check, and the reason the file is one fact per line: two clones of a
repo changing different facts merge in git without a conflict."""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

CTX = str(pathlib.Path(__file__).resolve().parent.parent / "src" / "keepctx.py")
fails = 0


def check(label, cond, detail=""):
    global fails
    print(("PASS " if cond else "FAIL ") + label + ("" if cond else f"\n     -> {detail}"))
    fails += 0 if cond else 1


def ctx(cwd, *args):
    r = subprocess.run([sys.executable, CTX, *args], cwd=cwd, text=True, capture_output=True)
    return r.stdout + r.stderr


def git(cwd, *args):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x"}
    r = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, env=env)
    return r.returncode, r.stdout + r.stderr


def lines(d):
    return (pathlib.Path(d) / ".ctx" / "context.jsonl").read_text().splitlines()


def facts(d):
    return {json.loads(x)["key"]: json.loads(x)["value"] for x in lines(d) if x.strip()}


tmp = pathlib.Path(tempfile.mkdtemp())
P = tmp / "proj"
P.mkdir()

# --------------------------------------------------------------- init
out = ctx(P, "init")
check("init: one committed file is the context", (P / ".ctx" / "context.jsonl").exists()
      and not (P / ".ctx" / ".gitignore").exists() and "commit it" in out, out)
check("init: the AGENTS.md pointer says to start with ctx ai", "`ctx ai`" in (P / "AGENTS.md").read_text())

# ------------------------------------------------- remember, forget, get
out = ctx(P, "remember", "environments", "server-a.ip", "10.0.4.12")
check("remember: says what it kept", out.strip() == "KeepCTX: remembered environments.server-a.ip — 10.0.4.12", out)
check("remember: one fact per line", lines(P) == ['{"key": "environments.server-a.ip", "value": "10.0.4.12"}'], lines(P))
ctx(P, "remember", "architecture.api.depends-on", "auth-service, for sessions")
ctx(P, "remember", "decisions", "storage", "SQLite")
check("save: lines are sorted by key", [json.loads(x)["key"] for x in lines(P)]
      == ["architecture.api.depends-on", "decisions.storage", "environments.server-a.ip"], lines(P))
out = ctx(P, "get")
check("get: facts appear under their category", "## Environments\n\n- **server-a.ip** — 10.0.4.12" in out, out)
check("get: the category.key form works too", "- **api.depends-on** — auth-service, for sessions" in out, out)
out = ctx(P, "remember", "environments", "server-a.ip", "10.0.4.12")
check("remember: the same value again changes nothing", "already remembered" in out, out)
out = ctx(P, "remember", "environments", "server-a.ip", "10.0.4.13")
check("remember: an existing key is updated, not doubled", "updated" in out and len(lines(P)) == 3, out)
out = ctx(P, "remember", "stuff", "x", "y")
check("remember: an unknown category is refused, with the list", "isn't a category" in out and "environments" in out, out)
out = ctx(P, "remember", "environments", "aws.key", "AKIA" + "ABCDEFGHIJKLMNOP")
check("remember: a secret is refused, and not written", "committed to git" in out
      and "environments.aws.key" not in facts(P), out)
out = ctx(P, "forget", "decisions", "storage")
check("forget: removes the line", "forgot decisions.storage" in out and "decisions.storage" not in facts(P), out)
out = ctx(P, "forget", "decisions", "storage")
check("forget: twice says there's nothing to forget", "nothing to forget" in out, out)

# ------------------------------------------------------------------ ai
ai = ctx(P, "ai")
check("ai: prints the rules, then the context",
      ai.index("how to work with this project's context") < ai.index("# proj —"), ai)
check("ai: says the context lives in git", "It lives in git" in ai and ".ctx/context.jsonl" in ai, ai)
check("ai: no server commands", all(c not in ai for c in ("ctx pull", "ctx push", "ctx remote", "ctx clone")), ai)
out = ctx(tmp, "ai")
check("ai: no context here says carry on", "carry on without it" in out, out)
for gone in ("remote", "clone", "pull", "push"):
    out = ctx(P, gone)
    check(f"{gone}: not a command", "unknown command" in out, out)
out = ctx(P, "--help")
check("people usage: init and get, and ctx ai", "ctx init" in out and "ctx get" in out
      and "ctx ai" in out and "remote" not in out, out)

# -------------------------------- git: different facts merge without a conflict
ORIGIN, A, B = tmp / "origin.git", tmp / "a", tmp / "b"
git(tmp, "init", "--bare", "-b", "main", str(ORIGIN))
git(tmp, "clone", str(ORIGIN), str(A))
ctx(A, "init")
ctx(A, "remember", "operations", "deploy.command", "`make ship`")
ctx(A, "remember", "people", "owner", "Jason")
git(A, "add", "-A")
git(A, "commit", "-m", "context")
git(A, "push", "origin", "HEAD:main")
git(tmp, "clone", str(ORIGIN), str(B))
check("git: a clone brings the context with it", facts(B).get("people.owner") == "Jason", facts(B))
check("git: the merge driver is named in a committed file",
      (B / ".ctx" / ".gitattributes").read_text() == "context.jsonl merge=keepctx\n")
ctx(B, "ai")                                  # each clone's git config gets the driver
check("git: ctx ai sets up the driver in this clone", "git-merge" in git(B, "config", "merge.keepctx.driver")[1])

ctx(A, "remember", "testing", "command", "`make test`")          # A adds one fact
ctx(A, "remember", "operations", "deploy.command", "`make release`")  # and changes another
git(A, "commit", "-am", "a")
git(A, "push", "origin", "HEAD:main")
ctx(B, "remember", "environments", "logs.location", "Splunk")      # B adds a different one
ctx(B, "forget", "people", "owner")                                 # and removes another
git(B, "commit", "-am", "b")
code, out = git(B, "pull", "--no-rebase", "origin", "main")
check("git: changes to different facts merge with no conflict", code == 0 and "CONFLICT" not in out, out)
f = facts(B)
check("git: every change from both sides lands",
      f.get("testing.command") == "`make test`" and f.get("operations.deploy.command") == "`make release`"
      and f.get("environments.logs.location") == "Splunk" and "people.owner" not in f, f)

git(B, "push", "origin", "HEAD:main")

# the same fact changed differently on both sides: only that fact conflicts
git(A, "pull", "--no-rebase", "origin", "main")
ctx(A, "remember", "testing", "command", "`make check`")
ctx(A, "remember", "people", "lead", "Jess")
git(A, "commit", "-am", "a2")
git(A, "push", "origin", "HEAD:main")
ctx(B, "remember", "testing", "command", "`make verify`")
git(B, "commit", "-am", "b2")
code, out = git(B, "pull", "--no-rebase", "origin", "main")
text = (B / ".ctx" / "context.jsonl").read_text()
check("conflict: same fact changed on both sides is a git conflict", code != 0 and "CONFLICT" in out, out)
check("conflict: only that fact is marked; the rest merged",
      text.count("<<<<<<<") == 1 and "make check" in text and "make verify" in text
      and '"people.lead"' in text and text.index('"people.lead"') < text.index("<<<<<<<"), text)
out = ctx(B, "get")
check("conflict: get reports the markers instead of dropping them", "git conflict" in out, out)

# an older pointer is replaced; nothing else in AGENTS.md is touched
E = tmp / "e"
E.mkdir()
(E / "AGENTS.md").write_text("<!-- ctx -->\nold words\n<!-- /ctx -->\n\n# Mine\nkeep me\n")
ctx(E, "init")
agents = (E / "AGENTS.md").read_text()
check("pointer: an old one is replaced, the rest kept",
      "old words" not in agents and "`ctx ai`" in agents and agents.endswith("# Mine\nkeep me\n"), agents)

# an earlier setup is made committable, and its facts carried over
O = tmp / "old"
(O / ".ctx").mkdir(parents=True)
(O / ".ctx" / ".gitignore").write_text("*\n")
(O / ".ctx" / "config.json").write_text("{}")
(O / ".ctx" / "context.json").write_text(json.dumps({"facts": {
    "decisions.x": {"value": "kept", "updated": "2026-10-01T10:00:00.000Z", "removed": False},
    "decisions.y": {"value": "gone", "updated": "2026-10-01T10:00:00.000Z", "removed": True}}}))
out = ctx(O, "init")
check("upgrade: .gitignore and config go, live facts carry over",
      not (O / ".ctx" / ".gitignore").exists() and facts(O) == {"decisions.x": "kept"}, out)

print(f"\n{fails} failed")
sys.exit(1 if fails else 0)
