# KeepCTX — design

## What it is

A convention, and a one-command setup for it. `ctx init` creates `.ctx/context.md` — a plain
Markdown file with the rules for keeping it at the top and a heading per category — and adds
a pointer to the top of `AGENTS.md` telling agents to read it at the start of every session
and keep it current. That's the whole product.

## Decisions

**It has to work for someone who never installed it.** A teammate clones the repo; their agent
has no `ctx`. So nothing in an agent's workflow depends on a command: agents read and edit the
file directly, and the rules travel inside it. The CLI only sets it up.

**`AGENTS.md` is the doorway, not the store.** It's the file most agents already read, and it
holds instructions people write. KeepCTX adds one pointer block there and touches nothing
else; the context itself lives in its own file. Running `ctx init` again replaces an older
pointer in place.

**One Markdown file, one fact per line.** `- **key** — value`, under one of eleven headings:
Overview, Requirements, Architecture, Environments, Decisions, Questions, Conventions,
Operations, Testing, Knowledge, People. Markdown because every agent and every person can
read and edit it with nothing installed, and it renders on GitHub. The categories are written
for software but read sensibly for a book, a business or a portfolio.

**Capture a wide net, distilled — never the conversation.** Goals, requirements, decisions with
their reasons, rejected options, open questions, corrections, and how things are built and
run. Musing is not deciding: an idea still being weighed is a question. Never secrets, never
what the user puts off the record.

**Tell the person.** The rules ask the agent to say in one line whenever it changes the file:
`KeepCTX: added to Decisions — storage: SQLite`.

**Shared through git, optionally.** Committing `.ctx/` gives teammates and their agents the same
context, with history, review and revert. Git merges it like any other file; the one common
conflict — two people adding a fact at the same spot — is answered in the rules: keep both.

## Tried and dropped

KeepCTX went through several larger designs before this one: a sync server with accounts, orgs,
a web console and self-hosting; agent commands (`ctx ai`, `remember`, `forget`, `pull`,
`push`); a three-way merge with AI-settled conflicts, then newest-wins timestamps; JSON
storage with a fact-by-fact git merge driver; a secret check; a journal and agent-written
prose; relationship facts drawn as a diagram.

Each worked. Each either needed the tool installed on every machine, or solved a problem no
user had reported yet. The server version is tagged `server-archive` in git.

**If something comes back, it should be because people using the file asked for it** —
contexts that span repos, a view for people who never open the repo, enforcement of the rules.
