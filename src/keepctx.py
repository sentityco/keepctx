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
working on the project reads it. **AI agents: read all of it before your next
reply of any kind, and keep it current as you work, by these rules.**

## How to keep this file

- **Read it before you reply.** Read this whole file before your next reply of
  any kind. Start that reply with one line: `KeepCTX: KEEPCTX.md read (N facts)`,
  where N is the number of `- **key** — value` lines under Facts below.
- **Fill an empty file.** If it has no facts yet, the *same reply* that reports
  `(0 facts)` must also offer to fill it — don't just report the count and stop.
  Offer to fill it from what you already know: this session, your own memory
  and instruction files, and the project itself (README, git history). List
  what you'd add and write only what the user approves, by the rules below.
  Someone may have emptied it on purpose.
- **One fact per line**, under Facts: `- **key** — value`. Keys are short and
  lowercase (`server-a.ip`, `deploy.command`). Values are one line that a
  newcomer would understand.
- **Write it down the moment you learn it** — a session can end at any time.
  Typical things worth keeping — not a complete list, use your judgment: goals
  and requirements the user states; decisions, once the user commits, with the
  reason; options turned down, as `rejected.<name>`, with why; open questions;
  corrections; how things are built, run, tested and deployed; hosts,
  environments and how to get access; conventions and what not to touch;
  gotchas and anything that took real effort to find out; who owns what.
- **If you have to ask what something is, write down the answer.** Any time you
  don't recognize a term, host, datasource or repo reference and the user
  explains it so you can proceed, add a fact for it before continuing — don't
  just use the answer and move on.
- **Check again before you stop, every reply, not just the first.** The
  start-of-reply read is not enough on its own — re-reading it doesn't keep it
  current, only writing does, and the task at hand will keep pulling your
  attention away from this file unless you deliberately check. Before you
  finish *any* reply — not just ones about this file — ask yourself: *did I
  learn, decide, reject, or get corrected on anything this turn that isn't in
  Facts yet?* If yes, add it in that same reply, before you stop, using the
  `KeepCTX: added/updated/removed — <key>` line. Don't defer it to "later" or
  to when the user asks explicitly — by then the session may already be over.
- **A costly wrong assumption is always a fact, no exceptions.** If something
  you assumed (a name, a location, a config value, which of two similar things
  was the right one) turned out to be wrong and it cost you two or more extra
  tool calls, a user correction, or a dead end to recover from — write down
  what was actually true the moment you find out, even if the user didn't ask
  you to and even if you're about to move on to something else. That cost is
  exactly the signal this file exists to capture: the next agent (or you,
  later) must not pay it twice.
- **This file is durable, project-level truth — not a session log.** Keep what
  a newcomer to the *project* would need, stated as a standing fact (what's
  true now), not a narrative of how you found it out or what you did this
  session. If something is genuinely one-off and not reusable, it probably
  doesn't belong here — but err toward keeping it if you're unsure, per the
  rule above.
- **Musing is not deciding.** "Maybe Postgres?" is a question, not a decision.
- **Change a fact by editing its line**, never by adding a second one. Delete a
  line when it's no longer true, and a question once a decision settles it.
- **Leave other facts alone** unless they're wrong or the user asks.
- **Never** write secrets (passwords, tokens, keys), anything the user says is
  off the record, opinions about people, or the conversation itself. This file
  is committed with the code.
- **Tell the user** in one line whenever you change this file, e.g.
  `KeepCTX: added — storage: SQLite` (or "updated", "removed").
  If you know of more than one `KEEPCTX.md`, name the file you changed:
  `KeepCTX: added to ../KEEPCTX.md — storage: SQLite`.
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
