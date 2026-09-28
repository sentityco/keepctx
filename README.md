# keepctx

**Your AGENTS.md, except it writes itself — shared across sessions, across AI tools, and
across your team, on our server or your own.**

Every AI session starts blind. You re-explain the same things — how to log in to your
servers, where the logs live, what runs where. `ctx` captures that as your agent works and
keeps it current. Next session remembers it, Codex and your other AI agents know what Claude
learned, and your team gets it too.

```sh
curl -fsSL https://keepctx.com/install.sh | sh
cd ~/work/example-project && ctx init
```

That's it. Local, no account, no network. An account only matters when you want to share.

The executable is `keepctx`; `ctx` is a short alias and what you'll actually type. If another
project's `ctx` is already on your PATH the alias is skipped, and `keepctx` works the same.

---

## What it does

A context is a list of facts in plain markdown. **What a context covers is up to you** — a
repo, a service, a team, a platform, or something that isn't software at all:

```markdown
- **prod.access** — SSO, then jump host `bastion.example.com`, then `aws --profile prod-ro`. Never direct SSH.  `[verified]`
- **network.proxy** — internal hosts only resolve through the corporate proxy; set `HTTPS_PROXY` first
- **logs.location** — Splunk, index `app_prod`. Not CloudWatch, whatever the old runbook says.
- **api.runs-on** → Cloud Foundry (`cf logs api --recent`), not Kubernetes
- **api.depends-on** → auth-service, for session validation
```

Your agent reads and edits that file directly, using the same tools it uses for any other
file. There's no write command to forget and no ceremony to skip — which is exactly why
capture actually happens.

Because it's plain markdown behind `AGENTS.md`, every AI agent that reads that file — Claude
Code, Codex and the rest — shares the same context. Switch tools and nothing is lost.

`ctx init` adds a short pointer to the top of your `AGENTS.md`, and **nothing you wrote
there is touched.** To uninstall, delete `.ctx/`. The pointer can stay: it tells agents to
carry on without context when `.ctx/` is missing. Delete it too if you want a clean file.

## What goes in a context

Everything you'd tell a sharp new teammate on day one — anything that would belong in an
`AGENTS.md`, kept current instead of written once:

| | |
|---|---|
| **Intent** | goals, requirements, decisions, what was considered and rejected, what's still open |
| **Purpose** | why this exists, what value it gives, and who it's for |
| **Parts & design** | what it's made of — components, stack, tools — and the shape it's meant to have |
| **Conventions** | naming, structure, workflow, the idioms *this* place uses |
| **How** | build, test, deploy, operate — the exact commands, done the way *this* place does them |
| **Where** | where things run and live, and where to look — logs, dashboards, files |
| **Vocabulary** | internal names no model could guess |
| **Gotchas** | what looks wrong but is intentional, and what looks right but breaks |
| **Sources of truth** | which doc wins when two disagree |
| **Decisions** | what was chosen, why, and what was ruled out |
| **Rules & boundaries** | standards, compliance, budgets, never-do-X, what not to touch |
| **People & access** | who owns what, who to ask, how they like to work, how to get in — never the credentials |

It isn't only for code. An investing context holds your thesis, sizing rules and what you've
ruled out; a book's holds characters, voice and what's canon; a business's holds customers,
pricing and tone. Anything you keep re-explaining to an AI is a context.

The agent's rules for this live in `.ctx/instructions.md`, which `ctx init` writes. It
captures everything worth knowing from your work together — not the conversation, and never
secrets or anything you put off the record — and says `noted: <key>` whenever it writes.

## What people see

Open a context in the console and it reads as a site, not a list: an overview, an
architecture diagram, goals, requirements, decisions, what was rejected, open questions, then
each area of the system, then a journal of how it got this way.

- **Prose** is written by the agents, one short section per area, in `.ctx/<name>/prose/`.
  The facts always sit beneath it, and a section whose facts changed after it was written is
  flagged until the next agent working there rewrites it.
