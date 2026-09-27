<!-- ctx -->
AI context for this project lives in `.ctx/instructions.md` — read it first.
No `.ctx/`? Carry on without it, and don't flag it: it is gitignored, so it may not
be cloned here yet, or it was removed on purpose. To set it up, install ctx
(https://keepctx.com), then `ctx clone <org>:<name>` — or `ctx init` for a new one.
<!-- /ctx -->

# keepctx

Context management for AI agents and people. See `DESIGN.md` for why things are
the way they are; it is long, and the **Explicitly rejected** section is the
useful half.

## Constraints that are not negotiable

- **`src/ctx.py` is one file, standard library only.** No dependencies. This is
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

There are no automated tests yet, which is honest but not good. Behaviour is
verified by hand. Adding tests is the single most useful contribution.
