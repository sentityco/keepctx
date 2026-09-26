# ctx

**Context management is the new wiki — AI first, readable by humans.**

```sh
ctx comcast:ace        # join. that is the setup.
```

That one command creates the workspace, subscribes, syncs, writes the index into
`AGENTS.md`, and renders the HTML view. Your agent reads the index from then on, and the
index tells it how to read and write context. Nothing else to run.

## The whole interface

```sh
ctx                    # what you have, and what the index costs per session
ctx <org>:<context>    # join one
ctx <name>             # read it, plus whatever it requires
ctx new <name> "..."   # write one back
```

Anything else is treated as a search. There is no init, no sync, no index, no render, no
push — those happen because something changed, not because you remembered.

Owners get two more: `ctx review` for the queue, `ctx ok <name>` to sign off.

## What the agent does

The index in `AGENTS.md` costs about 1,000 tokens and lists one line per context. The
agent fetches the full text only when a task needs it:

```
- `ace` — Team ACE: what we own and how we ship (2026-09-25)
- `idcmt` — IDCMT: identity and credential management (2026-09-25)
7 more contexts exist outside your subscriptions — find them with `ctx <query>`.
```

Preloading an organisation's knowledge costs ~50,000 tokens a session and is mostly
waste. That number is the whole argument.

Write-back has three triggers, and the agent is told them: someone corrected it,
something took real digging, or a decision was made whose reasoning would be lost. A
correction to a context you do not own becomes a proposal and goes upstream for the owner
to review.

## org : context

Two levels, that is the namespace. `comcast:ace`. Inside an org, names are bare — `ace`
requires `idcmt`, not `comcast:idcmt`. Subscribing to a context gives you that context
plus everything it requires; the person maintaining `ace` decides what a new starter sees.

## Why this does not rot the way wikis do

Wikis die of low read volume — a page nobody opens is a page nobody notices is wrong. An
agent reads context every session, which is what surfaces errors, and the correction gets
captured while someone still has the right answer in hand. The reading is what keeps the
writing honest.

## Layout

```
ctx/         contexts this repo owns — committed
.ctx/        cache, proposals, HTML — gitignored
AGENTS.md    the index, between <!-- ctx:begin --> markers
```

## Design

See [DESIGN.md](DESIGN.md).

## Status

Local backend works. Git and ctxhub are designed, not built.
