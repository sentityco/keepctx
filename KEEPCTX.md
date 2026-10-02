# Project Context

This file is this project's memory: what it is, why, how it's built and run,
what has been decided, and what is still open. Every AI agent and every person
working on the project reads it. **AI agents: read all of it at the start of
every session, and keep it current as you work, by these rules.**

## How to keep this file

- **One fact per line**, under the heading it belongs to: `- **key** — value`.
  Keys are short and lowercase (`server-a.ip`, `deploy.command`). Values are one
  line that a newcomer would understand.
- **Write it down the moment you learn it** — a session can end at any time.
  Worth keeping: goals and requirements the user states; decisions, once the
  user commits, with the reason; options turned down, under Decisions as
  `rejected.<name>`, with why; open questions; corrections; anything that took
  real effort to find out; how things are built, run, tested and deployed.
- **Musing is not deciding.** "Maybe Postgres?" is a question, not a decision.
- **Change a fact by editing its line**, never by adding a second one. Delete a
  line when it's no longer true, and a question once a decision settles it.
- **Leave other facts alone** unless they're wrong or the user asks.
- **Never** write secrets (passwords, tokens, keys), anything the user says is
  off the record, opinions about people, or the conversation itself. This file
  is committed with the code.
- **Tell the user** in one line whenever you change this file, e.g.
  `KeepCTX: added to Decisions — storage: SQLite` (or "updated in", "removed from").
- **A merge conflict here** almost always means both sides added facts: keep both.

## Overview
_What this is, why it exists, who it's for, and what success looks like._

- **what** — a convention plus one command: `keepctx init` creates `KEEPCTX.md`, a Markdown file of facts with its rules at the top, and points `AGENTS.md` at it
- **users** — anyone working with AI agents on a project, alone or with a team; not only code
- **tagline** — Keep one context. Every session, every AI, every teammate.

## Requirements
_What it must and must not do, and what is in and out of scope._

- **no-install** — nothing may depend on KeepCTX being installed; anyone who clones a repo must be able to read and keep the context with no tool
- **stdlib** — `src/keepctx.py` is one file, Python 3.9+, standard library only

## Architecture
_Services, components, dependencies and data flows: what connects to what._

- **cli** — `src/keepctx.py`: `keepctx init`, the template and its rules; that is the whole tool
- **installer** — `install.sh` downloads `src/keepctx.py` from GitHub at main's exact commit into `~/.local/bin/keepctx`; it also removes the `ctx` alias older versions installed
- **site** — `web/index.html` and `web/style.css`, static, no build step

## Environments
_Hosts, deployment environments, service names, versions and access. Never secrets._

- **site** — https://keepctx.com: S3 bucket `ctxhub-site-975050072453` behind CloudFront `E1FU0K7RDCME20`
- **repo** — https://github.com/sentityco/keepctx
- **old-server** — Lambda `ctxhub`, its API Gateway and DynamoDB table `ctx` are still running though nothing uses them (code tagged `server-archive`)

## Decisions
_What was chosen and why, and what was considered and rejected._

- **simple** — the product is the file and its rules; the CLI only sets it up, because it must work for people who never installed it
- **markdown** — every agent and person can read and edit it with nothing installed, and it renders on GitHub
- **one-file** — `KEEPCTX.md` at the project root, not a folder; the pointer says to carry on if it's missing
- **no-gitattributes** — merge conflicts in the file are rare, and the rules say what to do: keep both
- **rejected.server** — a sync server, accounts and console: most of the code, and needed the tool everywhere (tagged `server-archive`)
- **rejected.agent-commands** — `ctx ai` / `remember` / `forget` / `pull` / `push`: an agent without KeepCTX installed couldn't use them

## Questions
_What is still undecided. Deleted once a decision settles it._

- **old-server** — tear down the unused Lambda, API Gateway and DynamoDB table?

## Conventions
_Patterns future developers and agents should follow, and what not to touch._

- **name** — KeepCTX in prose; `keepctx` is the command (the `ctx` alias was dropped)
- **rules** — the template's rules are the product; most changes should be to their wording

## Operations
_Build, deploy, runbooks, troubleshooting and recurring operational details._

- **release** — push to `main`; the installer always fetches main's latest commit
- **deploy** — pushing does not deploy the site; run `./deploy.sh` after changing `web/` or `install.sh`

## Testing
_How to test, what passing means, and what is not covered._

- **command** — `python3 tests/test_cli.py`; no network needed

## Knowledge
_Gotchas, domain facts and vocabulary nobody outside would know._

## People
_Who owns what, who to ask, and how they like to work._

- **owner** — Jason (Sentity)
