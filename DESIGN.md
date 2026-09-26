# ctx — a context manager for AI and people

Status: design sketch, nothing built yet.

## The problem, stated precisely

Two problems get conflated here, and they have different solutions.

**1. Durable knowledge.** How the enterprise works. Who owns what. Why that service
exists. The conventions your team follows and the three other teams' conventions you
need to respect. This changes slowly, is genuinely shared, and is currently trapped in
Confluence, Slack threads, and people's heads. An agent starting cold has none of it.

**2. Session continuity.** What I was doing twenty minutes ago. Which files I had open,
what I already tried, what we decided. This changes constantly and is personal.

`ctx` should solve (1) properly. It can help with (2) but should not pretend to be a
memory system.

## The counterintuitive part

The obvious design — "pull enterprise context into my workspace so the agent has it" —
makes token cost *worse*, not better. If you preload 200KB of organisational context
into every session, you pay ~50K tokens before the first question, and 95% of it is
irrelevant to the task at hand.

**The win is retrieval, not preload.**

The design target:

| Approach | Tokens per session |
|---|---|
| Preload everything | ~50,000 |
| Index only, fetch on demand | ~1,000 + ~2,000 per card actually needed |

So the always-on cost is a small index. Everything else is a tool call the agent makes
when it decides it needs something.

This is the same shape as `llms.txt` for websites: a cheap index that tells a machine
what exists and where, not a dump of the content.

## Architecture

### Context cards

The unit is a **card**: one markdown file, one topic, with frontmatter.

```markdown
---
id: payments-service
title: Payments service ownership and on-call
scope: team:payments          # enterprise | team:<name> | project:<name>
owner: "@ktran"
updated: 2026-09-14
review_by: 2026-12-14
summary: Who owns payments, how to page them, and the two gotchas in the refund path.
tags: [payments, on-call, services]
---

Body. Kept short on purpose — a card that needs 3,000 words is two cards.
```

Cards are small, owned, and dated. **Wrong context is worse than no context**, so
ownership and freshness are first-class, not metadata afterthoughts.

### Sources and the cache

Teams publish cards in their own repos, under `ctx/`. The enterprise publishes a central
repo the same way. `ctx` registers those as **sources** and syncs them into a local
cache.

```
~/.ctx/cache/<source>/…     # synced, never edited by hand
./.ctx/                     # workspace-local: pins, overrides, session notes — gitignored
./ctx/                      # this repo's own published cards — committed
```

The instinct not to commit the pulled context is right, with one refinement: the *cache*
is gitignored, but the *source* lives in git, per team. That gives ownership, review,
history, and blame for free — and it means "who changed this and why" has an answer.

### Two front doors, one core

- **CLI** for humans and scripts: `ctx get payments-service`
- **MCP server** for agents that support it: the same operations as tools

Same index, same cards. The CLI matters because an agent can always shell out, even with
no MCP configured.

### The AGENTS.md hook

`ctx index` emits a compact index. It gets written into `AGENTS.md` between markers so it
regenerates cleanly:

```markdown
<!-- ctx:begin -->
## Available context

Run `ctx get <id>` to load any of these. Do not guess at these topics — fetch the card.

- `payments-service` — who owns payments, how to page them, refund path gotchas (team:payments, 2026-09-14)
- `deploy-pipeline` — how code reaches prod, who can approve (enterprise, 2026-08-02)
- `glossary` — internal acronyms and what they actually mean (enterprise, 2026-09-01)
<!-- ctx:end -->
```

That block is the entire always-on cost. Roughly 15 words per card, so 50 cards is about
1,000 tokens. The agent reads AGENTS.md automatically, sees what exists, and fetches only
what the task needs.

## Command surface (proposed)

```
ctx init                    scaffold ./ctx and ./.ctx, add gitignore entries
ctx source add <git-url>    register a context source
ctx sync                    pull all sources into the cache
ctx index                   print the index; --write updates AGENTS.md
ctx get <id> [<id>...]      print one or more cards
ctx search <query>          find cards by summary/tags/body
ctx new <id>                scaffold a card in this repo
ctx stale                   list cards past review_by, by owner
ctx save [note]             write a session handoff note to ./.ctx/sessions/
```

## On session continuity

`ctx save` writes a short handoff — what we were doing, what was decided, what is next.
`ctx get session:last` pulls it back. That is a deliberate substitute for keeping a
session alive for days: a 300-token note instead of a 200K-token transcript.

It is not memory. It is a note you choose to write, which is also why it will be accurate.

## Open questions

1. **Sync model** — git-only, or a hosted registry later? Git is right for v1.
2. **Access control** — if some cards are sensitive, does ctx rely on git permissions,
   or does it need its own model? Git is right for v1.
3. **Who writes cards?** The honest failure mode for this whole idea is that nobody
   maintains them. `ctx stale` and owner attribution are the hedge; it may not be enough.
