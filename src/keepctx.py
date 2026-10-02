#!/usr/bin/env python3
"""keepctx — keep one context. Every session, every AI, every teammate.

The command is `keepctx`. It does one thing: `keepctx init` creates `KEEPCTX.md` — a plain Markdown file of facts, with the
rules for keeping it at the top — and points AGENTS.md at it. After that,
nobody needs KeepCTX installed: agents read and edit the file like any other,
and it's shared through git with the rest of the code.
"""
import pathlib
import sys

VERSION = "0.7.0"

CONTEXT = "KEEPCTX.md"
AGENTS = "AGENTS.md"
BEGIN = "<!-- KeepCTX -->"
END = "<!-- /KeepCTX -->"
OLD_MARKERS = [("<!-- ctx -->", "<!-- /ctx -->")]      # earlier versions' pointer
OLD_CONTEXT = pathlib.Path(".ctx") / "context.md"      # where 0.5 kept the file

CATEGORIES = [
    ("Overview", "What this is, why it exists, who it's for, and what success looks like."),
    ("Requirements", "What it must and must not do, and what is in and out of scope."),
    ("Architecture", "Services, components, dependencies and data flows: what connects to what."),
    ("Environments", "Hosts, deployment environments, service names, versions and access. Never secrets."),
    ("Decisions", "What was chosen and why, and what was considered and rejected."),
    ("Questions", "What is still undecided. Deleted once a decision settles it."),
    ("Conventions", "Patterns future developers and agents should follow, and what not to touch."),
    ("Operations", "Build, deploy, runbooks, troubleshooting and recurring operational details."),
    ("Testing", "How to test, what passing means, and what is not covered."),
    ("Knowledge", "Gotchas, domain facts and vocabulary nobody outside would know."),
    ("People", "Who owns what, who to ask, and how they like to work."),
]

RULES = """# Project Context

This file is this project's memory: what it is, why, how it's built and run,
what has been decided, and what is still open. Every AI agent and every person
working on the project reads it. **AI agents: read all of it at the start of
every session, and keep it current as you work, by these rules.**

## How to keep this file

- **One fact per line**, under the heading it belongs to: `- **key** — value`.
  Keys are short and lowercase (`server-a.ip`, `deploy.command`). Values are one
  line that a newcomer would understand.
- **Write it down the moment you learn it** — a session can end at any time.
  Worth keeping: goals and requirements the user states; decisions, once the
  user commits, with the reason; options turned down, under Decisions as
  `rejected.<name>`, with why; open questions; corrections; anything that took
  real effort to find out; how things are built, run, tested and deployed.
- **Musing is not deciding.** "Maybe Postgres?" is a question, not a decision.
- **Change a fact by editing its line**, never by adding a second one. Delete a
  line when it's no longer true, and a question once a decision settles it.
- **Leave other facts alone** unless they're wrong or the user asks.
- **Never** write secrets (passwords, tokens, keys), anything the user says is
  off the record, opinions about people, or the conversation itself. This file
  is committed with the code.
- **Tell the user** in one line whenever you change this file, e.g.
  `KeepCTX: added to Decisions — storage: SQLite` (or "updated in", "removed from").
- **A merge conflict here** almost always means both sides added facts: keep both.
"""


def template():
    sections = "".join(f"\n## {title}\n_{desc}_\n" for title, desc in CATEGORIES)
    return RULES + sections


POINTER = (
    f"{BEGIN}\n"
    f"This project's context is kept in `{CONTEXT}`. Read it at the start of every session,\n"
    f"and keep it current as the rules at its top say. If `{CONTEXT}` is missing, ignore\n"
    f"this and carry on.\n"
    f"{END}\n"
)


def write_pointer(root):
    """At the top of AGENTS.md; nothing else in it is touched. An older pointer
    is replaced. -> True if the file changed."""
    agents = root / AGENTS
    existing = agents.read_text() if agents.exists() else ""
    for begin, end in [(BEGIN, END)] + OLD_MARKERS:
        if begin in existing and end in existing:
            start = existing.index(begin)
            stop = existing.index(end, start) + len(end)
            updated = existing[:start] + POINTER.rstrip("\n") + existing[stop:]
            break
    else:
        updated = POINTER + ("\n" + existing if existing else "")
    if updated == existing:
        return False
    agents.write_text(updated)
    return True


def cmd_init():
    root = pathlib.Path.cwd().resolve()
    path = root / CONTEXT
    old = root / OLD_CONTEXT
    moved = not path.exists() and old.exists()
    if moved:                      # one file at the root now, not a folder
        old.rename(path)
        try:
            old.parent.rmdir()     # only if nothing else is in it
        except OSError:
            pass
    created = not path.exists()
    if created:
        path.write_text(template())
    pointed = write_pointer(root)
    if created:
        print(f"Created {CONTEXT} — your project's context.")
    elif moved:
        print(f"Moved {OLD_CONTEXT} to {CONTEXT}.")
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
