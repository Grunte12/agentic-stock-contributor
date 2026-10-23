---
name: adobe-stock
description: Adobe Stock research, niche choice, production and upload know-how with the adobe-stock-analytics MCP tools (stock_*): measure supply and season, decide sub-niches, QC and package a batch, stage verified files on the Uploads page (the user clicks Submit), read outcomes. Use for any Adobe Stock contributor task: niche or keyword research, demand/supply, series planning, QC, metadata, upload, rejections.
---

# Adobe Stock (tool + know-how)

Agent-facing; English. Reply to the user in the user's language.

## Start here

0. Working inside the toolkit repository: follow the session loop in `AGENTS.md` first (read `workspace/STATE.md`, claim,
   matching `workspace/PLAYBOOK.md` entries; at the end log, update state, release). It is the shared memory of every agent.
1. Call `stock_status`. If `bridge_connected` is false, say so; market numbers are then `unmeasured`. If `stop` is not null,
   report its reason and queue nothing; only the user resumes. Note `pages_today` against `daily_cap`.
2. Read the know-how you need with `stock_knowledge` (topic `index` lists them; read only the one you need):
   `mindset` (read first), `analytics-tools` (read before any scan), `niche-research`, `production-workflow`, `generation`, `qc-upscale`,
   `metadata-seo`, `upload-and-portal`, `community-evidence`.
   The same docs are in `references/` next to this file when the skill was installed with `install-skill`.
3. Any host, any model: nothing here needs a named product. Missing capability = `unmeasured` or `BLOCKED`, never faked.

## Talking to the user

Many users are not technical (marketing, content, passive-income contributors). Use plain words, explain a term the first time (MCP, skill, extension, registry),
one step at a time, and ask choices with your host's question tool. Do the work yourself; ask the user only for decisions and for actions only they can do
(loading the extension, clicking Submit). First install: follow `INSTALL.md` in the repository.

## Facts to get right (from `config/stock_analytics.json` and the code, 2026-10-13)

- Pacing: one page read at least 25 s apart plus 0-10 s jitter; at most 150 page reads per UTC day. When the cap is reached the
  queue waits for the next day. No tool takes a pacing value. Tell the user the page count before a large scan.
- One phrase needs 3 scans for a `supply_rating`: `ai_filter all` + `order relevance`, `ai_filter only_ai` + `order relevance`,
  `ai_filter all` + `order downloads`. Fewer scans leave it `UNMEASURED`.
- `stock_wait` waits at most 120 s per call; call it again with the unfinished job ids until none is `queued` or `dispatched`,
  or a stop appears. Do not queue the same scans again.
- The MCP server reads the config once at start. Changed pacing, events, lead weeks, bands or weights apply only after the
  server restarts. Call `stock_restart_server`, then confirm `server_instance_id` changed with `stock_status`; queued jobs and
  the sticky stop are preserved. The `upload_stage` and `upload_metadata` switches are read on every use.
- `stock_verify_doc` exempts dates (YYYY-MM-DD), backticked text, headings, list numbers and fenced code; every other number
  needs a `[m:<metric_id>]` on its line. Keep run counts in the run report, not the decision doc.
- If a doc and the tool's printed output disagree, the output wins.

## Rules that never bend

- Code makes every number. Never type a count, volume, rate or sale from memory. Missing = `unmeasured`.
- Paste `stock_report` tables unchanged; cite other numbers as `[m:<metric_id>]`; check a doc with `stock_verify_doc`.
- Never click Submit. Staging (`stock_upload_stage`) only fills the New list, only when the user asked for it in chat for this run, and only when the user turned `upload_stage.enabled` on. Metadata (`stock_upload_metadata`) applies the plan's CSV and flags and only runs when the user turned `upload_metadata.enabled` on and answered the people/property question.
- Stop on CAPTCHA, restriction, sign-in, 403/429, unknown page, hash mismatch, partial stage. Never retry; only the user resumes.
- Never stage protected, holdout, quarantine or superseded folders.
- A local QC pass is not Adobe acceptance (in one account a blind cheap-tier reviewer pass caught 0 of 9 Adobe quality rejections).

