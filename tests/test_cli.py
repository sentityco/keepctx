"""The CLI end to end, against the real handler served locally.

Covers local facts (remember, forget, get, categories, an old file), a remote
the owner keeps from two copies (every write pushed, fact-by-fact merge on pull,
a conflict settled by the agent, deletions travelling), a member's read-only
copy, a reference clone beside a context, and an expired sign-in."""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

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


def facts(d, name):
    return (pathlib.Path(d) / ".ctx" / name / "facts.md").read_text()


def cfg(d):
    return json.loads((pathlib.Path(d) / ".ctx" / "config.json").read_text())


def signup(email, org=None):
    tok = call("POST", "/v1/auth/register", {"email": email, "password": "password1"})[1]["token"]
    if org:
        call("POST", "/v1/orgs", {"org": org}, token=tok)
    return tok


owner = signup("owner@x.com", "team")
signup("member@x.com")
call("POST", "/v1/orgs/team/members", {"email": "member@x.com"}, token=owner)
tmp = pathlib.Path(tempfile.mkdtemp())
A, B, C, D, L, O = (tmp / x for x in "abcdlo")
for d in (A, B, C, D, L, O):
    d.mkdir()
me = "owner@x.com\npassword1\n"

# ------------------------------------------------------------------ local
ctx(L, "init", "solo")
f = facts(L, "solo")
check("init: facts.md has a heading per category", "## Environments" in f and "## Decisions" in f, f)
check("init: no instructions file — the rules come from ctx ai",
      not (L / ".ctx" / "instructions.md").exists())
agents = (L / "AGENTS.md").read_text()
check("init: the AGENTS.md pointer says to start with ctx ai", "`ctx ai`" in agents, agents)
ai = ctx(L, "ai")
check("ai: prints the rules, then the context",
      ai.index("how to work with this project's context") < ai.index("# solo —") and "ctx remember" in ai, ai)
check("ai: a local context's rules have no sync steps", "It pulled" not in ai and "local only" in ai, ai)
check("ai: every command and when to use it", all(c in ai for c in
      ("`ctx get --remote`", "`ctx forget", "`ctx pull`", "`ctx push`")), ai)
out = ctx(L)
check("people: plain ctx is short, and points at ctx ai",
      "ctx ai" in out and "remember" not in out, out)
out = ctx(tmp, "ai")
check("ai: no context here says carry on", "carry on without it" in out, out)

out = ctx(L, "remember", "environments", "server-a.ip", "10.0.4.12")
check("remember: says what it kept", out.strip() == "KeepCTX: remembered environments.server-a.ip — 10.0.4.12", out)
ctx(L, "remember", "architecture.api.depends-on", "→ auth-service, for sessions")
out = ctx(L, "get")
check("get: facts appear under their category",
      "## Environments\n\n- **server-a.ip** — 10.0.4.12" in out, out)
check("get: a → value is a relationship", "- **api.depends-on** → auth-service, for sessions" in out, out)
check("get: empty categories are left out, and listed at the end",
      "## Testing" not in out and "Categories: overview" in out, out)
out = ctx(L, "remember", "environments", "server-a.ip", "10.0.4.13")
check("remember: an existing key is updated, not doubled",
      "updated" in out and facts(L, "solo").count("server-a.ip") == 1, out)
out = ctx(L, "remember", "stuff", "x", "y")
check("remember: an unknown category is refused, with the list", "isn't a category" in out and "environments" in out, out)
out = ctx(L, "remember", "environments", "aws.key", "AKIA" + "ABCDEFGHIJKLMNOP")
check("remember: a secret is refused, and not written", "Secrets never" in out and "aws.key" not in facts(L, "solo"), out)
out = ctx(L, "forget", "environments", "server-a.ip")
check("forget: removes the fact", "forgot environments.server-a.ip" in out and "server-a" not in facts(L, "solo"), out)
out = ctx(L, "pull")
check("pull: a local-only context says so", "local only" in out, out)
out = ctx(L, "sync")
check("sync: tells you what replaced it", "ctx pull" in out and "ctx push" in out, out)

# a file from before categories still reads, sorted into categories
ctx(O, "init", "old")
(O / ".ctx" / "old" / "facts.md").write_text(
    "# old\n\n- **decision.storage** — SQLite\n- **deploy.command** — `make ship`\n")
out = ctx(O, "get")
check("old file: decision.* lands under Decisions",
      "## Decisions\n\n- **storage** — SQLite" in out and "## Knowledge\n\n- **deploy.command**" in out, out)

