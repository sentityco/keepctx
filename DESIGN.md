# keepctx — design

**Positioning.** Context management is the new wiki: AI first, readable by humans.

A wiki is written for people and machine-read as an afterthought. This inverts it —
written to be read by an agent every session, rendered to HTML when a person wants to
look. There is no render step: HTML regenerates on every write, so the human view is a
byproduct rather than a chore. A documentation site that requires a command to rebuild is
a documentation site that is out of date.

**Why it does not rot the way wikis do.** Wikis die of low read volume: a page nobody
opens is a page nobody notices is wrong. An agent reads context every session, which is
what surfaces errors — and the correction gets captured at the moment someone has the
right answer in hand. The reading is what keeps the writing honest. That is the whole
argument for AI-first, and it is a claim this project lives or dies on.

**Thesis.** Agents start every session blind. The fix is not to load more context — it is
to make context *cheap to find, cheap to read, and cheap to write*. Everything below
follows from that.

**Two framings, two rooms.** "Context management is the new wiki" is the one for anyone
thinking at the level of organisational knowledge — a platform team, an exec, anyone who has
watched a Confluence space die. "Your AGENTS.md, except it writes itself" is the one for a
developer, who does not need the category explained and does need their own stale file fixed.
Same claim at two altitudes; use whichever matches who is asking. See *How to pitch it*.

---

## How to pitch it

**"Your AGENTS.md, except it writes itself — and your team shares it."**

This is the framing to lead with *for developers* — the wiki framing at the top of this
document is the one for anyone thinking about organisational knowledge, and neither replaces
the other. This one wins with a developer because it attaches to something people already have and
already know is broken. Everyone with an `AGENTS.md` knows it is stale: hand-written once,
never updated, quietly wrong about half of what it says. There is no new category to
establish and no one needs "context manager" explained — the pitch is fixing a file they are
already annoyed by.

It also collapses three claims into one sentence: writes itself (capture), stays current
between sessions (persistence), shared (team).

**One precision to keep.** ctx *extends* the mechanism; it does not take over the file. Hand-
written instructions in `AGENTS.md` survive untouched — ctx adds a pointer and the maintained
knowledge lives behind it. Worth stating plainly, because "this tool manages my AGENTS.md"
makes people fear it will eat notes they wrote carefully, and the true answer is better than
the worry. It is also the enterprise anti-objection: nothing you wrote is overwritten, and
removing ctx is deleting two lines.

### The benefits, strongest first

**1. Stop re-explaining the same thing.** The felt version of persistence. "Context survives
between sessions" is a mechanism; "I have told it three times we use Kinesis, not Kafka" is a
pain people recognise instantly. Corrections stick.

**2. It costs less per session.** Preloading an organisation's knowledge runs ~50,000 tokens
and is ~95% waste. The index is ~1,200, and a context is paid for only when the task touches
it. Quantified, and nobody else leads with it — for an enterprise it is a line item rather
than a vibe.

**3. Onboarding.** A new person clones the repo and their agent already knows the deploy
command, the real logging index, and which docs are lying. "New hire productive on day one" is
something companies actually buy, and "share with your colleagues" does not say it.

**4. The AI cannot wreck your knowledge base.** Every change is versioned and one revert away.
This is the first objection anyone raises about agent-written documentation, and having the
answer ready turns a blocker into a shrug.

**5. Zero ceremony, which is why it will not rot like the wiki.** No page to create, no review
queue, no commit. Wikis die because capture costs more than skipping it; here capture is a
side effect of working.

**6. Plain markdown, self-hostable, nothing in git.** Three things that are one argument: no
lock-in. A procurement conversation rather than a developer one.

### Claims not to make

**That it makes the AI smarter.** It does not. It stops the AI being ignorant of things your
team already knows, which is a different and more defensible claim.

**That you can see what context gets read.** Impossible by construction — the agent opens
`facts.md` directly, so nothing observes a read. Easy to promise by accident, and it is a
claim a customer can disprove in a day.

## What ctx is

A small index that an agent always sees, pointing at contexts it fetches only when the
task needs them.

```
AGENTS.md                ~40 tokens     — two lines the dev owns, pointing at ctx
.ctx/instructions.md     ~1,200 tokens  — the rules, plus one line per context
.ctx/<name>/facts.md     ~500 tokens    — read when the task touches it
```

Three files, and the agent reaches them with ordinary file reads. `AGENTS.md` belongs to the
developer, so ctx adds a pointer and never writes there again.

Preloading an organisation's knowledge costs ~50,000 tokens a session and is ~95% waste.
That number is the whole argument.

## The commands

```sh
ctx                    # status and usage
ctx sync               # upload local changes, download remote ones
ctx init [name]        # set up here. local, no account, no network.
ctx remote             # one-time. creates this context on a remote, settles the name.
ctx clone org:name     # get a context you do not have, plus what it requires.
ctx upgrade            # replace the binary. only ever when asked.
```

There is no `add`, no `commit`, no `push`, no `pull`, no `render`, and no read command.