## Tool map (one call per job, fewest tokens)

| Job | Tool |
|---|---|
| Is the extension connected, queue state | `stock_status` |
| Supply of keyword phrases (up to 20 requests per call; 3 per phrase) | `stock_scan` then `stock_wait` (loop) then `stock_report` |
| Keywords of specific assets | `stock_asset` |
| Competitor gallery | `stock_contributor` |
| Season and attention | `stock_report lead_as_of`, `stock_fetch_attention`, `stock_import_trends`, `stock_import_related` |
| Own downloads, groups, calibration | `stock_portfolio`, `stock_import_groups`, `stock_report portfolio/calibration` |
| Not accepted list with Adobe's cause | `stock_outcomes_scan` then `stock_outcomes` |
| Accept / reject rates per sub-niche and content pattern; what to make next | `stock_outcome_report`, knowledge topic `outcomes` |
| Transform technical-pass raws (when chosen) | `stock.py upscale` (CLI) or the user's chosen resize/upscaler; knowledge topic `qc-upscale` |
| Look-alike screen against earlier uploads | `stock.py similar` (CLI, Pillow), knowledge topic `qc-upscale` |
| Stage a verified plan on the Uploads page | `stock_upload_stage`, `stock_upload_result` |
| Apply CSV metadata and flags to the staged files | `stock_upload_metadata`, `stock_upload_result` |
| Visual summary for the user | `stock_dashboard` |
| Stop now | `stock_stop` |

Token habits: batch scans; read the rendered report, not raw observations; never ask for page dumps; hand visual QC to a capable
fresh-context reviewer and keep only its JSON evidence in the lead context. Confirm a visual fail with an independent visual
reviewer; never infer or overturn it from text alone.

## The end-to-end job

Follow `production-workflow` (read it with `stock_knowledge`): 10 stages, an exit gate each. Market stages use the `stock_*` tools;
the local steps use these commands (stdlib only, read-only unless they name an output file):

| Stage | Command |
|---|---|
| 5 Prompts and registry | `lint-registry <registry.json>` |
| 6 Generate | `check-decisions <generation_decisions.json>` (lists what the user has not answered; ask until `ok`) |
| 7 Finals | `check-images <final_dir>` (JPEG, 4-100 MP, <= 45 MB, duplicates) |
| 8 QC | `qc-tiles <final_dir> --out <tmp>` (Pillow), then `check-qc <qc_decisions.json> <final_dir>` |
| 9 Package | `build-csv <registry.json> <package_dir> --out <csv>`, then `prepare-plan <package_dir> --csv <csv> --qc <qc.json> --out <plan.json>` |
| 9 Stage | `stock_upload_stage` / `stock_upload_metadata` with the plan (user's switch + chat go-ahead) |

Generation (stage 6) and upscaling (stage 7) use the user's own generator and upscaler.
**Goal mode for stage 6:** read `generation`, then grill the user in dependency rounds (host question popup such as `AskUserQuestion`, a recommended answer per question, facts looked up by you) until
`check-decisions` says ok. Never pick the provider, model, account, spend or count yourself; the user may choose any generator. Templates: `examples/`.
New install? Run `doctor` and follow its `next` list; `docs/SETUP.md` has the full setup.

## CLI (same tools, no AI needed)

Run from the repository root; your work goes in `workspace/` (read `workspace/STATE.md` first, then `workspace/README.md`). `stock.py` needs no environment variable.

`python3 stock.py <cmd>`: `doctor`, `print-mcp-config`, `status`, `report`, `lint-registry`, `check-images`, `qc-tiles`, `similar`,
`check-qc`, `check-decisions`, `build-csv`, `prepare-plan`, `upload-stage <plan> [--only FILE]`, `upload-metadata <plan>`, `reset-staged`, `resume`, `dashboard`,
`write-extension-token`, `install-skill --agent claude|codex|opencode|agents`. The MCP server (`serve`) also runs the extension bridge.
