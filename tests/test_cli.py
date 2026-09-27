"""The CLI end to end, against the real handler served locally.

Covers the owner's copies (writable, merged per key, deletions travel), a
member's copy (read-only, refreshed by sync), a clone beside an existing
context, and an expired sign-in."""
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


def add(d, name, line):
    p = pathlib.Path(d) / ".ctx" / name / "facts.md"
    p.write_text(p.read_text().rstrip() + "\n" + line + "\n")


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
A, B, C, D = (tmp / x for x in "abcd")
for d in (A, B, C, D):
    d.mkdir()
me = "owner@x.com\npassword1\n"

# the owner puts a context on the remote
ctx(A, "init", "proj")
add(A, "proj", "- **deploy.command** — `make ship`")
out = ctx(A, "remote", typed=me + "\n")
check("owner: ctx remote puts it live", "team:proj is live" in out, out)

# the owner's second copy is writable, and the two merge
out = ctx(B, "clone", "team:proj", typed=me)
check("owner: clone elsewhere is writable", "You maintain it" in out and not cfg(B)["readonly"], out)
check("owner: the clone has the facts", "make ship" in facts(B, "proj"))
check("owner: the clone got an AGENTS.md pointer", (B / "AGENTS.md").exists())
add(A, "proj", "- **logs.location** — Splunk")
add(B, "proj", "- **api.runs-on** → Cloud Foundry")
ctx(A, "sync")
ctx(B, "sync")
ctx(A, "sync")
check("owner: different facts from two copies both land",
      "Splunk" in facts(B, "proj") and "Cloud Foundry" in facts(A, "proj"),
      facts(A, "proj") + "\n---\n" + facts(B, "proj"))
p = A / ".ctx" / "proj" / "facts.md"
p.write_text("\n".join(l for l in p.read_text().splitlines() if "logs.location" not in l) + "\n")
ctx(A, "sync")
out = ctx(B, "sync")
check("owner: a deletion in one copy reaches the other", "Splunk" not in facts(B, "proj"), out)

# a member's copy is read-only, and sync keeps it current
out = ctx(C, "clone", "team:proj", typed="member@x.com\npassword1\n")
check("member: clone is read-only", "Read-only" in out and cfg(C)["readonly"], out)
instr = (C / ".ctx" / "instructions.md").read_text()
check("member: the agent is told not to edit", "Don't edit it" in instr)
add(A, "proj", "- **oncall** — #ops-oncall")
ctx(A, "sync")
add(C, "proj", "- **local.scribble** — mine")
out = ctx(C, "sync")
check("member: sync brings in the owner's update", "ops-oncall" in facts(C, "proj"), out)
check("member: local edits are replaced, not sent", "scribble" not in facts(C, "proj"), out)
out = ctx(C)
check("member: the agent's index says read-only", "read-only" in out, out)

# beside an existing context, a clone is a reference, refreshed by sync
ctx(D, "init", "other")
out = ctx(D, "clone", "team:proj", typed=me)
check("beside: clone next to an existing context", "beside `other`" in out, out)
check("beside: the directory's own context is unchanged", cfg(D)["name"] == "other")
add(A, "proj", "- **runbook** — wiki/ops")
ctx(A, "sync")
out = ctx(D, "sync")
check("beside: sync refreshes it", "wiki/ops" in facts(D, "proj"), out)

# an expired sign-in: an agent gets told what to do instead of a raw 401
conf = cfg(C)
conf["token"] = "expired.token.value"
(C / ".ctx" / "config.json").write_text(json.dumps(conf))
out = ctx(C, "sync")
check("expired: an agent is told to sign in from a terminal", "Run `ctx sync` in a terminal" in out, out)

# plain `ctx` from an agent no longer claims AGENTS.md changed
out = ctx(A)
check("agent index: no false 'AGENTS.md changed'", "changed" not in out, out)

stop()
print(f"\n{fails} failed")
sys.exit(1 if fails else 0)