# ------------------------------------------------------- owner, two copies
ctx(A, "init", "proj")
ctx(A, "remember", "operations", "deploy.command", "`make ship`")
out = ctx(A, "remote", typed=me + "\n")
check("remote: goes live and says what it pushed", "team:proj is live" in out and "pushed 1 facts" in out, out)
out = ctx(A, "ai")
check("ai: with a remote, it pulls first and the rules gain the sync steps",
      out.startswith("KeepCTX: pulled") and "It pulled the latest" in out, out)

out = ctx(A, "remember", "environments", "logs.location", "Splunk, index app_prod")
check("remember: with a remote, it pushes straight away", "pushed 2 facts" in out and "(v2)" in out, out)

out = ctx(B, "clone", "team:proj", typed=me)
check("clone: the owner's second copy is writable", "You maintain it" in out and not cfg(B)["readonly"], out)
check("clone: it has the facts", "Splunk" in facts(B, "proj"))

# both copies write different facts: the second push finds the server moved on,
# pulls, merges and pushes — no conflict, nothing for the agent to do
ctx(A, "remember", "testing", "command", "`make test`")
out = ctx(B, "remember", "people", "owner", "Jason")
check("merge: a stale push pulls, merges and pushes by itself",
      "moved on" in out and "1 added from the server" in out and "pushed 4 facts" in out, out)
out = ctx(A, "pull")
check("merge: pull brings in the other copy's fact", "1 added from the server" in out
      and "Jason" in facts(A, "proj"), out)
check("pull: each download is kept by version", (A / ".ctx" / "proj" / "remote" / "v4.md").exists())

# both copies change the same fact differently: a conflict the agent settles
ctx(A, "remember", "operations", "deploy.command", "`make release`")
out = ctx(B, "remember", "operations", "deploy.command", "`make publish`")
check("conflict: reported, not pushed", "1 conflict to settle: operations.deploy.command" in out
      and "pushed" not in out.split("conflict")[1], out)
check("conflict: the local value stays until settled", "make publish" in facts(B, "proj"))
out = ctx(B, "push")
check("conflict: push refuses until it's settled", "not pushed" in out, out)
out = ctx(B, "get", "--remote")
check("conflict: get --remote shows the server's side", "make release" in out, out)
out = ctx(B, "get")
check("conflict: get lists what's unsettled", "Unsettled conflicts: operations.deploy.command" in out, out)
out = ctx(B, "remember", "operations", "deploy.command", "`make release`, then tag")
check("conflict: remembering the fact settles it and pushes", "pushed" in out and not cfg(B)["conflicts"], out)
ctx(A, "pull")
check("conflict: the settled value reaches the other copy", "then tag" in facts(A, "proj"))

# deletions travel; a merge never brings a forgotten fact back
ctx(A, "forget", "environments", "logs.location")
out = ctx(B, "pull")
check("forget: a deletion reaches the other copy", "1 removed from the server" in out
      and "Splunk" not in facts(B, "proj"), out)
out = ctx(B, "push")
check("push: nothing new says so", "nothing new to push" in out, out)

# ------------------------------------------------------- member, read-only
out = ctx(C, "clone", "team:proj", typed="member@x.com\npassword1\n")
check("member: clone is read-only", "Read-only" in out and cfg(C)["readonly"], out)
check("member: ctx ai says don't change it", "Don't change it" in ctx(C, "ai"))
out = ctx(C, "remember", "knowledge", "x", "y")
check("member: remember is refused", "read-only" in out, out)
ctx(A, "remember", "people", "oncall", "#ops-oncall")
out = ctx(C, "pull")
check("member: pull brings in the owner's update", "ops-oncall" in facts(C, "proj"), out)

# ---------------------------------------------- a reference beside a context
ctx(D, "init", "other")
out = ctx(D, "clone", "team:proj", typed=me)
check("beside: clone next to an existing context", "beside `other`" in out and cfg(D)["name"] == "other", out)
out = ctx(D, "get")
check("beside: get shows it after the context's own facts", "# proj" in out and "read-only" in out, out)

# an expired sign-in: an agent gets told what to do instead of a raw 401
conf = cfg(C)
conf["token"] = "expired.token.value"
(C / ".ctx" / "config.json").write_text(json.dumps(conf))
out = ctx(C, "pull")
check("expired: an agent is told to sign in from a terminal", "Run `ctx pull` in a terminal" in out, out)

out = ctx(A)
check("agent index: points at ctx ai", "ctx ai" in out and "changed" not in out, out)
out = ctx(C, "ai")
check("ai: can't pull, still works from the local copy", "working from the local copy" in out
      and "# proj" in out, out)

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