**Reading and writing are plain file operations, not commands.** The agent reads
`.ctx/<name>/facts.md` with its ordinary file tools and edits the same file as it learns
things. That is what agents are already good at — no subprocess, no stdout to parse, no
permission prompt on the most frequent operation in the system.

**ctx is only called for network work.** Once at session start and again after recording
facts. Facts change on the scale of hours, so paying for a round trip on every read would buy
freshness nobody needs.

An earlier draft hid sync inside a read command so it could not be skipped. It was the wrong
trade: it made the cheapest, most common operation the most expensive one.

**`ctx init` takes an optional name and defaults to the current directory, slugified.**
`ctx init` in `~/work/example-project` gives you `example-project`; `My Project` becomes `my-project`. Nobody should
have to type a name they do not have to.

**The name is settled at `ctx remote`, not at init.** Before creating a remote it is a local label and
nothing depends on it, so local names are permissive. At `ctx remote` it becomes globally
addressable as `org:name` — the first moment it has to be unique in a namespace — so that is
where it is validated, and where `ctx remote` rejects a name too generic to claim. Which matters,
given how many people are sitting in `~/code/src` or `~/work/api`.

**`sync` and `clone` stay distinct.** Sync updates contexts you have; clone fetches one you
do not.

**Why `remote` and `sync` stay separate**, despite collapsing neatly into one verb whose
first call configures the remote: `sync` would become the command that first exposes your
data. Creating the remote is one-time, consequential and hard to walk back; syncing is routine and
idempotent. Merged, the routine word carries the consequential invocation — and a
session-start hook firing `ctx sync` would silently create a remote for a local-only context the first
time it ran, with nobody having typed anything. Creating a remote also needs inputs sync does not
(which org, what name, validated), so the first call would be interactive and the rest silent
from one command. So `ctx sync` with no remote fails helpfully instead:

```
$ ctx sync
no remote for this context — `ctx remote` to create one
  (everything local keeps working without it)
```

Actions that push data outward get typed deliberately, once.

## One directory, one authored context

You author one context. Every other context on your disk is someone else's, brought in by
`clone`. There is no act of creating a second context of your own in one place — that is
what a second directory is for.

```
AGENTS.md              # the dev's file. ctx adds two lines at the top, then never returns.
.ctx/
  .gitignore           # contains `*`. see below.
  instructions.md      # the rules + the index. ctx owns it; the agent never writes it.
  example-project/
    facts.md           # yours. the agent appends and updates lines here.
  example-platform/
    facts.md           # cloned dependency. read-only.
  example-logging/
    facts.md           # cloned dependency. read-only.
```

One hidden directory, like `.git`. Subdirectory per context. **Ownership decides
writability**, which is the only distinction that matters and the only one worth encoding
in the layout.

Three things about that shape are load-bearing:

**`instructions.md` sits above the contexts, not inside one.** The rules for maintaining
context are identical for every context on the machine — they are ctx's own manual, not
data about your project. A copy per context directory would be N copies drifting to
different versions the moment clones arrive.

**The agent never writes `instructions.md`.** If the maintenance rules lived in the same
file as the content, every update would be the agent rewriting a file whose own
instructions are part of its content. Over a dozen sessions those rules get summarised,
drifted or dropped — and once they are gone the auto-update stops silently. Splitting the
file the agent rewrites from the file it only reads removes that whole failure class.

**A context is a directory even when it holds one file.** It gives clones and your own
context the same shape, with no special case anywhere, and it leaves somewhere to put a
context that outgrows one file — split by key prefix, `gateway.md` and `deploy.md`, so a
fetch can take the cluster it needs instead of everything. A single flat file read whole is
preloading, the thing this design exists to avoid.

### Context never lives in git

**Code is correct relative to a commit; context is a claim about the world right now.**
Versioning context by branch means a context that is right on `main` is wrong on a
two-week-old feature branch for no reason at all, and two people editing one context on
different branches produce a prose merge conflict neither can resolve from the diff. Git's
model — snapshots pinned to branch state — actively fights the one property this tool
exists to have.

The noise is the smaller half of the argument but it is real: a file an agent rewrites
every session leaves `git status` permanently dirty and drags unrelated churn into every
pull request.

So there are exactly two places context lives:

- **Local only.** `.ctx/` persists your context between AI sessions and nothing else knows
  it exists. No account, no network, forever.
- **Published.** A remote — hosted or self-hosted — holds the latest, and local is a cache
  of it.

**Local mode is persistence, not durability.** No remote means no backup, and a dead laptop
takes the context with it. That is the correct trade for a free local tool, and it makes
the reason to get a remote honest: run `ctx remote` if you want it to survive, or to let anyone else
read it.

### How `.ctx/` stays out of git

`ctx init` writes `.ctx/.gitignore` containing a single `*`. The directory ignores its own
contents, including that file.

This is chosen over adding a line to the project's `.gitignore` for three reasons:

- **It works before git exists, and the moment git arrives.** A dev who runs `ctx init`
  today and `git init` next week is covered with no window in which `git add .` could
  swallow the context.
