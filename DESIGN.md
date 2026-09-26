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

## The model: org and context

Two levels, and that is the whole namespace.

```
comcast:ace          organization : context
```

**Organization is tenancy** — who owns the store. Comcast's `ace` and Acme's `ace` are
different things that must never collide, which is what matters the moment a hub hosts
more than one company. Set once, then implicit:

```sh
ctx use comcast:ace
# organization set to `comcast`
# subscribed to `ace` in `comcast`
```

Inside an organization you write bare names. `comcast:ace` requires `idcmt`, not
`comcast:idcmt` — qualification is only for crossing an org boundary.

### There is no scope, and no team

Both were cut. A scope was a grouping layer that existed to answer "what should be in my
index", and **the dependency graph already answers that better**:

```sh
ctx use comcast:ace
```
```
- `ace` — Team ACE: what we own, how we ship, who to ask
- `cloud-foundry` — CF spaces, quotas, routes
- `idcmt` — IDCMT: identity and credential management, how to request access
7 more contexts exist outside your subscriptions — find them with `ctx search <query>`.
```

Ten contexts exist; three are in the index, because `ace` requires the other two. You
subscribe to **a context**, and your working set is its closure.

This is better than a scope for a reason worth stating: the person who maintains `ace`
decides what a new starter sees, by declaring what ACE actually depends on. That is
curation by the person best placed to do it, rather than a flat namespace everyone dumps
into. When ACE picks up a dependency on Splunk, one line in `ace` puts it in every team
member's index.

A solo developer subscribes to one context and never thinks about any of this.

## Limiting recursion## Limiting recursion: three limits, not one

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

## Where the paid line goes

Free for individuals, paid for enterprises. The org is the tenant and therefore the
billing boundary, which the namespace already gives us.

The line has to be drawn so that **nothing which drives adoption is ever gated**. The
format, the CLI, local and git backends, unlimited contexts, unlimited people in a free
org — all permanently free. If an enterprise can run this on a git repo and never pay,
let them; they were never going to pay, and their usage still grows the format. That is
the deal that made git/GitHub work.

### Never gate

- **The format.** Plain markdown. If contexts are only readable by paid software, nobody
  adopts and no enterprise will risk the lock-in.
- **Context count.** Charging per context taxes exactly the behaviour the product needs.
- **Seats.** Punishes the org for rolling it out, and pushes people to share accounts.
- **Write-back.** Proposals are the flywheel. Making them a paid feature kills it.

### What enterprises pay for

Things a git repo structurally cannot do, so the gate is real rather than artificial:

- **SSO/SAML and SCIM.** The classic enterprise line. Nobody else wants it, every
  enterprise requires it, and it is genuinely work to build.
- **Usage telemetry.** Which contexts get read, which get disputed, which are read and
  then contradicted. Git cannot see reads. This is also what makes the `confirmed` state
  possible, so it is a feature *and* a product improvement.
- **Access control below repo granularity.** Some contexts are sensitive in ways that do
  not map to "who can clone this".
- **Audit.** Who changed what context, when, and who approved it.
- **Cross-org sharing.** A vendor publishing context to its customers — `acme:shared-sso`
  appearing in Comcast's index. That is a hub-only capability and a strong one.
- **Private orgs, self-hosting, SLA.**

### Sequencing

Pricing is downstream of adoption, and adoption is unproven. The order stays: use it
locally, then one team on git, then a hub — and think about pricing when there is
something to charge for. Designing the paywall before the product has users is the most
common way this kind of tool dies.
