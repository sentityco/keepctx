# KeepCTX

Keep your AI context across sessions, across AIs, across your team. See `DESIGN.md` for why things are
the way they are; it is long, and the **Explicitly rejected** section is the
useful half.

## Constraints that are not negotiable

- **`src/keepctx.py` is one file, standard library only.** No dependencies. This is
  what makes the installer a `curl` and the code readable in one sitting.
- **`server/handler.py` is one file, boto3 only (and only on Lambda)**, and is deliberately
  model-free: storage and version history; the merge happens in the CLI. Nothing
  in it needs inference, which is what keeps self-hosting plausible.
- **`server/serve.py` is the self-hosted server, standard library only.** It runs the
  same `handler.py` on SQLite and serves `web/` beside the API, so a self-hosted server
  is keepctx.com on one port. Anything added to the handler's storage calls has to work
  on its `Table` too.
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
python3 tests/test_server.py   # accounts, orgs, membership, who can read and write
python3 tests/test_cli.py      # the CLI end to end, against the handler served locally
python3 tests/test_serve.py    # the self-hosted server: site, API on SQLite, restart
```

No AWS and no network: `tests/fakes.py` stands in for DynamoDB and serves the real
handler on a local port. Run both before pushing; add a check for anything you change.