- **ctx never edits a file the developer owns.** Their `.gitignore` stays theirs.
- **It removes the detection logic entirely** — no walking up for `.git`, no handling
  `.git`-as-a-file in worktrees and submodules, no deciding between root and nested
  placement, no idempotent append. None of that is needed.

Git has no way to represent a directory with no tracked files in it, so `.ctx/` does not
appear in the index, in a commit, or even as untracked. (The `.gitkeep` hack exists because
people sometimes want the opposite; its existence is the proof of the default.)

A developer who deliberately wants context in git can `git add -f`. That is the right
friction ratio for a decision this design has already made.

### What git sees: two lines

Nothing about ctx is committed except a pointer, at the top of `AGENTS.md`, that a human
can read, edit or delete:

```markdown
AI context for this project lives in `.ctx/instructions.md` — read it first.
Missing? It is gitignored by design. Install ctx (https://keepctx.com), then
`ctx clone <org>:<name>` — or `ctx init` if this project has no context yet.
```

The pointer goes at the top so an agent sees it before reasoning on the rest of the file,
and it is phrased as an instruction rather than a notice — "this file is managed by ctx"
tells a model nothing it can act on.

**The second line exists because the first one is a dead link on a fresh clone.** There are
two failure shapes and only one self-heals. A teammate who has ctx installed follows the
fallback and is fine. A teammate who does not has an instruction they cannot satisfy — and
an agent handed a missing referenced file tends to either burn turns hunting for it or
quietly invent what it probably said. Naming the install step makes the pointer resolvable
from any machine.

It links to an install page rather than inlining `curl … | sh`. A file in a repo that tells
an agent to pipe a remote script into a shell is a pattern not worth normalising, and the
human should see that step.

**The trade this accepts:** because no context list is committed, a fresh clone cannot tell
an agent *which* contexts the project used — the developer has to know the name. Free for a
solo dev, one line in a real README for a team, and it is the price of keeping git clean.

**Uninstalling is deleting two lines.** ctx never returns to `AGENTS.md` after init, so
those lines also persist if someone abandons ctx and removes `.ctx/`. Nothing can be done
about that, and it is worth documenting plainly: a tool that is trivial to remove is easier
to adopt.

## The unit: a context

A context is **a list of facts**. Not a document, not prose with facts in it — a list.

**A context is whatever unit of knowledge is useful to you** — one repository, one service,
one team, one programme, one platform. ctx does not care and should never impose a shape. The
examples here use `example-org:example-project` for a repo or service and
`example-org:example-platform` for something it depends on. `example-org:example-team` for a
team, `example-org:example-migration` for a six-month programme, or
`example-org:example-rotation` for an on-call rotation are all equally valid. The only rule is
that a context has an owner and a name.

```markdown
---
id: example-project
title: Checkout service — what we own and how we ship
org: example-org
owner: "@you"
updated: 2026-09-26
review_by: 2027-09-26
summary: What example-project owns, how we deploy, who to ask. ONE LINE — every session pays for this.
requires: [example-platform, logging]
related:  [payments-service]
---

- **deploy.command** — `make ship` from the repo root, not the platform CLI directly.
- **logging.index** — `app_prod_v2`. The docs still say `app-prod`; they are wrong.  `[verified]`
- **gateway-1.ip** — 10.2.3.5
- **gateway.routes-to** → portal tier, chosen by source IP
- **gateway.depends-on** → example-platform, for session validation
- **event.transport** — Kinesis, not Kafka. Inherited, and not changing.  `[verified]`
- **deploy.process** — three steps:
    - build with `make`
    - push to staging
    - verify the health endpoint
```

The bolded lead is the **key**; everything after the dash is the value. A value can be an
IP, a command, or a sentence — so dropping prose costs expressiveness nothing. What it costs
is narrative flow, and agents do not need flow. They need retrievable statements.

Dotted keys group for free: `gateway.*` reads as a cluster without anyone maintaining
headings.

### Why markdown, and why line-oriented

The format is downstream of one decision already made: **the agent edits this file directly
with an ordinary text-edit tool.** That rules out most of the richer options.

**Line-oriented formats fail gracefully; document formats fail catastrophically.** A malformed
bullet is one odd-looking line. A missing quote in YAML or a trailing comma in JSON destroys
the whole file — and the editor here is a model that will eventually get it wrong. YAML is
particularly bad for these payloads: values get type-coerced, and a colon inside a value breaks
the parse unless quoted, which models forget constantly. The facts are IPs, shell commands and
sentences, which is exactly what YAML mangles.

Three pieces of syntax carry everything, and no more should be added:

| Syntax | Means |
|---|---|
| `— value` | an attribute |
| `→ value` | a relationship. one character, and it makes edges mechanically extractable |
| `` `[verified]` `` | a human settled it |

Indented sub-lists cover multi-step values and stay line-diffable.

**What deliberately stays out of the file:** who wrote it, when, previous values, evidence. All
of it is derivable from version history, and duplicating it into the file is what turned an
earlier design into an unmaintainable schema. **If a field can be derived, it does not go in
the file.**

**When this decision should be revisited:** if `ctx` ever mediates writes — a write command
taking structured input — then JSON or YAML becomes safe, because a program does the formatting
and can validate before saving. That fork costs the zero-ceremony write path, which is the
thing that makes capture actually happen, so it should not be taken lightly.

