"""The CLI end to end, against the real handler served locally.

Covers a local context (remember, forget, get, ai, AGENTS.md), sharing it,
two copies of one context kept in step by newest-wins (including a removal and
an edit made in the console), clone joining a local context of the same name,
the one-context-per-directory rule, a read-only member, and a sign-in that
expired."""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time

from fakes import call, fresh, serve

CTX = str(pathlib.Path(__file__).resolve().parent.parent / "src" / "keepctx.py")
fresh()
URL, stop = serve()
fails = 0


def check(label, cond, detail=""):
    global fails
    print(("PASS " if cond else "FAIL ") + label + ("" if cond else f"\n     -> {detail}"))
    fails += 0 if cond else 1


def ctx(cwd, *args, typed=""):
    r = subprocess.run([sys.executable, CTX, *args], cwd=cwd, input=typed, text=True,
                       capture_output=True, env={**os.environ, "CTX_REMOTE": URL})
    return r.stdout + r.stderr


def facts(d):
    return json.loads((pathlib.Path(d) / ".ctx" / "context.json").read_text())["facts"]


def value(d, key):
    f = facts(d).get(key)
    return None if f is None or f["removed"] else f["value"]


def cfg(d):
    return json.loads((pathlib.Path(d) / ".ctx" / "config.json").read_text())


def tick():
    time.sleep(0.01)      # timestamps are to the millisecond


def signup(email, org=None):
    tok = call("POST", "/v1/auth/register", {"email": email, "password": "password1"})[1]["token"]
    if org:
        call("POST", "/v1/orgs", {"org": org}, token=tok)
    return tok


owner = signup("owner@x.com", "team")
signup("member@x.com")
call("POST", "/v1/orgs/team/members", {"email": "member@x.com"}, token=owner)
tmp = pathlib.Path(tempfile.mkdtemp())
A, B, C, J, L = (tmp / x for x in "abcjl")
for d in (A, B, C, J, L):
    d.mkdir()
me = "owner@x.com\npassword1\n"

# ------------------------------------------------------------------ local
ctx(L, "init", "solo")
check("init: one JSON file is the context", (L / ".ctx" / "context.json").exists()
      and not list((L / ".ctx").glob("*.md")) and facts(L) == {})
check("init: the AGENTS.md pointer says to start with ctx ai", "`ctx ai`" in (L / "AGENTS.md").read_text())

out = ctx(L, "remember", "environments", "server-a.ip", "10.0.4.12")
check("remember: says what it kept", out.strip() == "KeepCTX: remembered environments.server-a.ip — 10.0.4.12", out)
f = facts(L)["environments.server-a.ip"]
check("remember: a fact is a value and a time", f["value"] == "10.0.4.12" and f["updated"].endswith("Z")
      and f["removed"] is False, f)
ctx(L, "remember", "architecture.api.depends-on", "auth-service, for sessions")
out = ctx(L, "get")
check("get: facts appear under their category", "## Environments\n\n- **server-a.ip** — 10.0.4.12" in out, out)
check("get: the category.key form works too", "- **api.depends-on** — auth-service, for sessions" in out, out)
out = ctx(L, "remember", "environments", "server-a.ip", "10.0.4.12")
check("remember: the same value again changes nothing", "already remembered" in out, out)
out = ctx(L, "remember", "stuff", "x", "y")
check("remember: an unknown category is refused, with the list", "isn't a category" in out and "environments" in out, out)
out = ctx(L, "remember", "environments", "aws.key", "AKIA" + "ABCDEFGHIJKLMNOP")
check("remember: a secret is refused, and not written",
      "Secrets never" in out and "environments.aws.key" not in facts(L), out)
out = ctx(L, "forget", "environments", "server-a.ip")
check("forget: the key stays, marked removed, and get hides it",
      "forgot environments.server-a.ip" in out and facts(L)["environments.server-a.ip"]["removed"]
      and "server-a" not in ctx(L, "get"), out)
ai = ctx(L, "ai")
check("ai: prints the rules, then the context",
      ai.index("how to work with this project's context") < ai.index("# solo —"), ai)
check("ai: a local context's rules have no sync steps", "local only" in ai and "It pulled" not in ai, ai)
check("ai: tells the agent to leave existing facts alone", "Leave existing facts alone" in ai, ai)
out = ctx(L, "pull")
check("pull: a local-only context says so", "local only" in out, out)
out = ctx(tmp, "ai")
check("ai: no context here says carry on", "carry on without it" in out, out)

