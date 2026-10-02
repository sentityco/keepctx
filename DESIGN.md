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

**Capture a wide net, distilled — never the conversation.** Goals, requirements, decisions with
their reasons, rejected options, open questions, corrections, and how things are built and
run. Musing is not deciding: an idea still being weighed is a question. Never secrets, never
what the user puts off the record.

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

**Shared through git, optionally.** Committing `KEEPCTX.md` gives teammates and their agents the same
context, with history, review and revert. Git merges it like any other file; the one common
conflict — two people adding a fact at the same spot — is answered in the rules: keep both.