**Why no prose.** An earlier draft had prose paragraphs alongside the facts, which forced two
merge policies — additive for facts, last-write-wins per section for prose — and section-level
clobbering was the best available answer for the prose half. One kind of content means one
policy. Anything genuinely worth keeping is a fact with a subject.

**`[verified]` marks a fact a human settled** — "this is a decision, stop re-deriving it."
Not a write block. A marker that makes an agent think twice and makes a change notification
worth reading.

**Wrong context is worse than no context**, so ownership and freshness are structural rather
than decoration.

## One role: everyone reads, everyone writes

There is no publisher class. Anyone who consumes context can improve it, and the fastest
person to spot that a context is wrong is the newest person on the team — they are the one
hitting it cold.

A correction trapped on one laptop is worth nothing; the value is entirely in the next
person not hitting the same wall. That is why write-back goes upstream by default, and why
the local-only build is only step one.

## The model: org and context

Two levels, and that is the whole namespace.

```
example-org:example-project          organization : context
```

**Organization is tenancy** — who owns the store. `example-org:example-project` and
`other-org:example-project` are different things that must never collide, which is what matters
the moment a hub hosts more than one company. It is also therefore the billing boundary.

Inside an organization you write bare names. `example-org:example-project` requires `example-platform`, not
`example-org:example-platform` — qualification is only for crossing an org boundary.

### There is no scope, and no team

Both were cut. A scope was a grouping layer that existed to answer "what should be in my
index", and **the dependency graph already answers that better**. Ten contexts exist;
three are in your index, because `example-project` requires the other two. Your working set is the
closure of what you have.

This is better than a scope for a reason worth stating: the person who maintains `example-project`
decides what a new starter sees, by declaring what it actually depends on. That is
curation by the person best placed to do it, rather than a flat namespace everyone dumps
into. When it picks up a dependency on example-logging, one line in `example-project` puts that in
every team member's index.

A solo developer has one context and never thinks about any of this.

## Limiting recursion: three limits, not one

"How deep do dependencies go" has three different answers because it is three different
questions. The rule: **greedy on disk, stingy on tokens.**

**1. Sync — unbounded.** Pull the whole reachable graph. These are small markdown files;
disk is free and a missing file is worse than an unused one.

**2. Index — bounded by the closure.** Only your own context and what it *directly*
requires get a line in `.ctx/instructions.md`. Everything else collapses to one line:

```
- `example-project` — what this service owns, how it deploys, who to ask
- `example-platform` — identity and credentials: how to request access, how tokens expire
- `example-logging` — which indexes we can read, and the one the docs get wrong
42 more contexts exist in example-org — find them with `ctx search <query>`.
```

46 synced, 3 listed. The index is a **working set, not a catalogue** — which is what keeps
it constant-cost as the organisation grows. Search is the escape hatch, so nothing is ever
unreachable, just unlisted.

**3. Read — your own context, then only what you need.** Reads are plain file reads, so this
is not something ctx can enforce. It is guidance in `instructions.md`: read your own
`facts.md`, consult the index for dependencies, and open a dependency's `facts.md` only when
the task actually touches it.

That is weaker than a mechanism and it is the right weakness. The alternative was routing reads
through ctx so depth could be capped — which made the most common operation in the system a
subprocess, to solve a problem the index already mostly solves. An agent with a good index does
not open forty files; it opens the one it needs.

## Sync and conflict resolution

The problem: a junior with a weak model must not be able to destroy a senior's context.
Three answers were tried and discarded before the simple one, and the discards are worth
keeping because each looked right at the time.

**A reviewing AI that judges whether a change is good enough.** It has no ground truth — it
has never seen your logging index or your deploy pipeline — so it can only guess from
plausibility, which selects for confident prose. It also rebuilds the pull-request queue
this tool exists to avoid, staffed by a reviewer nobody can argue with.

**A server-side classifier that only detects contradictions.** Narrower and technically
sound, but it puts a model dependency in every install including every self-hosted one, and
"bring an API key to run your own context server" would stop most people from running one.

**Keyed JSON claims with supersede pointers, evidence fields and corroboration counts.** This
was an elaborate reimplementation of version history. Everything it bought is available by
keeping versions of the file.

### Three rules

1. **The client sends only the lines it changed**, never the whole file. A changing
   `gateway-1.ip` and B adding `logging.index` both land, because they are different keys.
2. **Same key, different value — the later one wins**, and the change appears in the diff.
3. **Every sync is a new version on the server.** A bad change is one revert away.

That is the entire conflict model. Nothing is ever lost, because the server keeps versions.

**This is git's versioning without git's branching.** Branching was the real objection — it
is where stale context and prose merge conflicts came from. One linear history that is always
current gives undo without any of it.

**Provenance is per-version, not per-fact.** "a teammate changed these two lines on the 26th" is
`git blame`, and it is enough. Per-claim authorship, model attribution and evidence fields
all bought less than they cost.

