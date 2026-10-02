# Contributing

## The shape of the thing

- `src/keepctx.py` — the whole tool: `ctx init`, the template and its rules. One file,
  standard library only.
- `install.sh` — the `curl … | sh` installer.
- `web/` — the landing page at keepctx.com. No build step, no framework.
- `DESIGN.md` — why it is the way it is, and what was tried and dropped.

**The template and its rules are the product.** Most useful changes are to their wording: what
an agent should keep, how it should keep it, and what it should never write down.

Keep it simple. Nothing may depend on KeepCTX being installed — anyone who clones a repo must
be able to read and keep the context with no tool at all. A pull request that adds a command,
a dependency or a server needs to argue for it against `DESIGN.md`.

## Running it

```sh
python3 src/keepctx.py init      # in any directory; no install needed
```

## Tests

```sh
python3 tests/test_cli.py
```

Add a check for anything you change.
