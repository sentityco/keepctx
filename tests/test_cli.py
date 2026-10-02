"""The CLI: `ctx init` makes .ctx/context.md and points AGENTS.md at it."""
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
    return r.returncode, r.stdout + r.stderr


tmp = pathlib.Path(tempfile.mkdtemp())
P = tmp / "proj"
P.mkdir()

code, out = ctx(P, "init")
f = P / ".ctx" / "context.md"
check("init: creates .ctx/context.md", code == 0 and f.exists() and "Created" in out, out)
text = f.read_text()
check("context: the rules are at the top", text.startswith("# Project Context")
      and text.index("How to keep this file") < text.index("## Overview"), text)
check("context: every category has a heading and a description",
      all(f"## {h}" in text for h in ("Overview", "Decisions", "Questions", "People"))
      and "_What is still undecided" in text, text)
check("context: no secrets, and tell the user", "Never" in text and "KeepCTX: added to Decisions — storage: SQLite" in text, text)
agents = (P / "AGENTS.md").read_text()
check("init: AGENTS.md points at it", ".ctx/context.md" in agents, agents)

f.write_text(text + "- **owner** — Jason\n")
code, out = ctx(P, "init")
check("init again: leaves the context alone", "already here" in out and "Jason" in f.read_text(), out)
check("init again: AGENTS.md unchanged", (P / "AGENTS.md").read_text() == agents)

E = tmp / "e"
E.mkdir()
(E / "AGENTS.md").write_text("<!-- ctx -->\nold words\n<!-- /ctx -->\n\n# Mine\nkeep me\n")
ctx(E, "init")
agents = (E / "AGENTS.md").read_text()
check("pointer: an old one is replaced, the rest kept",
      "old words" not in agents and ".ctx/context.md" in agents and agents.endswith("# Mine\nkeep me\n"), agents)

code, out = ctx(P)
check("usage: one command", "ctx init" in out and "remember" not in out, out)
code, out = ctx(P, "remember")
check("usage: anything else is unknown", code == 1 and "unknown command" in out, out)

print(f"\n{fails} failed")
sys.exit(1 if fails else 0)