Recording *which model* wrote a fact was considered and dropped. It is genuinely useful for
diagnosis — "these twelve bad facts came from one weak model" — but a field that exists gets
used, and weighting facts by model is user-scoring wearing a hat.

### What the client decides

The client's model marks each write **add** or **update**, and the user is already paying for
that model, so the semantics cost the server nothing. A weak model gets this wrong sometimes.
That is survivable for one reason: **versions make every mistake reversible**, so the worst
outcome is a revert rather than a loss.

A better model therefore makes the context better, and a worse one can add noise but never
subtract quality. The incentive gradient points the right way, and the floor is held by
structure rather than by trusting anyone's model.

## How it all hangs together

```
AGENTS.md                →  read .ctx/instructions.md          (two committed lines)
.ctx/instructions.md     →  1. before reading context, run `ctx sync`
                            2. read .ctx/<name>/facts.md for context
                            3. write facts back to it as you learn them
                            4. rewrite the narrative section for the keys you touched
                            5. after writing facts, run `ctx sync`
.ctx/<name>/facts.md     →  the facts. the agent reads and edits this directly.
```

Three hops, and only the middle one is ctx's. The first is a file read of two committed lines;
the last is a file the agent owns for the length of the session.

**`instructions.md` is where the discipline lives**, because it is loaded every session and the
agent never rewrites it. Two directives about ctx and three about what deserves recording.

### Reaching a session that is already running

`AGENTS.md` is read into an agent's context **at session start**. A file written after that
reaches nobody until the next session — so `ctx init` in a live session installs instructions
that the agent running right now will never see. This is not hypothetical; it is what happened
the first time ctx was used on a real project, and the facts file stayed empty because of it.

The fix uses the one channel that does reach a running agent: **ctx runs as its subprocess, so
whatever ctx prints lands in the agent's context as the tool result.** The agent invoked the
command, so ctx gets to answer.

So `ctx init` and `ctx clone` print a short brief addressed to the agent — read this file,
write facts to it in this format, run sync afterwards. No re-read is required because the
output *is* the injection. Both commands are one-time, so the token cost is paid once.

`ctx sync` prints nothing extra; it runs constantly and a reminder on every call would be
waste.

**The honest limit:** this only reaches an agent that *ran the command*. A human running
`ctx init` in a separate terminal reaches no agent at all, and there is nothing ctx can do
about that from inside a subprocess. For that case the answer is a session-start hook where
the harness offers one, or simply the next session. Worth stating plainly rather than
implying the brief closes the gap completely.

### When sync fires

**Before a read**, so you start from what your teammates learned. **After a write**, so a
session that ends does not take its findings with it.

Both directives are phrased as *before you read* and *after you write* rather than "at session
start" and "at session end" — an agent cannot reliably tell when a session begins or ends, but
it always knows what it is about to do. Instructions have to be written against actions the
model can actually observe itself taking.

A session-start hook makes the first one reliable where a harness offers one, but it must not
be the mechanism.

**Compliance will not be perfect, and that is acceptable.** An agent told to run `ctx sync`
sometimes will not. The failure is soft — you read facts that are a session stale — so it is
worth accepting rather than engineering around. Every mechanism that made skipping impossible
cost more than the staleness did.

### How ctx knows what changed

It diffs `facts.md` against the last-synced copy. A new key is an add; a changed value on an
existing key is an update.

**This is why the client model never has to classify its own writes.** An earlier draft had it
mark each write `add` or `update` and submit a structured claim — one more judgment for a weak
model to get wrong, replaced by a diff that cannot be wrong.

### ctx never updates itself unasked

The version check prints a line and stops. A tool that silently replaces its own binary — one
that agents invoke, inside an enterprise — is a supply-chain surprise waiting to happen. Same
boundary as not inlining `curl | sh` in `AGENTS.md`: tell the human, let them decide.

## The human view

The wiki half of the positioning. Two layers, and only one of them needs a model.

### The mechanical render needs no inference

Turning a fact list into a reference site is markdown-to-HTML plus grouping. Nothing to infer:

- `gateway.*` collapses into a **Gateway** section — the dotted keys already encode it
- every fact shows who last changed it and when, straight from version history
- anything past `review_by` renders greyed with a stale flag
- a client-side search box, because that is how reference docs are actually used

This regenerates on every write, so the human view is a byproduct rather than a chore.

**A good fact list already is good documentation** for the use case that dominates. Man pages,
API references, runbooks and FAQs are all fact lists, and they are what people reach for.
Nobody reads a narrative page to find the deploy command; they search for it. A list with good
keys beats prose at lookup, which is most of what wiki reads are.

The server renders because the wiki needs a URL; ctx can render to `.ctx/html/` for someone who
never publishes. Neither needs a model, which is what keeps the server runnable on the cheapest
box there is.

### The narrative layer, kept in step with the facts

What the mechanical render cannot do is narrative: "here is how our system works,
conceptually." That is generated by the **client's** model, so the expensive work lands on the
machine of whoever is already paying for a session, and the server stays model-free.

It is not a separate deliberate act. **When facts change, the narrative for those facts changes
with them**, in the same write. Docs that need remembering to regenerate are docs that are
always out of date.

