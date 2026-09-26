# ctx

**Context management is the new wiki — AI first, readable by humans.**

```sh
brew install ctx                  # or: curl -fsSL ctxhub.com/install | sh

ctx new notes "what I forget between sessions"
```

No account, no signup, no prompt. Contexts land in `./ctx`, the index is written into
`AGENTS.md`, and your agent reads it from then on.

When you want somebody else's context, that comes from ctxhub:

```sh
ctx login
ctx pull comcast:idcmt
```

## Two commands

```sh
ctx new  <name> "summary"     create one — always local, never asks
ctx pull <org>:<context>      fetch one from ctxhub, and what it requires
```

`ctx` alone reports what you have. `ctx <name>` prints one you already have. `ctx login`
adds an org when you want to share.

Everything else happens on its own: the `AGENTS.md` index, the HTML view, sending a
correction upstream. A step you have to remember is a step that gets skipped.

## Local and hosted

Local is the default and is not a degraded mode — contexts are plain markdown either way,
and an individual developer never needs an account.

An account buys the things a local directory structurally cannot do: pulling other
teams' contexts, sending a correction to the person who owns it, and a review queue
somebody will actually drain.

## What the agent does

The index costs about 1,000 tokens and lists one line per context. Full text is fetched
only when a task needs it — preloading an org's knowledge costs ~50,000 tokens a session
and is mostly waste.

The index also tells the agent when to write back: someone corrected it, something took
real digging, or a decision was made whose reasoning would be lost. A correction to a
context you do not own becomes a proposal for the owner.

## org : context

Two levels, that is the namespace. Inside an org names are bare — `ace` requires `idcmt`,
not `comcast:idcmt`. Pulling a context gives you it plus what it requires, so the person
maintaining `ace` decides what a new starter sees.

## Why this does not rot the way wikis do

Wikis die of low read volume — a page nobody opens is a page nobody notices is wrong. An
agent reads context every session, which is what surfaces errors, and the correction is
captured while someone still has the right answer in hand.

## Layout

```
ctx/         contexts this repo owns — committed
.ctx/        cache, proposals, HTML — gitignored
AGENTS.md    the index, between <!-- ctx:begin --> markers
```

## Design

See [DESIGN.md](DESIGN.md).

## Status

Local works end to end. `ctx login` and `ctx pull` stub the ctxhub calls.
