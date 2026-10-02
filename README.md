# KeepCTX

**Keep one context. Every session, every AI, every teammate.**

Every AI session starts blind. You re-explain the same things — what the project is for, how
to log in to your servers, where the logs live, what was decided last week and why. KeepCTX
keeps it as a list of facts: your agent remembers each one as it learns it, the next session
starts knowing, Codex and your other AI agents know what Claude learned, and because the facts
live in git next to your code, your team gets them too.

```sh
curl -fsSL https://keepctx.com/install.sh | sh
cd ~/work/example-project && ctx init
git add .ctx AGENTS.md && git commit -m "Add KeepCTX"
```

That's it. No account, no server, no network.

The command is `keepctx`; `ctx` is a short alias and what you'll actually type. If another
project's `ctx` is already on your PATH the alias is skipped, and `keepctx` works the same.

---

## How it works

A context is a list of facts in one file, `.ctx/context.jsonl`, committed with your code. Your
agent works through `ctx`: it reads everything with `ctx get`, and changes it with
`ctx remember` and `ctx forget` the moment it learns something:

```sh
ctx remember environments logs.location "Splunk, index app_prod. Not CloudWatch."
KeepCTX: remembered environments.logs.location — Splunk, index app_prod. Not CloudWatch.
```

Every line starting with `KeepCTX:` is passed on to you by the agent, so you always see what's
kept.

`AGENTS.md` is only the doorway. `ctx init` adds a short pointer to the top of it — the file
Claude Code, Codex and most other agents already read — telling the agent to start every
session with `ctx ai`, which prints the rules and then the whole context. **Nothing you wrote
in `AGENTS.md` is touched.** Switch tools and nothing is lost.

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

Never secrets — the file is committed, and `ctx` refuses anything shaped like a key or token —
never what you put off the record, and never the conversation itself. Musing isn't deciding:
"maybe Postgres?" is a question, not a decision.

It isn't only for code. An investing context holds your thesis, sizing rules and what you've
ruled out; a book's holds characters, voice and what's canon; a business's holds customers,
pricing and tone. Anything you keep re-explaining to an AI is a context.

The agent's rules come from `ctx ai`, made fresh by the installed CLI every time, so they
never go stale. Run it yourself to see exactly what your agent is told.

## Sharing, through git

The context is shared the way your code is. Commit it, and teammates get it when they pull;
history, blame, review and revert all work as they do for anything else.

The file has one fact per line, sorted by key, and KeepCTX teaches git to **merge it fact by
fact**. Git's normal merge goes line by line and calls two changes on neighbouring lines a
conflict, which in a small sorted file would be almost every change. With the KeepCTX merge:

- Two people adding, changing or removing **different** facts never conflict.
- Only the **same** fact changed two different ways needs someone to choose, and git marks
  just that one fact.

`.ctx/.gitattributes` (committed) tells git to use the KeepCTX merge for the file, and
`ctx init` / `ctx ai` set it up in each clone's git config. A clone without `ctx` installed
falls back to git's normal merge.

## Commands

Plain `ctx` lists only what people need, and points at `ctx ai`, where the agent learns the
rest.

| | |
|---|---|
| `ctx` | status |
| `ctx init` | set up here — then commit `.ctx/` |
| `ctx ai` | where your agent starts every session: the rules, then the whole context |
| `ctx get` | print the whole context |
| `ctx remember <category> <key> "<value>"` | add a fact, or change it |
| `ctx forget <category> <key>` | remove a fact |

## A server, later

`server/` (and `web/app.*`) hold a sync server — accounts, orgs, a console, self-hosting —
from an earlier version. It's paused: the CLI doesn't use it. If contexts that span repos, or
live outside one, turn out to matter, sync can come back on top of the same file.

## Design

[`DESIGN.md`](DESIGN.md) is the long version — what was decided, and what was rejected and
why. The rejected list is the useful half.

## License

Apache-2.0.