The whole design of this rests on one decision:

**Sections are scoped to key prefixes, and only the changed section regenerates.**

```
## Gateway          ← regenerated, because gateway.* changed
## Deploy              ← untouched
## Event transport     ← untouched
```

Two things follow, and both matter:

**Latest-wins becomes safe.** A narrative is one blob with no keys, so whole-document
regeneration means every write is a wholesale replacement — a junior changing one fact would
replace a senior's good prose with worse prose, which is the original problem in a new costume.
Sectioning makes the unit small enough that writes do not collide, which is the same move that
made facts safe. One conflict rule for everything, no special case.

**It becomes affordable.** Regenerating one section on a fact write is a small call.
Regenerating the whole narrative every time anyone learns anything would be expensive enough
that people turn it off, and a feature people turn off is a feature that does not exist.

Versions still back it up: a bad section regeneration is one revert away, same as a bad fact.

Two smaller rules:

**Ordering within a section is derived, not generated.** The facts are the source and the prose
wraps them, so regeneration cannot reshuffle the document unpredictably and diffs stay readable.

**An orphaned section is flagged mechanically.** Delete every `gateway.*` fact and the
Gateway narrative is prose describing nothing. That check is deterministic — no model — and
it is the narrative equivalent of a stale flag.

**The render always shows the facts, with narrative as a wrapper — never instead of them.**

```
## Gateway

The gateway tier terminates client sessions and routes each one to a
portal based on source IP.

- **gateway-1.ip** — 10.2.3.5
- **gateway.routes-to** → portal tier, chosen by source IP
```

Generation is client-side, so narrative quality is whatever that client's model produced — good,
bad or indifferent, and the server cannot improve it without becoming a thing that needs a model.
That is an acceptable trade for prose, which is regenerable and self-heals the next time a better
model touches those keys. It is not acceptable if the prose can *contradict* the facts, because a
human browsing reads the prose and not the list. Keeping the facts visible directly beneath means
wrong prose is visibly arguing with something three lines below it, and the worst case becomes
prose someone ignores rather than prose someone believes.

**Diagrams as mermaid, not generated images.** Diagram-as-code is reviewable, diffable and
deterministic, and it cannot invent boxes that do not exist. A hallucinated architecture diagram
is worse than none, because it looks authoritative and nobody checks it. Mermaid text sitting in
the context is something a human can glance at and correct.

**Every node must trace back to a fact**, and that check is mechanical because mermaid is text.
Extract the node labels, match them against keys and values, flag what does not match:

```
⚠ diagram references 2 things with no facts: "Redis cache", "rate limiter"
```

This catches the real failure mode, which is not bad layout but confident invention — a model
asked to draw an architecture will happily add the components it assumes must be there.

**Diagram quality is decided by whether the facts capture relationships.** If every fact is
`thing.property — value` there is no structure to draw from and the model has to guess at the
arrows, which is precisely when it invents. Relationship facts make the diagram mostly draw
itself, which is why `instructions.md` should ask for them explicitly. They are more useful to
agents anyway.

**Diagrams get different staleness economics than prose.** A prose section regenerates when its
own keys change. A system-wide diagram spans every prefix, so any fact anywhere makes it stale,
and regenerating it per-write would be expensive and churny. So diagrams are **marked stale
immediately and regenerated on sync**. The node-tracing check is what makes that safe: a stale
diagram announces itself rather than quietly misleading.

**Why this does not reintroduce model or people weighting.** A better model produces better
prose in the sections it touches. No fact is outranked, no claim is weighted by who wrote it,
and nobody's section is protected from anyone else's. The asymmetry shows up only in writing
quality, which is where it is harmless.

## Trust states

Two, plus one derived.

| Marker | Meaning |
|---|---|
| *(none)* | Agent-written. The default, and most of the file. Useful, unconfirmed. |
| `[verified]` | A human settled it. A decision, not an observation — stop re-deriving it. |
| *stale* | Derived, not written: past `review_by`. Age is itself a claim about accuracy. |

`disputed` was cut along with the machinery that produced it. Under later-wins-plus-versions
there is no lasting contradiction to label — there is a current value and a history, and the
diff shows what changed. A state nothing sets is a state nothing should document.

`verified` is a marker rather than a lock. It does not block a write; it makes an agent think
twice and makes a change notification worth reading. Blocking would be wrong anyway, because
verified facts genuinely change — the IP really did move.

## Four decisions

**1. Retrieval, not preload.** The index is the product; everything else is plumbing. If
the index is good, the agent knows what exists and fetches correctly. If it is bad, no
amount of storage helps.

**2. `requires` is loaded, `related` is not.** Hard dependencies get pulled with the
context; pointers get listed. Cycles detected, token cost always printed. Without that
split, one fetch drags in half the company.

**3. Agents write freely, and every write is reversible.** Write-back is how this survives
contact with reality — every wiki dies of neglect, and capture-as-a-side-effect is the only
known cure. So writes are never blocked, never queued, never reviewed. What makes that safe
is not a gate but versions: any change can be undone, which is a far cheaper guarantee than
trying to decide in advance whether a change is good.

