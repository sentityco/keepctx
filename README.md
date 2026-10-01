# KeepCTX

**Keep your AI context — across sessions, across AIs, across your team.**

Every AI session starts blind. You re-explain the same things — what the project is for, how
to log in to your servers, where the logs live, what was decided last week and why. KeepCTX
keeps it as facts: your agent remembers each one as it learns it, the next session starts
knowing, Codex and your other AI agents know what Claude learned, and your team gets it too.

```sh
curl -fsSL https://keepctx.com/install.sh | sh
cd ~/work/example-project && ctx init
```

That's it. Local, no account, no network. An account only matters when you want to share.

The command is `keepctx`; `ctx` is a short alias and what you'll actually type. If another
project's `ctx` is already on your PATH the alias is skipped, and `keepctx` works the same.

---

## How it works

A context is a list of facts, grouped by category in one file. Your agent works through
`ctx`: it reads everything with `ctx get`, and changes it with `ctx remember` and
`ctx forget` the moment it learns something:

```sh
ctx remember environments logs.location "Splunk, index app_prod. Not CloudWatch."
KeepCTX: remembered environments.logs.location — Splunk, index app_prod. Not CloudWatch.
KeepCTX: pushed 48 facts to https://keepctx.com (v13)
```

Every line starting with `KeepCTX:` is passed on to you by the agent, so you always see what's
kept and synced.

`AGENTS.md` is only the doorway. `ctx init` adds a short pointer to the top of it — the file
Claude Code, Codex and most other agents already read — and the pointer sends them to KeepCTX.
**Nothing you wrote there is touched.** Switch tools and nothing is lost. To uninstall, delete
`.ctx/`; the pointer can stay, since it tells agents to carry on when `.ctx/` is missing.

## What goes in a context

A wide net: not only how things run, but what's being built and why — everything you'd tell a
sharp new teammate. The categories:

| | |
|---|---|
| **overview** | what this is, why it exists, who it's for, what success looks like |
| **requirements** | what it must and must not do, and what's in and out of scope |
| **architecture** | services, components, dependencies and data flows |
| **environments** | hosts, deployment environments, service names, versions, access |
| **decisions** | what was chosen and why, and what was rejected |
| **questions** | what's still undecided, until a decision settles it |
| **conventions** | patterns to follow, and what not to touch |
| **operations** | build, deploy, runbooks, troubleshooting |
| **testing** | how to test, what passing means, what isn't covered |
| **knowledge** | gotchas, domain facts, vocabulary no model could guess |
| **people** | who owns what, who to ask, how they like to work |

Never secrets — `ctx` and the server both refuse anything shaped like a key or token — never
what you put off the record, and never the conversation itself. Musing isn't deciding: "maybe
Postgres?" is a question, not a decision.

It isn't only for code. An investing context holds your thesis, sizing rules and what you've
ruled out; a book's holds characters, voice and what's canon; a business's holds customers,
pricing and tone. Anything you keep re-explaining to an AI is a context.

The agent's rules live in `.ctx/instructions.md`, which `ctx` writes and keeps current.

## Sharing, pulling and pushing

`ctx remote` puts a context on a server. After that:

- **Every `ctx remember` and `ctx forget` is pushed straight away**, so a session that ends
  abruptly loses nothing.
- **The agent runs `ctx pull` at the start of each session.** It downloads the latest into
  `.ctx/<name>/remote/`, kept by version, and merges it into the local facts **fact by fact**.
- **A fact changed on one side is simply taken.** A fact changed differently here and on the
  server is a conflict: `ctx pull` names it, the agent compares `ctx get` with
  `ctx get --remote`, settles just that fact with `ctx remember` or `ctx forget`, and pushes.
  Everything else was already merged.
- **A push is accepted only from the latest version.** If the server moved on, `ctx` pulls and
  merges first, so nobody overwrites what they never saw.
- **Every push is a version on the server** — a bad change is one revert away in the console.

A context is **written by its owner** — whoever ran `ctx remote` — **and the org's admins.
Everyone else in the org reads it.** Add teammates to your org in the
[console](https://keepctx.com/app.html); then, in their checkout:

```sh
ctx clone your-org:your-context
```

They get a read-only copy that `ctx pull` keeps current. The same command gives you a writable
copy on another machine. Run beside an existing context, it brings the other one in as a
read-only reference that `ctx get` shows after the context's own facts.

## What people see

Open a context in the console and it reads by category, each with its facts, and an
architecture diagram drawn from the `→` relationship facts — so it shows only what's recorded.
It's all drawn in the browser; the server stores text and never needs a model, so a
self-hosted server shows exactly the same page.

## Why not just commit it

Code is correct relative to a commit. Context is a claim about the world *right now*.
Versioning it by branch means a context that's right on `main` is wrong on a two-week-old
feature branch, and every agent write becomes a diff in someone's pull request.

So `.ctx/` ignores itself — it contains a `.gitignore` holding `*`, which works whether or
not git exists yet, and keeps working if you run `git init` next week.

## Commands

| | |
|---|---|
| `ctx` | status |
| `ctx init [name]` | set up here. local, no account, no network |
| `ctx get [--remote]` | print the whole context — or the copy the last pull downloaded |
| `ctx remember <category> <key> "<value>"` | add a fact, or replace it |
| `ctx forget <category> <key>` | remove a fact |
| `ctx remote [server]` | put this on a server — shares it and backs it up |
| `ctx clone org:name [server]` | bring a context here from a server |
| `ctx pull` | bring in the latest and merge it, fact by fact |
| `ctx push` | send what's here — done for you after every remember |

A value starting with `→` is a relationship: `ctx remember architecture api.depends-on "→
auth-service"`. The name of a context defaults to your directory, slugified; it only has to be
unique when you run `ctx remote`.

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

The server is deliberately **model-free**: storage and version history, with the merge done by
the client. `server/handler.py` is the same code keepctx.com runs on Lambda and DynamoDB;
`serve.py` runs it on SQLite instead. Auth is email + password with PBKDF2 and HMAC-signed
tokens — stdlib only, no Cognito, no vendor dependency. Self-hosting is a commitment here, not
a maybe: it's the only thing standing between this and lock-in.

## Design

[`DESIGN.md`](DESIGN.md) is the long version — what was decided, and what was rejected and
why. The rejected list is the useful half.

## License

Apache-2.0.
