# KeepCTX

Keep one context. Every session, every AI, every teammate. See `DESIGN.md` for why things are
the way they are; it is long, and the **Explicitly rejected** section is the
useful half.

## Constraints that are not negotiable

- **`src/keepctx.py` is one file, standard library only.** No dependencies. This is
  what makes the installer a `curl` and the code readable in one sitting.
- **Nothing may depend on KeepCTX being installed.** The product is `.ctx/context.md`, a
  Markdown file whose rules are at its top; `ctx init` only creates it and points
  `AGENTS.md` at it. `server/` and `web/app.*` are a paused sync server; keep its tests
  passing, but the CLI must not depend on it.
- **`web/` has no build step and no framework.**
- **No per-agent integrations.** No hooks, plugins, or config for Claude Code,
  Cursor, Copilot or anything else. `AGENTS.md` is the integration. ctx prints
  to stdout, which works for any agent that can run a shell command.

## Before proposing a change

Read the rejected list in `DESIGN.md`. Several reasonable-sounding ideas have
already been tried and discarded — scoring users, a server-side AI that judges
whether a change is good enough, keyed JSON claims with supersede pointers,
prose alongside the facts. Each records why. Arguing against the recorded
reasoning is welcome; re-proposing it without reading is not.

## Testing

```sh
python3 tests/test_cli.py      # ctx init: the template and the AGENTS.md pointer
python3 tests/test_server.py   # the paused server: accounts, orgs, who can read and write
python3 tests/test_serve.py    # the paused server, self-hosted on SQLite
```

No AWS and no network. Run all three before pushing; add a check for anything you change.