- **The diagram** is drawn from the `→` relationship facts, so it shows only what's recorded.
- **The journal** is a dated entry per stopping point — `ctx journal "..."` — for teammates
  who weren't there.

All of it is drawn in the browser. The server stores text and never needs a model, so a
self-hosted server shows exactly the same page.

## Why not just a wiki

Wikis die of low read volume: a page nobody opens is a page nobody notices is wrong. An
agent reads context every session, which is what surfaces errors — and the correction gets
captured at the moment someone has the right answer in hand.

## Why not just commit it

Code is correct relative to a commit. Context is a claim about the world *right now*.
Versioning it by branch means a context that's right on `main` is wrong on a two-week-old
feature branch, and two people editing one context on different branches produce a prose
merge conflict neither can resolve from a diff.

So `.ctx/` ignores itself — it contains a `.gitignore` holding `*`, which works whether or
not git exists yet, and keeps working if you run `git init` next week.

## Sharing

A context on the remote is **written by its owner** — whoever ran `ctx remote` — **and the
org's admins. Everyone else in the org reads it.** Add teammates to your org in the
[console](https://keepctx.com/app.html); then, in their checkout:

```sh
ctx clone your-org:your-context
```

They get a read-only copy that `ctx sync` keeps current. The same command gives you a
writable copy on another machine. Run beside an existing context, it brings the other one in
as a read-only reference.

Opening writes to the whole team is planned; for now, one writer keeps it simple.

## Conflicts

Your copies sync **per key, not per file**.

- Two copies change different facts → both land.
- Two copies change the same fact → the later sync wins.
- A fact deleted in one copy is deleted in the others.
- Every sync is a version on the server → a bad change is one revert away.

That's the whole conflict model. Nothing is ever destroyed, so nobody has to arbitrate.

## Commands

| | |
|---|---|
| `ctx` | status |
| `ctx init [name]` | set up here. local, no account, no network |
| `ctx remote [server]` | put this on a remote — shares it and backs it up |
| `ctx clone org:name [server]` | bring a context here from the remote |
| `ctx sync` | send your changes, bring in the latest |
| `ctx journal "..."` | add a dated entry: what was done, decided, left open |

The name defaults to your directory, slugified. It only has to be unique when you run
`ctx remote`, which is where it gets validated.

## Self-hosting

Your own server looks and works exactly like keepctx.com — the same console, the same API —
on one port, stored in one SQLite file. Python 3.9+, no dependencies, no AWS:

```sh
curl -fsSL https://keepctx.com/server.sh | sh
keepctx-server                      # http://127.0.0.1:8080  (--host, --port, --data)
```

It speaks plain HTTP, so put HTTPS in front before anyone signs in over a network. With
Caddy that's one line:

```sh
caddy reverse-proxy --from keepctx.sample-company.com --to :8080
```

Make the first account and an org in its console, then name the server when you share or
clone — everything after that remembers it:

```sh
ctx remote https://keepctx.sample-company.com
ctx clone team:proj https://keepctx.sample-company.com
```

A bare `keepctx.sample-company.com` works too; HTTPS is assumed. A directory syncs with one
server, because its sign-in belongs to that server.

Reinstalling replaces the code and never touches the data, which lives in
`~/.local/share/keepctx-server/data`: the database, and the secret that signs sign-ins.
Back up that directory and you've backed up everything.

The server is deliberately **model-free**: storage, a keyed merge, and version history.
`server/handler.py` is the same code keepctx.com runs on Lambda and DynamoDB; `serve.py`
runs it on SQLite instead. Auth is email + password with PBKDF2 and HMAC-signed tokens —
stdlib only, no Cognito, no vendor dependency. Self-hosting is a commitment here, not a
maybe: it's the only thing standing between this and lock-in.

## Design

[`DESIGN.md`](DESIGN.md) is the long version — what was decided, and what was rejected and
why. The rejected list is the useful half.

## License

Apache-2.0.
