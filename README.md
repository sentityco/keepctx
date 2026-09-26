# keepctx

**Your AGENTS.md, except it writes itself — and your team shares it.**

Every AI session starts blind. You re-explain the same things — which queue you use, why
the docs are wrong, what actually deploys. `ctx` captures that as your agent works, keeps
it current, and shares it with your team.

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
repo, a service, a team, a programme, a platform. keepctx doesn't impose a shape:

```markdown
- **deploy.command** — `make ship` from the repo root, not the platform CLI
- **logging.index** — `app_prod_v2`. The docs still say app-prod; they're wrong.  `[verified]`
- **gateway.depends-on** → example-platform, for session validation
- **event.transport** — Kinesis, not Kafka. Inherited, and we're not changing it.  `[verified]`
```

Your agent reads and edits that file directly, using the same tools it uses for any other
file. There's no write command to forget and no ceremony to skip — which is exactly why
capture actually happens.

`ctx init` adds two lines to the top of your `AGENTS.md` pointing at the rules, and
**nothing you wrote there is touched.** Uninstalling is deleting those two lines.

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
