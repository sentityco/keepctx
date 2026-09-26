# ctx

**Context management is the new wiki — AI first, readable by humans.**

```sh
brew install ctx        # or: curl -fsSL ctxhub.com/install | sh

ctx new ace             # opens ctxhub — SSO if your org is there,
                        # otherwise create an account and an org
```

That is the setup. The context is created in your org, the index is written into
`AGENTS.md`, and your agent reads it from then on.

Need someone else's?

```sh
ctx pull comcast:idcmt
```

## Two commands

```sh
ctx pull <org>:<context>    pull one, and everything it requires
ctx new  <name> "summary"   create one in your org
```

`ctx` on its own shows what you have. `ctx <name>` prints one you already pulled.

Everything else happens on its own: syncing, the `AGENTS.md` index, the HTML view,
sending a correction upstream. A step you have to remember is a step that gets skipped.

## What the agent does

The index costs about 1,000 tokens and lists one line per context. Full text is fetched
only when a task needs it — preloading an org's knowledge costs ~50,000 tokens a session
and is mostly waste.

The index also tells the agent when to write back: someone corrected it, something took
real digging, or a decision was made whose reasoning would be lost. A correction to a
context you do not own becomes a proposal and goes to the owner.

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

Local backend works; `ctx new` stubs the ctxhub sign-in. Hosted auth and git sync are
designed, not built.
