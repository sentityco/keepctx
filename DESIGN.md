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

## Write-back: context that maintains itself

The failure mode of every wiki is that nobody updates it. The fix is to let the agent
capture context as a side effect of work that is already happening. But an agent writing
straight into the trusted store is how you get compounding fiction: a wrong card becomes
a fact, the next session builds on it, and six weeks later nobody can find the origin.

So writes land in a **staging state**, not the trusted store. Every card carries a trust
state, and the index shows it:

| State | Meaning |
|---|---|
| `verified` | A human owner signed off. Treat as fact. |
| `proposed` | Agent-written, unreviewed. Useful, unconfirmed. |
| `confirmed` | Used successfully N times, never contradicted. |
| `disputed` | Someone hit a contradiction. Read the dispute before trusting. |
| `stale` | Past `review_by`. Age is a claim about accuracy. |

Promotion is one command (`ctx verify <id>`), so capture stays frictionless and readers
still know what they are getting.

### When the agent should write

The seed instructions matter more than the mechanism. Most "interesting" things are not
worth a card. The high-signal triggers are narrow:

- **A correction.** The human corrected the agent about how something actually works.
  This is the single most valuable signal available — it means the existing context was
  wrong or missing, and you now have the right answer in hand.
- **A discovery that cost effort.** Something that took reading four repos to establish.
  If it was expensive once it will be expensive again.
- **A decision and its reason.** We chose A over B because C. Decisions decay fastest
  because the reasoning never gets written down.

And explicitly not: anything task-specific, anything the agent inferred rather than
verified, anything already covered by an existing card (update that one instead).

### Confirmation instead of review

When an agent uses a `proposed` card and the work succeeds, it calls `ctx confirm <id>`.
Several confirmations with no disputes makes a card eligible for promotion. That is an
observed signal rather than an assigned one, and it attaches to the card.

## On weighting by person

The instinct is right — some claims should carry more weight than others — but scoring
people is the wrong lever, for four reasons.

**Expertise is domain-scoped, not scalar.** The best distributed-systems engineer in the
building is not authoritative about the payments refund path. The person who owns it is,
regardless of seniority.

**Any computable proxy measures the wrong thing.** Tenure, commit volume, verbosity,
confidence of phrasing — these are what an LLM can actually observe, and they reward
people who sound certain. That is the opposite of what you want.

**The social cost is disqualifying.** A tool that silently ranks colleagues and
discounts some of them is a political grenade, and people will find out. "The AI decided
your input counts less" ends adoption on the day it is discovered.

**It solves a rare problem.** Genuinely conflicting context from two people is uncommon
on a small team. Do not build a ranking system for the edge case.

What you actually want from scoring is two things: whose claim wins in a conflict, and
how much to trust a given card. Both are better served by scoring **the context, not the
people**:

- **Ownership decides conflicts.** Cards have an owner; for their domain, their version
  wins. This is `CODEOWNERS` logic, which organisations already accept.
- **Provenance and state decide trust.** Who wrote it, when, whether anyone confirmed or
  disputed it.
- **Usage decides quality.** A card fetched often and never corrected is probably good.

Same benefit, none of the politics.

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
ctx propose <id>            agent-written card, lands as `proposed`
ctx confirm <id>            record that a card held up in practice
ctx dispute <id> <why>      flag a contradiction
ctx verify <id>             owner signs off; promotes to `verified`
ctx review                  queue of proposed/disputed cards awaiting a human
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
3. **Does the review queue get drained?** Auto-capture moves the failure mode rather than
   removing it: instead of an empty wiki you get an unreviewed queue. Worth deciding what
   happens to a `proposed` card nobody looks at for 90 days — expire it, or let
   confirmations promote it without a human.
