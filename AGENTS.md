<!-- KeepCTX -->
This project's context is kept in `KEEPCTX.md`. Read it at the start of every session,
and keep it current as the rules at its top say. If `KEEPCTX.md` is missing, ignore
this and carry on.
<!-- /KeepCTX -->

# KeepCTX

Keep one context. Every session, every AI, every teammate. `CONTRIBUTING.md` has the shape
of the code; `DESIGN.md` has why it is the way it is.

## Constraints that are not negotiable

- **Nothing may depend on KeepCTX being installed.** The product is `KEEPCTX.md`, a
  Markdown file whose rules are at its top. `keepctx init` only creates it and points
  `AGENTS.md` at it. Agents read and edit the file directly.
- **`src/keepctx.py` is one file, standard library only.** It's what makes the installer a
  `curl` and the code readable in one sitting.
- **`web/` has no build step and no framework.**
- **No per-agent integrations.** `AGENTS.md` is the integration.

## Testing

```sh
python3 tests/test_cli.py
```

## Deploying

Pushing does not deploy. After a change to `web/` or `install.sh`, run `./deploy.sh`.
