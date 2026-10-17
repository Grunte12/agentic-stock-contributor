# Instructions for AI agents working in this repository

This repository is both the Adobe Stock contributor toolkit and the place where the user works with it. The toolkit is a Chrome
extension, an MCP server (`stock_*` tools), local batch commands (`stock.py`), a skill and a know-how library. The user's own
work lives in `workspace/`, which git ignores except its `README.md` guides.

## Which job are you doing?

| The user wants to... | Start here |
|---|---|
| Install or set up the toolkit | `INSTALL.md`, exactly. Manual details: `docs/SETUP.md`. First check: `python3 stock.py doctor` |
| Do Adobe Stock work (research, a batch, QC, upload, results) | `skills/adobe-stock/SKILL.md`, then `workspace/README.md` and `workspace/STATUS.md` |
| Connect their image generator | knowledge topic `generation`, section "Build an adapter"; the adapter goes in `workspace/adapters/` |
| Change the toolkit itself | "Changing the toolkit" below |

For Adobe Stock work, call `stock_knowledge` (topic `index`, then `mindset`) if the MCP server is connected; otherwise read
`knowledge/*.md` directly. Run commands from the repository root with paths under `workspace/`.

## Where things go

| Stage | Folder |
|---|---|
| 1-3 research, demand and supply | `workspace/research/` |
| 4-10 one batch (brief, registry, raw, final, QC, waves, report) | `workspace/runs/<RUN>/` |
| 6 the user's generator adapter | `workspace/adapters/<name>/` |
| 10 Adobe's decisions and sales | `workspace/outcomes/` |
| finished or superseded batches (never staged) | `workspace/archive/` |
| the state of every batch, one line each | `workspace/STATUS.md` |
| the user's switches (upload on/off, agent resume) | `config/local.json` (never edit `config/stock_analytics.json` for one user) |
| MCP database, raw page captures, pairing token | `data/` (the server owns it; do not edit by hand) |

## Hard rules

- Never click Submit or upload on your own. Staging and metadata run only when the user asked in chat for that run and their
  switch is on.
- Never invent a number: write `unmeasured`. Code makes every count.
- Stop on CAPTCHA, sign-in, restriction, 403/429 and never retry; read the stop reason before any resume.
- Never decide for the user: ask with the host's question tool and give a recommended answer.
- Every run leaves a dated `REPORT.md` and a line in `workspace/STATUS.md`.

## Changing the toolkit

- Run `cd tests && python3 -m unittest discover -p 'test_*.py'` (stdlib only, no network; Pillow tests skip without it).
- Bump `extension/manifest.json` and add a line to `CHANGELOG.md` for any change under `extension/`.
- A lesson learned in `workspace/` that helps any contributor goes into `knowledge/` (dated, with its evidence tag), never the
  raw run data.
- Never commit `workspace/` content other than its README guides, `data/`, `config/local.json`, `extension/token.js`, tokens or
  your own `.mcp.json`. Check `git status` before every commit.
