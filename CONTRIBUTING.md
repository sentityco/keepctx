# Contributing

## The shape of the thing

- `src/keepctx.py` — the whole client. One file, standard library only.
- `server/handler.py` — the whole server. One file, boto3 only.
- `web/` — landing page and the org app. No build step, no framework.
- `DESIGN.md` — why things are the way they are.

The single-file, zero-dependency constraint is deliberate. It's what makes the installer a
`curl`, self-hosting plausible, and the code readable in one sitting. A pull request that
adds a dependency needs to argue for it.

## Running it

```sh
python3 src/keepctx.py init        # no install needed
CTX_REMOTE=http://localhost:8000 python3 src/keepctx.py sync
```

## Before you open a PR

Read the **Explicitly rejected** section of `DESIGN.md` first. Several reasonable-sounding
ideas have already been tried and discarded — scoring users, a server-side AI that judges
whether a change is good enough, keyed JSON claims with supersede pointers, prose alongside
the facts. Each entry records why, and the reasoning is usually the load-bearing part.

If you want to reopen one, that's legitimate — argue against the recorded reasoning rather
than around it.

## Things that would genuinely help

- **Homebrew formula and release automation.** Currently there's an install script and
  nothing else.
- **A static binary.** Python is the right thing to prototype in and the wrong thing to
  hand to strangers. See *Language is a distribution decision* in `DESIGN.md`.
- **The HTML render of a context.** Facts are a reference document; the mechanical render
  is grouping plus markdown-to-HTML and needs no model.
- **Tests.** There are none yet, which is honest but not good.

## Style

Match what's there. Comments explain *why*, not *what*. If a behaviour is surprising, the
comment should say what it would otherwise look like a bug for.
