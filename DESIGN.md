# KeepCTX — design

## What it is

A convention, and a one-command setup for it. `keepctx init` creates `KEEPCTX.md` — a plain
Markdown file of facts with the rules for keeping it at the top — and adds
a pointer to the top of `AGENTS.md` telling agents to read it before their next reply of any
kind and keep it current, or carry on if it's missing. That's the whole product.

## Decisions

**It has to work for someone who never installed it.** A teammate clones the repo; their agent
has no KeepCTX. So nothing in an agent's workflow depends on a command: agents read and edit the
file directly, and the rules travel inside it. The CLI only sets it up.

**`AGENTS.md` is the doorway, not the store.** It's the file most agents already read, and it
holds instructions people write. KeepCTX adds one pointer block there and touches nothing
else; the context itself lives in its own file. Running `keepctx init` again brings the pointer up
to date.

**One file at the root, named for what it is.** `KEEPCTX.md` sits beside `AGENTS.md` and
`README.md`, where people and agents see it. One file doesn't need a folder.

**If it's missing, carry on.** The pointer says so, so an agent never hunts for the file or
stops when someone has removed it or copied `AGENTS.md` without it.

**One Markdown file, one fact per line.** `- **key** — value`, in one list under `## Facts`.
Markdown because every agent and every person can read and edit it with nothing installed,
and it renders on GitHub.

**No categories.** There used to be eleven headings — Overview, Requirements, Architecture and
so on — each with a description of what belongs there. They were dropped: an AI already knows
what belongs in a project's context, the headings were written for software and fit a book or a
business badly, and a flat list leaves one less decision per fact. Keys like `prod.access` and
`rejected.postgres` group related facts well enough. What the categories did well — reminding an
agent of the kinds of things worth keeping — survives as a short list of typical examples in the
rules, marked as not complete so the agent still uses its judgment.

**More context beats less — distilled, never the conversation.** Goals, requirements, decisions
with their reasons, rejected options, open questions, corrections, and how things are built and
run. When unsure, keep it: a missing fact costs the next session far more than an extra line.
Each fact is stated as what's true now, not as a log of the session. Musing is not deciding: an
idea still being weighed is a question. Never secrets, never what the user puts off the record.

**Written as you go, checked before every stop.** Reading the file at the start of a reply
doesn't keep it current; only writing does, and the task pulls attention away from it. So the
rules ask the agent, before it finishes any reply, whether it learned, decided, rejected or was
corrected on anything not yet in Facts — and a wrong assumption that cost real effort to recover
from is always written down, so nobody pays for it twice.

**An empty file is filled by asking, not by dumping.** The first agent to meet an empty
`KEEPCTX.md` often already knows a lot — from the session, its own memory, the README and git
history — and that knowledge should move into the shared file. But it offers a list and writes
only what the person approves: an empty file may be a deliberate fresh start, an agent's memory
mixes personal preferences with project facts, and anything it writes gets committed.

**Tell the person.** The rules ask the agent to say in one line whenever it changes the file:
`KeepCTX: added — storage: SQLite`.

**Contexts inside contexts, left to the agent.** A `KEEPCTX.md` can sit in a folder below
another — a repo inside a team workspace — and an agent may read one or both. There are no
rules for which wins or where a fact goes: agents sort that out well, and the change line names
the file whenever there's more than one, so a fact in the wrong place is easy to spot.

**Updated by running init again.** Re-running the installer gets the latest `keepctx`, and
re-running `keepctx init` replaces everything above `## Facts` with the current rules, leaving
everything from `## Facts` down exactly as it was. The heading is the boundary, so files made
before there was an update path update the same way. The rules carry a version stamp so `init`
can say what changed. A file with no `## Facts` heading is left alone rather than guessed at.
One person runs it and commits; everyone else gets the new rules through git, still with
nothing installed. Fetching the rules from a URL at read time was turned down: it breaks
"nothing to install," fails offline, and agents don't reliably fetch.

**Shared through git, optionally.** Committing `KEEPCTX.md` gives teammates and their agents the same
context, with history, review and revert. Git merges it like any other file; the one common
conflict — two people adding a fact at the same spot — is answered in the rules: keep both.
