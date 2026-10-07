"""The CLI: `keepctx init` makes KEEPCTX.md and points AGENTS.md at it."""
import pathlib
import subprocess
import sys
import tempfile

KEEPCTX = str(pathlib.Path(__file__).resolve().parent.parent / "src" / "keepctx.py")
fails = 0


def check(label, cond, detail=""):
    global fails
    print(("PASS " if cond else "FAIL ") + label + ("" if cond else f"\n     -> {detail}"))
    fails += 0 if cond else 1


def keepctx(cwd, *args):
    r = subprocess.run([sys.executable, KEEPCTX, *args], cwd=cwd, text=True, capture_output=True)
    return r.returncode, r.stdout + r.stderr


tmp = pathlib.Path(tempfile.mkdtemp())
P = tmp / "proj"
P.mkdir()

code, out = keepctx(P, "init")
f = P / "KEEPCTX.md"
check("init: creates KEEPCTX.md", code == 0 and f.exists() and "Created" in out, out)
text = f.read_text()
check("context: the rules are at the top", text.startswith("# Project Context")
      and text.index("How to keep this file") < text.index("## Facts"), text)
check("context: one Facts list, no category headings",
      text.endswith("\n## Facts\n") and "## Overview" not in text and "## Decisions" not in text, text)
# the six goals, in order
check("1. read it before the first reply of any kind",
      "before your first reply of any\n  kind" in text, text)
check("2. say it was read, with the fact count", "KeepCTX: KEEPCTX.md read (N facts)" in text, text)
check("3. empty: offer to fill from the AI's own context, in the same reply, write only what's approved",
      "If it's empty, offer to fill it in that same reply" in text
      and "your own memory and instruction files" in text and "approves" in text, text)
check("4. keep writing all session, checked before every reply ends",
      "Keep writing all session" in text and "Before you finish *every* reply" in text, text)
check("5. more context beats less, with typical examples marked as not complete",
      "More context beats less" in text and "When you're unsure whether something belongs,\n  keep it" in text
      and "Typical things worth keeping — not a complete list" in text and "rejected.<name>" in text, text)
check("5. always keep answers to questions and costly wrong assumptions",
      "whenever you had to ask what a term" in text and "whenever a wrong assumption cost you" in text, text)
check("6. tell the user every time, naming the file when there's more than one",
      "Tell the user every time" in text and "KeepCTX: added — storage: SQLite" in text
      and "KeepCTX: added to ../KEEPCTX.md — storage" in text, text)
check("standing facts, not a session log", "Write standing facts, not a session log" in text, text)
check("never secrets", "**Never** write secrets" in text, text)
agents = (P / "AGENTS.md").read_text()
check("init: AGENTS.md points at it, marked KeepCTX", "`KEEPCTX.md`" in agents
      and agents.startswith("<!-- KeepCTX -->"), agents)
check("pointer: if the file is missing, carry on", "is missing,\nignore" in agents, agents)
check("pointer: read it before the next reply", "Read it before your next reply of any\nkind" in agents, agents)

f.write_text(text + "- **owner** — Jason\n")
code, out = keepctx(P, "init")
check("init again: leaves the context alone", "already here" in out and "Jason" in f.read_text(), out)
check("init again: AGENTS.md unchanged", (P / "AGENTS.md").read_text() == agents)

E = tmp / "e"
E.mkdir()
(E / "AGENTS.md").write_text("<!-- KeepCTX -->\nold words\n<!-- /KeepCTX -->\n\n# Mine\nkeep me\n")
keepctx(E, "init")
agents = (E / "AGENTS.md").read_text()
check("pointer: brought up to date in place, the rest kept",
      "old words" not in agents and "`KEEPCTX.md`" in agents and agents.endswith("# Mine\nkeep me\n"), agents)

code, out = keepctx(P)
check("usage: one command, keepctx init", "keepctx init" in out and "remember" not in out, out)
code, out = keepctx(P, "remember")
check("usage: anything else is unknown", code == 1 and "unknown command" in out, out)

print(f"\n{fails} failed")
sys.exit(1 if fails else 0)
