#!/usr/bin/env python3
"""keepctx — keep one context. Every session, every AI, every teammate.

It does one thing: `keepctx init` creates KEEPCTX.md — a plain Markdown file
of facts, with the rules for keeping it at the top — and points AGENTS.md at
it. After that, nobody needs KeepCTX installed: agents read and edit the file
like any other, and it's shared through git with the rest of the code.
"""
import pathlib
import sys

VERSION = "0.9.0"

CONTEXT = "KEEPCTX.md"
AGENTS = "AGENTS.md"
BEGIN = "<!-- KeepCTX -->"
END = "<!-- /KeepCTX -->"

RULES = """# Project Context

This file is this project's memory: what it is, why, how it's built and run,
what has been decided, and what is still open. Every AI agent and every person
working on the project reads it. **AI agents: read all of it before your first
reply, and keep it current for the whole session, by these rules.**

## How to keep this file

- **Read it first.** Read this whole file before your first reply of any
  kind, even a one-line answer. Start that reply with one line:
  `KeepCTX: KEEPCTX.md read (N facts)`, where N is the number of
  `- **key** — value` lines under Facts below.
- **If it's empty, offer to fill it in that same reply.** With 0 facts, don't
  just report the count: list what you already know that belongs here — from
  your own memory and instruction files, this session, and the project itself
  (README, git history) — and offer to add it. Write only what the user
  approves; they may have emptied it on purpose.
- **Keep writing all session.** Add a fact the moment you learn it — a session
  can end at any time. Reading this file doesn't keep it current; only writing
  does. Before you finish *every* reply, not just the first, ask: *did I learn,
  decide, reject or get corrected on anything this turn that isn't in Facts
  yet?* If so, add it in that same reply. Don't wait for the user to ask.
- **More context beats less.** When you're unsure whether something belongs,
  keep it. Typical things worth keeping — not a complete list: goals and
  requirements; decisions, once the user commits, with the reason; options
  turned down, as `rejected.<name>`, with why; open questions; corrections;
  how things are built, run, tested and deployed; hosts, environments and how
  to get access; conventions and what not to touch; gotchas; who owns what.
  Always keep:
  - the answer, whenever you had to ask what a term, host, datasource or repo
    reference is;
  - what was actually true, whenever a wrong assumption cost you extra work, a
    dead end or a correction — the next agent must not pay for it twice.
- **Write standing facts, not a session log.** State what's true now, so a
  newcomer to the project would understand it — not how you found it out or
  what you did this session. "Maybe Postgres?" is an open question, not a
  decision.
- **One fact per line**, under Facts: `- **key** — value`. Keys are short and
  lowercase (`server-a.ip`, `deploy.command`); values are one line. Change a
  fact by editing its line, never by adding a second one. Delete a line when
  it's no longer true, and a question once it's settled. Leave other facts
  alone unless they're wrong or the user asks.
- **Tell the user every time** you change this file, in one line:
  `KeepCTX: added — storage: SQLite` (or "updated", "removed").
  If you know of more than one `KEEPCTX.md`, name the file you changed:
  `KeepCTX: added to ../KEEPCTX.md — storage: SQLite`.
- **Never** write secrets (passwords, tokens, keys), anything the user says is
  off the record, or opinions about people. This file is committed with the
  code.
- **A merge conflict here** almost always means both sides added facts: keep both.
"""


def template():
    return RULES + "\n## Facts\n"


POINTER = (
    f"{BEGIN}\n"
    f"This project's context is kept in `{CONTEXT}`. Read it before your next reply of any\n"
    f"kind, and keep it current as the rules at its top say. If `{CONTEXT}` is missing,\n"
    f"ignore this and carry on.\n"
    f"{END}\n"
)


def write_pointer(root):
    """At the top of AGENTS.md; nothing else in it is touched. If the pointer is
    already there, it's brought up to date. -> True if the file changed."""
    agents = root / AGENTS
    existing = agents.read_text() if agents.exists() else ""
    if BEGIN in existing and END in existing:
        start = existing.index(BEGIN)
        stop = existing.index(END, start) + len(END)
        updated = existing[:start] + POINTER.rstrip("\n") + existing[stop:]
    else:
        updated = POINTER + ("\n" + existing if existing else "")
    if updated == existing:
        return False
    agents.write_text(updated)
    return True


def cmd_init():
    root = pathlib.Path.cwd().resolve()
    path = root / CONTEXT
    created = not path.exists()
    if created:
        path.write_text(template())
    pointed = write_pointer(root)
    if created:
        print(f"Created {CONTEXT} — your project's context.")
    else:
        print(f"{CONTEXT} is already here.")
    if pointed:
        print(f"Added a pointer to it at the top of {AGENTS}.")
    if created or pointed:
        print("Start a new AI session, or tell your AI to re-read AGENTS.md.")
    return 0


def usage():
    print("KeepCTX — keep one context. Every session, every AI, every teammate.")
    print()
    print("  keepctx init    create KEEPCTX.md here and point AGENTS.md at it")
    print()
    print("That's the only command. From then on, your AI reads KEEPCTX.md at the")
    print("start of each session and adds what it learns.")
    print()
    print("Optional: commit KEEPCTX.md so teammates and their AI agents share it too —")
    print("they don't need KeepCTX installed.")
    return 0


def main():
    argv = sys.argv[1:]
    if argv[:1] == ["init"]:
        return cmd_init()
    if argv[:1] in (["-v"], ["--version"]):
        print(f"keepctx {VERSION}")
        return 0
    if argv and argv[0] not in ("-h", "--help", "help"):
        print(f"error: unknown command `{argv[0]}`", file=sys.stderr)
        usage()
        return 1
    return usage()


if __name__ == "__main__":
    sys.exit(main())
