# ctx

A context manager for AI and people.

Every new AI session starts blind. The usual workarounds are to keep one session alive
for days, or to paste the same background in again — both of which burn tokens on
context the model mostly does not need.

`ctx` stores organisational knowledge as small markdown files it calls **contexts**, publishes a one-line
index into `AGENTS.md`, and lets the agent fetch only the contexts a task actually needs.

```sh
ctx init            # one command, no flags, working immediately
ctx new <id>        # write a context
ctx list            # what exists  (--scope --state --tag)
ctx get <id>        # print it, plus whatever it requires
ctx deps <id>       # what it pulls in, and what that costs
ctx status          # totals, and what the index costs per session
```

## Why an index instead of a dump

Preloading everything makes the problem worse:

| | Tokens per session |
|---|---|
| Preload all context | ~50,000 |
| Index + fetch on demand | ~1,000 + ~2,000 per context used |

`ctx status` prints the real number for your repo.

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