**4. No server required to start, and no server you cannot run yourself.** Local mode is
complete: your context persists between sessions with no account and no network, forever.
What a remote adds is sharing and durability — which does mean sharing structurally
requires a server, so **self-hosting is a commitment, not a maybe.** It is the only thing
standing between this and lock-in, and two choices are what make it credible: the format
stays plain markdown, and the server needs no model — it stores versioned lines of text,
runnable on the cheapest box there is.

## When an agent writes back

The instructions matter more than the mechanism. Most interesting things are not worth
keeping. Three triggers only:

- **A human corrected you.** Highest signal available — existing context was wrong or
  missing, and the right answer is in hand.
- **Something cost real effort to establish.** Expensive once means expensive again.
- **A decision and its reasoning.** Decisions decay fastest because the why never gets
  written down.

Never for task-specific detail, never for something inferred rather than verified.

**Write as you learn, not at session end.** Sessions get truncated, interrupted, or hit a
context limit. A fact learned at minute five and written at minute ninety is a fact that may
never get written at all.

**Record relationships, not just properties.** `gateway.depends-on → example-platform` is worth more
than three facts about gateway's configuration, because it is the kind of thing nobody writes
down and everybody needs. It is also what lets the architecture diagram draw itself instead of
being guessed at.

**Reuse an existing key rather than adding a second line.** If `deploy.command` is there and
now wrong, edit that line. Appending a second `deploy.command` makes the diff read as a
duplicate instead of an update, and leaves an agent two answers with no way to choose.

## Explicitly rejected

**Scoring people and weighting "smarter" users more.** Expertise is domain-scoped, not
scalar — the best distributed-systems engineer is not authoritative on the refund path.
Every proxy an LLM can compute (tenure, volume, confident phrasing) rewards the wrong
thing. The social cost of a tool that silently ranks colleagues is disqualifying. And it
addresses a rare problem.

What that idea actually wants is *whose claim wins* and *how much to trust this*. Both
come from ranking the **context**: ownership decides conflicts, state decides trust, usage
decides quality.

**A server-side AI that judges whether a change is good enough to accept.** It has no
ground truth, so it selects for confident prose, and it recreates the review queue as a
robot nobody can argue with.

**A server-side AI that merely detects contradictions.** Narrower and technically sound, but
it puts a model dependency in every self-hosted install, and "bring an API key to run your own
context server" would stop most people from running one.

**Keyed JSON claims with supersede pointers, evidence fields, corroboration counts and a
per-claim `op`.** An elaborate reimplementation of version history. Kept in this list because
it took a while to see that, and the lesson generalises: when a design starts growing fields
to remember what used to be true, it wants versions.

**Prose alongside the facts.** It forced two merge policies in one file, and the best answer
available for the prose half was section-level clobbering. One kind of content, one policy.

**Recording which model wrote a fact.** Genuinely useful for diagnosis, but a field that
exists gets used, and weighting facts by model is user-scoring wearing a hat.

**Merging `ctx remote` into `sync`.** Tempting — one verb for talking to the remote, first call
configures it. But it makes the routine, automatable command the one that first exposes your
data, and a session-start hook would create a remote for a local-only context with nobody having typed
anything.

**Session memory.** Continuity between sessions is a real problem and a different one.
`ctx` should not pretend to solve it.

**A render command.** HTML regenerates on write. A documentation site that needs a command
to rebuild is a documentation site that is out of date.

## Distribution

Two install paths, and they need different answers about staying current.

**Homebrew: nothing to build.** `brew upgrade ctx` is what users already expect, and Homebrew
refreshes its formula index on most commands, so they find out on their own. The only work is
publishing the formula, which release tooling can do on every tag.

**curl-installed: notify, plus an explicit `ctx upgrade`.** This is the settled pattern for
tools that ship outside a package manager — rustup, Deno, uv and Bun all do exactly this. The
installer drops a binary at a known path and the tool knows how to replace it when asked.

**The version check costs nothing**, which is what makes it worth having: ctx already talks to
the server on sync, so the response carries the latest version and ctx prints a line. No extra
request, no telemetry, no phone-home to justify.

```
$ ctx sync
example-project        2 facts updated by alex

ctx 0.4.1 available (you have 0.3.2) — `ctx upgrade`
```

### Four guardrails on the update check

This is where auto-updaters normally go wrong, so all four are requirements rather than
niceties:

- **Silent when stdout is not a TTY.** An agent parsing `ctx sync` must never receive an
  upgrade nag mixed into the output it is reading.
- **Silent when `CI` is set.** A build that changes its own tool versions is not reproducible.
- **`CTX_NO_UPDATE_CHECK=1`** disables it outright.
- **Enterprises will pin and distribute their own way** — internal package repo, or a container
  image. The updater has to be optional and never the only path, or it becomes a reason for a
  security review to say no.

### Language is a distribution decision

The prototype is a single Python file with no dependencies, which is the right thing to think
in. It is the wrong thing to hand to strangers: they need a Python, and self-update means
replacing a script plus whatever it imports.

