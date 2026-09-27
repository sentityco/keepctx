# keepctx

Context management for AI agents and people. See `DESIGN.md` for why things are
the way they are; it is long, and the **Explicitly rejected** section is the
useful half.

## Constraints that are not negotiable

- **`src/keepctx.py` is one file, standard library only.** No dependencies. This is
  what makes the installer a `curl` and the code readable in one sitting.
- **`server/handler.py` is one file, boto3 only**, and is deliberately
  model-free: storage, a keyed merge, version history. Nothing in it needs
  inference, which is what keeps self-hosting plausible.
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
```

No AWS and no network: `tests/fakes.py` stands in for DynamoDB and serves the real
handler on a local port. Run both before pushing; add a check for anything you change.
