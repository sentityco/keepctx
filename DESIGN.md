# ctx — design

**Thesis.** Agents start every session blind. The fix is not to load more context — it is
to make context *cheap to find, cheap to read, and cheap to write*. Everything below
follows from that.

---

## What ctx is

A small index that an agent always sees, pointing at contexts it fetches only when the
task needs them.

```
AGENTS.md          ~1,000 tokens  — always loaded, one line per context
ctx get <id>       ~500 tokens    — paid only when relevant
```

Preloading an organisation's knowledge costs ~50,000 tokens a session and is ~95% waste.
That number is the whole argument.

## The unit: a context

One markdown file, one topic, with frontmatter.

```markdown
---
id: ace
title: Team ACE — what we own and how we ship
scope: team:ace              # enterprise | team:<name> | project:<name>
owner: "@jmarks"
state: verified
updated: 2026-09-25
review_by: 2027-09-25
summary: What ACE owns, how we deploy, who to ask. ONE LINE — every session pays for this.
requires: [comcast-cf, plat-splunk]
related:  [payments-service]
---
```

Small, owned, dated. **Wrong context is worse than no context**, so ownership and
freshness are structural, not decoration.

## Five decisions

**1. Retrieval, not preload.** The index is the product; everything else is plumbing. If
the index is good, the agent knows what exists and fetches correctly. If it is bad, no
amount of storage helps.

**2. Three layers, one mechanism.** `enterprise`, `team:<x>`, `project:<x>` are just
scopes on the same object. No separate systems.

**3. `requires` is loaded, `related` is not.** Hard dependencies get pulled with the
context; pointers get listed. Depth 2 by default, cycles detected, token cost always
printed. Without that split one fetch drags in half the company.

**4. Agents propose, humans verify.** Write-back is how this survives contact with
reality — every wiki dies of neglect, and capture-as-a-side-effect is the only known
cure. But proposals land in a staging state, never straight into the trusted store, or
a wrong context silently becomes a fact and the next session builds on it.

| State | Meaning |
|---|---|
| `verified` | An owner signed off. Treat as fact. |
| `proposed` | Agent-written, unreviewed. Useful, unconfirmed. |
| `disputed` | Someone hit a contradiction. Read that first. |
| `stale` | Past `review_by`. Age is a claim about accuracy. |

The index shows state, so a reader always knows what it is trusting.

**5. No server required, ever.** Contexts are plain markdown; the index is a plain file.
A team can run this out of a git repo forever. ctxhub adds hosting, discovery, usage
signal and a review queue — it must never be the thing that makes `ctx` work, or this is
a SaaS with a CLI rather than a format with a host.

## When an agent writes back

The instructions matter more than the mechanism. Most interesting things are not worth
keeping. Three triggers only:

- **A human corrected you.** Highest signal available — existing context was wrong or
  missing, and the right answer is in hand.
- **Something cost real effort to establish.** Expensive once means expensive again.
- **A decision and its reasoning.** Decisions decay fastest because the why never gets
  written down.

Never for task-specific detail, never for something inferred rather than verified, never
when an existing context covers it — update that one instead.

## Explicitly rejected

**Scoring people and weighting "smarter" users more.** Expertise is domain-scoped, not
scalar — the best distributed-systems engineer is not authoritative on the refund path.
Every proxy an LLM can compute (tenure, volume, confident phrasing) rewards the wrong
thing. The social cost of a tool that silently ranks colleagues is disqualifying. And it
addresses a rare problem.

What that idea actually wants is *whose claim wins* and *how much to trust this*. Both
come from scoring the **context**: ownership decides conflicts, state decides trust,
usage decides quality.

**Session memory.** Continuity between sessions is a real problem and a different one.
`ctx` should not pretend to solve it.

## Build order

1. **Local only.** Built. Use it on a real repo for a fortnight.
2. **Git backend.** One team. The question it answers: does anyone but the author ever
   write a context?
3. **ctxhub.** Only if step 2 produced anything worth hosting.

Building the hub first is a platform with nothing on it and no evidence anyone wants to
put anything there.

## The thing that decides whether this works

Not the storage, the sync, or the hub. **Whether the one-line summaries are good.** A bad
summary means the agent never fetches the context, and an unfetched context may as well
not exist. No tooling fixes that — it is a writing problem, and it is the only real risk.
