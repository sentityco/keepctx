# keepctx

**Your AGENTS.md, except it writes itself — shared across sessions, across AI tools, and
across your team.**

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

Everything you'd tell a sharp new teammate on day one:

| | |
|---|---|
| **Purpose** | why this exists, and who it's for |
| **Parts** | what it's made of — components, stack, tools |
| **Where** | where things run and live, and where to look — logs, dashboards, files |
| **How** | the routines, done the way *this* place does them — deploy, operate, maintain |
| **Vocabulary** | internal names no model could guess |
| **Gotchas** | what looks wrong but is intentional, and what looks right but breaks |
| **Sources of truth** | which doc wins when two disagree |
| **Decisions** | what was chosen, why, and what was ruled out |
| **Rules** | standards, compliance, budgets, never-do-X |
| **People & access** | who owns what, who to ask, how to get in — never the credentials |

It isn't only for code. An investing context holds your thesis, sizing rules and what you've
ruled out; a book's holds characters, voice and what's canon; a business's holds customers,
pricing and tone. Anything you keep re-explaining to an AI is a context.

The agent's rules for this live in `.ctx/instructions.md`, which `ctx init` writes.

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

## Conflicts

Changes sync **per key, not per file**.

- Two people learn different things → both land.
- Two people change the same fact → the later one wins.
- Every sync is a version on the server → a bad change is one revert away.

That's the whole conflict model. Nothing is ever destroyed, so nobody has to arbitrate.

## Commands

| | |
|---|---|
| `ctx` | status |
| `ctx init [name]` | set up here. local, no account, no network |
| `ctx remote` | put this on a remote — shares it and backs it up |
| `ctx clone org:name` | get a remote context you don't have |
| `ctx sync` | upload local changes, download remote ones |

The name defaults to your directory, slugified. It only has to be unique when you run
`ctx remote`, which is where it gets validated.

## Self-hosting

The server is in [`server/`](server/) — a single Lambda handler plus a DynamoDB table. It
is deliberately **model-free**: storage, a keyed merge, and version history. Nothing in it
needs inference, so it runs on the cheapest box there is.

Point the CLI anywhere with `CTX_REMOTE`:

```sh
CTX_REMOTE=https://ctx.internal.example.com ctx sync
```

Auth is email + password with PBKDF2 and HMAC-signed tokens — stdlib only, no Cognito, no
vendor dependency. Self-hosting is a commitment here, not a maybe: it's the only thing
standing between this and lock-in.

## Design

[`DESIGN.md`](DESIGN.md) is the long version — what was decided, and what was rejected and
why. The rejected list is the useful half.

## License

Apache-2.0.
