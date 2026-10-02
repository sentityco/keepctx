# KeepCTX

**Keep one context. Every session, every AI, every teammate.**

Every AI session starts blind. You re-explain the same things — what the project is for, how
to log in to your servers, where the logs live, what was decided last week and why. KeepCTX
gives your project one file where your AI writes those things down as it learns them, and
reads them back at the start of every session.

```sh
curl -fsSL https://keepctx.com/install.sh | sh
cd ~/work/your-project && ctx init

# optional: commit KEEPCTX.md so teammates and their AI agents see and update the context too
git add KEEPCTX.md AGENTS.md && git commit -m "Add KeepCTX"
```

That's all. Open source, no account, no server.

## What `ctx init` does

1. Creates **`KEEPCTX.md`** in your project — a plain Markdown file with a heading per
   category, and the rules for keeping it at the top.
2. Adds a short pointer to the top of **`AGENTS.md`**, the file Claude Code, Codex and most
   other agents already read: *read `KEEPCTX.md` at the start of every session and keep it
   current; if it's missing, ignore this and carry on.* Nothing else in `AGENTS.md` is
   touched.

From then on your AI reads and edits the file like any other. **Nobody needs KeepCTX
installed** — not your teammates, not their agents. The rules travel inside the file.

## What it looks like

```markdown
## Environments
_Hosts, deployment environments, service names, versions and access. Never secrets._

- **logs.location** — Splunk, index app_prod. Not CloudWatch.
- **prod.access** — SSO, then the bastion host. Never direct SSH.

## Decisions
_What was chosen and why, and what was considered and rejected._

- **storage** — SQLite: one file to back up, no database server to run
- **rejected.postgres** — a server to operate for a few megabytes of text
```

Whenever the AI changes the file, it tells you in one line:
`KeepCTX: added to Decisions — storage: SQLite` (or "updated in", "removed from").

## The categories

Overview · Requirements · Architecture · Environments · Decisions · Questions · Conventions ·
Operations · Testing · Knowledge · People

A wide net: not just how things run, but what's being built and why. Never secrets, never
what you put off the record. It isn't only for code — anything you keep re-explaining to an
AI belongs in a context.

## Sharing

It's a file in your repo, so it's shared the way your code is: commit it, and teammates get it
when they pull. History, review and revert work as they do for everything else.

## Contributing

`src/keepctx.py` is the whole tool: one file, standard library only. The template and the
rules in it are the product, so changes to them matter most. See
[`CONTRIBUTING.md`](CONTRIBUTING.md), and [`DESIGN.md`](DESIGN.md) for why it's this simple.

## License

Apache-2.0.
