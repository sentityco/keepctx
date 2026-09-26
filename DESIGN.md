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
scope: ace                   # a flat name. '/' nests if you want it.
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

## One role: everyone reads, everyone writes

There is no publisher class. Anyone who consumes context can improve it, and the fastest
person to spot that a context is wrong is the newest person on the team — they are the
one hitting it cold.

```sh
brew install ctx
ctx use ace               # subscribe: read and write, same command

# later, having lost an hour to a wrong Splunk index name
ctx propose splunk-index-gotcha --summary "ace-prod index is actually ace_prod_v2"
ctx push                  # goes upstream to the ACE source
```

The scope owner sees it in `ctx review`, with the author attached:

```
[proposed ] splunk-index-gotcha   ace-prod index is actually ace_prod_v2   from jmarks
```

Attribution is for **routing and credit**, never for weighting. The owner knows who to
ask a follow-up question; that is all it is for.

`ctx init` still exists, but only for the rare act of starting a brand-new source. Most
people never run it. `ctx use` is the command.

### Why proposals go upstream rather than staying local

A correction trapped in one person's `.ctx/` is worth nothing. The value is entirely in
the next person not hitting the same wall. `ctx push` is what makes write-back a shared
asset rather than a private note — and it is why the local-only build is only step one.

## Scopes: one name, no taxonomy

A scope is a flat name. `ace`. `billing`. `myapp`. There is no `team:` prefix, because
the prefix is a *type* and nothing in the mechanism uses one — grouping needs a name, not
a classification. Forcing an indie developer to declare that their side project is a
`project:` and not a `team:` is asking them to model an organisation they do not have.

**Indie developer.** One scope, named after the thing:

```
- `deploy` — How myapp ships: fly.io, one command, rollback story (myapp)
- `gotchas` — The three things that bite me every time I come back (myapp)
```

**Enterprise.** Same mechanism. `/` nests when it earns its keep, and subscribing to a
parent picks up the children:

```sh
ctx use ace platform enterprise
```
```
- `ace-deploy` — How ACE ships to prod (ace)
- `ace-oncall` — ACE paging and escalation (ace)
- `cloud-foundry` — CF spaces, quotas, routes (enterprise)
- `grafana` — Dashboards that matter (platform/observability)
- `splunk` — Splunk indexes and access (platform/observability)
- `k8s` — Clusters, namespaces, who approves (platform/runtime)
4 more contexts exist outside your scopes — find them with `ctx search <query>`.
```

`platform` matched both `platform/observability` and `platform/runtime`; `billing` was
not subscribed, so it collapsed into the count.

`enterprise` is a convention, not a keyword — it is just the name people will reach for.
The tool does not know or care.

Scope defaults to your first subscription, or the directory name if you have none. An
indie developer never types `--scope` at all.

## Limiting recursion: three limits, not one

The question "how deep do dependencies go" has three different answers because it is
three different questions. The rule: **greedy on disk, stingy on tokens.**

**1. Sync — unbounded.** Pull the whole reachable graph. These are small markdown files;
disk is free and a missing file is worse than an unused one.

**2. Index — bounded by scope.** Only your subscribed scopes and what they *directly*
require get a line in AGENTS.md. Everything else collapses to one line:

```
- `comcast-cf` — Cloud Foundry: spaces, quotas, routes (enterprise)
- `plat-splunk` — Splunk: indexes we can read, how to get access (enterprise)
- `ace` — Team ACE: what we own, how we deploy, who to ask (ace)
- `oncall-rota` — Who is on call and how paging reaches them (ace)
42 more contexts exist outside your scopes — find them with `ctx search <query>`.
```

46 synced, 4 listed. The index is a **working set, not a catalogue** — which is what keeps
it constant-cost as the organisation grows. `ctx search` is the escape hatch, so nothing
is ever unreachable, just unlisted.

**3. Fetch — depth 1 by default.** `ctx get ace` returns ACE and what it directly
requires. Anything beyond is named but not loaded:

```
<!-- depth 1 reached; not loaded: sso-onboarding -->
<!-- 3 contexts, roughly 45 tokens -->
```

The agent can see what it did not get and ask for it. That is better than a default that
quietly pulls forty files, and better than one that hides that more exists.

## Five decisions

**1. Retrieval, not preload.** The index is the product; everything else is plumbing. If
the index is good, the agent knows what exists and fetches correctly. If it is bad, no
amount of storage helps.

**2. Scopes are flat names, and nesting is optional.** Not a taxonomy. See below.

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