A single static binary makes every part of this easier — one file to download, one file to
swap, and `brew`, `scoop` and `curl` all become trivial. Release tooling in that ecosystem
builds the binaries, cuts the GitHub release and updates the Homebrew tap from one config.

So the language choice is about distribution, not coding preference. Python to find out whether
the design is right; a static binary before anyone else installs it.

## Build order

1. **Local only.** Use it on a real repo for a fortnight. This has to be worth running
   with no server at all, or nothing downstream matters.
2. **Remote, one team.** Publish and clone against a server, self-hosted first because it
   is the simpler thing to stand up. The question it answers: does anyone but the author
   ever write a context?
3. **ctxhub.** Only if step 2 produced anything worth hosting.

Building the hub first is a platform with nothing on it and no evidence anyone wants to put
anything there.

**The static-binary rewrite belongs between steps 1 and 2**, not before step 1. Step 1 is one
person finding out whether the design is right, and a Python file is faster to change. Step 2
is the first time someone else installs it, which is the moment distribution starts mattering
more than iteration speed.

## The thing that decides whether this works

Not the storage, the sync, or the hub. **Whether the one-line summaries are good.** A bad
summary means the agent never fetches the context, and an unfetched context may as well
not exist. No tooling fixes that — it is a writing problem, and it is the only real risk.

## Open source, and one hosted instance

Client and server are both open source, and anyone can run their own. One canonical
instance runs on the internet — the github.com of this, if the analogy helps — and that is
the one with the network effects.

Two consequences to be clear-eyed about rather than discover later:

**You cannot charge for the software, only for running it.** An enterprise that hits a
paywall will self-host, and the honest answer is "good, that was the deal." So the paid
tier has to be about the hosted instance: uptime, not thinking about it, and the network
effects below. Never about a licence term.

**Licensing needs deciding before contributors arrive.** Fully permissive on the server
means a cloud provider can offer hosted ctx and out-distribute the people who built it. The
standard defence is a permissive client with AGPL or BSL on the server. Relicensing after
other people have committed code is painful, so this is an early decision, not a later one.

## Where the paid line goes

Free for individuals and small teams, paid for enterprises. The org is the tenant and
therefore the billing boundary, which the namespace already gives us.

**Not metered on headcount.** Employee count cannot be observed, cannot be verified, and
has no relationship to what the service costs to run — metering on it means asking
enterprises to self-report and trusting them. Every company that meters successfully meters
on something it can see.

The gate does not need to be a number at all. The enterprise feature list below
self-selects: a company large enough to matter needs SSO and audit long before any
threshold would bite, and nobody argues about whether they need SSO. That is a cleaner line
than a figure that invites argument and cannot be checked.

The line has to be drawn so that **nothing which drives adoption is ever gated**. The
format, the CLI, local mode, self-hosting, unlimited contexts, unlimited people in a free
org — all permanently free. If an enterprise can self-host this and never pay, let them;
they were never going to pay, and their usage still grows the format. That is the deal that
made git and GitHub work.

### Never gate

- **The format.** Plain markdown. If contexts are only readable by paid software, nobody
  adopts and no enterprise will risk the lock-in.
- **Self-hosting.** Since sharing now requires a server, gating the ability to run your own
  makes the whole thing lock-in. This is the replacement for "you can always just use git".
- **Context count.** Charging per context taxes exactly the behaviour the product needs.
- **Seats.** Punishes the org for rolling it out, and pushes people to share accounts.
- **Write-back.** Capture is the flywheel. Making it a paid feature kills it.

### What enterprises pay for

Things a git repo structurally cannot do, so the gate is real rather than artificial:

- **SSO/SAML and SCIM.** The classic enterprise line. Nobody else wants it, every
  enterprise requires it, and it is genuinely work to build.
- **Write-side telemetry.** Which contexts are cloned and synced, which facts churn, which
  have sat untouched past `review_by`. Churn is the interesting one: a fact rewritten every
  other week is either an unstable system or a fact nobody can pin down, and both are worth
  a human looking at.

  **Not reads.** Because the agent opens `facts.md` directly, nothing reports a read — not
  the server, not ctx. An earlier draft claimed read telemetry as an enterprise feature; that
  died with the decision to make reads plain file operations, and it is worth recording as a
  real cost of that choice rather than quietly dropping. Recovering it would mean routing
  reads through ctx, which is the trade already rejected.
- **Access control below repo granularity.** Some contexts are sensitive in ways that do
  not map to "who can clone this".
- **Audit.** Who changed what context, when, and who settled it.
- **Cross-org sharing — the actual moat.** A vendor publishing context that its customers
  pull, so `vendor-org:shared-sso` appears in Example-org's index. This only works on the instance
  everyone is already on, which makes it the one asset a self-hoster cannot reproduce and
  worth more than any feature gate. The roadmap should aim at it.
- **Private orgs, self-hosting, SLA.**

### Sequencing

Pricing is downstream of adoption, and adoption is unproven. The order stays: use it
locally, then one team on git, then a hub — and think about pricing when there is
something to charge for. Designing the paywall before the product has users is the most
common way this kind of tool dies.