# ------------------------------------------------------- share, two copies
ctx(A, "init", "proj")
ctx(A, "remember", "operations", "deploy.command", "`make ship`")
out = ctx(A, "remote", typed=me + "\n")
check("remote: goes live and says what it pushed", "team:proj is live" in out and "pushed 1 fact" in out, out)

out = ctx(A, "remember", "environments", "logs.location", "Splunk")
check("remember: with a server, it pushes straight away", "pushed 1 change" in out, out)

out = ctx(B, "clone", "team:proj", typed=me)
check("clone: into an empty directory", "cloned team:proj" in out and value(B, "environments.logs.location") == "Splunk", out)
check("clone: writes the AGENTS.md pointer", (B / "AGENTS.md").exists())

# both copies change things; every fact settles on its most recent change
tick()
ctx(A, "remember", "testing", "command", "`make test`")
tick()
out = ctx(B, "remember", "operations", "deploy.command", "`make release`")
check("newest wins: a push also brings in what the other copy changed",
      "pushed 1 change" in out and "pulled 1 new" in out and value(B, "testing.command") == "`make test`", out)
out = ctx(A, "pull")
check("newest wins: pull takes the newer value", "1 updated" in out
      and value(A, "operations.deploy.command") == "`make release`", out)

tick()
ctx(B, "forget", "environments", "logs.location")
out = ctx(A, "pull")
check("removal: reaches the other copy", "1 removed" in out and value(A, "environments.logs.location") is None, out)
out = ctx(A, "push")
check("removal: an older copy doesn't bring it back", "nothing new to push" in out
      and value(B, "environments.logs.location") is None, out)

# a person edits in the console; the next pull brings it in
tick()
call("POST", "/v1/contexts/team/proj/facts", {"key": "people.owner", "value": "Jason"}, token=owner)
out = ctx(A, "ai")
check("console edit: ctx ai pulls it in first", out.startswith("KeepCTX: pulled") and "1 new" in out
      and "- **owner** — Jason" in out, out)

# ------------------------------------- clone into a local context, same name
ctx(J, "init", "proj")
ctx(J, "remember", "knowledge", "local-only", "kept")
out = ctx(J, "clone", "team:proj", typed=me)
check("clone: joins a local context of the same name and says so",
      "joined your local `proj`" in out and value(J, "people.owner") == "Jason"
      and value(J, "knowledge.local-only") == "kept", out)
view = call("GET", "/v1/contexts/team/proj", token=owner)[1]["facts"]
check("clone: the local facts reach the server", "knowledge.local-only" in view, view)
out = ctx(J, "clone", "team:other", typed=me)
check("one context per directory: a different one is refused", "One context per directory" in out, out)
ctx(L, "init", "solo")
out = ctx(L, "clone", "team:proj", typed=me)
check("one context per directory: a different local name is refused", "local context, `solo`" in out, out)

# ------------------------------------------------------- member, read-only
out = ctx(C, "clone", "team:proj", typed="member@x.com\npassword1\n")
check("member: clone is read-only", "Read-only" in out and cfg(C)["readonly"], out)
check("member: ctx ai says don't change it", "Don't change it" in ctx(C, "ai"))
out = ctx(C, "remember", "knowledge", "x", "y")
check("member: remember is refused", "read-only" in out, out)

# an expired sign-in: an agent is told what to do, and ctx ai still works
conf = cfg(C)
conf["token"] = "expired.token.value"
(C / ".ctx" / "config.json").write_text(json.dumps(conf))
out = ctx(C, "pull")
check("expired: an agent is told to sign in from a terminal", "Run `ctx pull` in a terminal" in out, out)
out = ctx(C, "ai")
check("expired: ctx ai works from the local copy", "working from the local copy" in out and "# proj" in out, out)

out = ctx(A)
check("agent index: points at ctx ai", "ctx ai" in out, out)

# an older pointer is replaced; nothing else in AGENTS.md is touched
E = tmp / "e"
E.mkdir()
(E / "AGENTS.md").write_text("<!-- ctx -->\nold words\n<!-- /ctx -->\n\n# Mine\nkeep me\n")
ctx(E, "init", "fresh")
agents = (E / "AGENTS.md").read_text()
check("pointer: an old one is replaced, the rest kept",
      "old words" not in agents and "`ctx ai`" in agents and agents.endswith("# Mine\nkeep me\n"), agents)

stop()
print(f"\n{fails} failed")
sys.exit(1 if fails else 0)
