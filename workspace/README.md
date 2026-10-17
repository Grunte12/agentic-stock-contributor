# workspace/ (your work, never pushed)

Everything you produce lives here: the shared state, research, batches, packages, outcome records and your generator adapter.
Git ignores it except these `README.md` files, so your images, prompts and portal records stay on your computer. Updating the kit
(`git pull`) never touches your work. Run every command from the repository root with paths that start with `workspace/`.

## The shared state (read first, keep current)

Three files are the single source of truth for every agent that works here (any host, any model). Create them with
`python3 stock.py init`; check them with `python3 stock.py lint-workspace`. How to use them each session: `AGENTS.md`.

| File | Holds | Who changes it, how |
|---|---|---|
| `STATE.md` | Now: focus, each run's stage or portal state, decisions waiting on the user (`D-NNN`), stops, next actions, which agent is working | Any agent, sections rewritten in place, at every gate; under 150 lines |
| `LOG.md` | History: one dated entry per meaningful step | Any agent, append only, newest last |
| `PLAYBOOK.md` | What this account learned (`L-NNN`, with evidence and helpful/harmful counts) and the user's standing choices (`C-NNN`) | Only through `python3 stock.py lesson add / vote / retire` |

## Folders

| Folder | Stages | What goes in it |
|---|---|---|
| `research/` | 1-3 | Niche notes and decision docs built from `stock_report` tables (`research/README.md`) |
| `runs/<RUN>/` | 4-10 | One batch: brief, registry, raw, finals, QC, wave packages, report (`runs/README.md`) |
| `outcomes/` | 10 | Adobe's decisions and your sales, joined to batches (`outcomes/README.md`) |
| `adapters/` | 6 | Your own image-generator adapter (`adapters/README.md`) |
| `archive/` | - | Finished or superseded batches, read-only. Never stage from here (the tool refuses). |

The MCP server's own database (scans, portfolio, outcomes, pairing token) is in `data/` at the repository root, also ignored.
Your personal switches go in `config/local.json` (ignored); the shipped `config/stock_analytics.json` stays as it is.

## Rules for this folder

- One batch = one `runs/<RUN>/` folder. Do not scatter files of one batch across other folders.
- `RUN` is `<THEME>_<YYYYMMDD>` in capitals with underscores (for example `XMAS_NY_20261016`). A replacement batch gets a new
  name; never overwrite another batch's files.
- Copy, never move, into a wave package (`stock_upload_stage` refuses symlinks that point outside the plan folder).
- A run's `REPORT.md` is the full record; its line in `STATE.md` is the one-line summary.
- To retire a batch, move the whole folder to `archive/`, update `STATE.md` and log it.
- Portal states, in order: `staged` (in the New list), `submitted` (the user clicked Submit), `decided` (Adobe's result read with
  `stock_outcomes_scan`), `archived`. Never write `accepted` before Adobe decided.
