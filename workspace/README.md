# workspace/ (your work, never pushed)

Everything you produce lives here: research notes, batches, packages, outcome records and your generator adapter. Git
ignores it except these `README.md` files, so your images, prompts and portal records stay on your computer. Updating the kit
(`git pull`) never touches your work.

Agents: read this file and `STATUS.md` before any Adobe Stock task. Run every command from the repository root
(`python3 stock.py ...`) with paths that start with `workspace/`.

| Folder | Stages | What goes in it |
|---|---|---|
| `STATUS.md` | all | One line per batch and wave: where it is (planned, generating, packaged, staged, submitted, decided). Create it from the template below if missing. |
| `research/` | 1-3 | Niche notes and decision docs built from `stock_report` tables (`research/README.md`) |
| `runs/<RUN>/` | 4-10 | One batch: brief, registry, raw, finals, QC, wave packages, report (`runs/README.md`) |
| `outcomes/` | 10 | Adobe's decisions and your sales, joined to batches (`outcomes/README.md`) |
| `adapters/` | 6 | Your own image-generator adapter (`adapters/README.md`) |
| `archive/` | - | Finished or superseded batches, read-only. Never stage from here. |

The MCP server's own database (scans, portfolio, outcomes, pairing token) is in `data/` at the repository root, also ignored.
Your personal switches go in `config/local.json` (ignored); the shipped `config/stock_analytics.json` stays as it is.

## Rules for this folder

- One batch = one `runs/<RUN>/` folder. Do not scatter files of one batch across other folders.
- `RUN` is `<THEME>_<YYYYMMDD>` in capitals with underscores (for example `XMAS_NY_20261016`). A replacement batch gets a new
  name; never overwrite another batch's files.
- Copy, never move, into a wave package (`stock_upload_stage` refuses symlinks that point outside the plan folder).
- Keep the run's `REPORT.md` current; `STATUS.md` is the one-line summary of it.
- To retire a batch, move the whole folder to `archive/` and say so in `STATUS.md`.

## STATUS.md template

```markdown
# Status (updated YYYY-MM-DD)

| Run / wave | Files | State | Portal job / date | Next action (who) |
|---|---|---|---|---|
| XMAS_NY_20261016 / W1 | 10 | submitted by the user 2026-10-16 | job-... | wait for Adobe (user) |
```

States: `planned`, `generating`, `qc`, `packaged`, `staged` (in the New list), `submitted` (the user clicked Submit),
`decided` (Adobe's result read with `stock_outcomes_scan`), `archived`. Never write `accepted` before Adobe decided.
