# ctx

**Context management is the new wiki — AI first, readable by humans.**

A wiki is written for people and scraped by machines as an afterthought. `ctx` inverts
that: contexts are written to be read by an agent every session, and rendered to HTML
when a person wants to look.

Every new AI session starts blind. The usual workarounds are to keep one session alive
for days, or to paste the same background in again — both of which burn tokens on
context the model mostly does not need.

`ctx` stores organisational knowledge as small markdown files it calls **contexts**, publishes a one-line
index into `AGENTS.md`, and lets the agent fetch only the contexts a task actually needs.

```sh
ctx use <scope>     # subscribe — read and write, one command
ctx new <id>        # write a context
ctx list            # what exists  (--scope --state --tag)
ctx get <id>        # print it, plus whatever it requires
ctx deps <id>       # what it pulls in, and what that costs
ctx propose <id>    # write something back
ctx push            # send it upstream for the owner to review
ctx status          # totals, index cost, and where to browse it
```

## Why this does not die the way wikis die

Wikis rot because nobody reads them. A page nobody opens is a page nobody notices is
wrong, and the error sits there for years.

An agent reads context on **every session**. High read volume is what surfaces errors —
and when the agent is corrected, `ctx propose` captures the correction while someone has
the right answer in hand. The reading is what keeps the writing honest.

There is no render command. HTML regenerates on every change, so the human-readable view
is always current and nobody has to remember it exists. `ctx status` prints the path.

Same files either way. The agent reads the markdown; a person opens the page.

## Why an index instead of a dump

Preloading everything makes the problem worse:

| | Tokens per session |
|---|---|
| Preload all context | ~50,000 |
| Index + fetch on demand | ~1,000 + ~2,000 per context used |

`ctx status` prints the real number for your repo.

## org : context

Two levels, that is all.

```sh
ctx use comcast:ace      # org is `comcast`, thereafter implicit
ctx use sentity:myapp    # solo: same mechanism
```

Inside an org, names are bare — `comcast:ace` requires `idcmt`. You subscribe to a
**context**, and your index is that context plus everything it requires. Nothing else.

## Layout

```
ctx/         contexts this repo owns — committed
.ctx/        cache, proposals, session notes — gitignored
AGENTS.md    the index, between <!-- ctx:begin --> markers
```

## Context that maintains itself

Agents write back with `ctx propose`. Proposals land in a staging state rather than the
trusted store, so a wrong context never silently becomes a fact:

| State | Meaning |
|---|---|
| `verified` | An owner signed off. Treat as fact. |
| `confirmed` | Held up in practice, never contradicted. |
| `proposed` | Agent-written, unreviewed. |
| `disputed` | Someone hit a contradiction. |
| `stale` | Past `review_by`. |

The index marks state, so a reader always knows what it is trusting.

## Design

See [DESIGN.md](DESIGN.md) — including why this scores *context* rather than people, and
why `ctxhub` must never be required for `ctx` to work.

## Status

Local backend only. Git and ctxhub backends are designed, not built.
