# Changelog

## Toolkit 0.14.1

- Agents can call `stock_restart_server` to restart the MCP process in place while preserving its stdio connection, queued jobs and sticky stop. `stock_status` now reports a `server_instance_id` so the restart can be verified without asking the user to restart the host.

## Toolkit 0.14.0

- Shared state for every agent (any host): `workspace/STATE.md` (now: focus, runs, decisions waiting on the user as `D-NNN`, stops, next, which agent is working), `LOG.md` (append-only history) and `PLAYBOOK.md` (lessons `L-NNN` with evidence paths and helpful/harmful counts, and the user's standing choices `C-NNN`). Templates in `examples/workspace/`. Design follows Anthropic's long-running harness (progress file plus structured state), OpenAI harness engineering (short AGENTS.md as a map), ACE and ExpeL (itemized, delta-updated lessons with counters, never full rewrites) and evidence that self-diagnosed lessons and planted memory are unreliable.
- New commands: `init` (creates the three files, never overwrites), `lesson add|vote|retire` (the only way to change the playbook; a lesson needs an evidence file that exists), `lint-workspace` (sections, size caps, stale claim, decision ids, log order, evidence paths, AGENTS.md length).
- `AGENTS.md` rewritten as a short map with the session loop (start, work, end) and the learning rules; a test keeps it under 100 lines. `workspace/STATUS.md` is replaced by `STATE.md`.

## Toolkit 0.13.0

- One repository to clone and work in: the user's work goes in `workspace/` (git-ignored except its README guides): `research/`, `runs/<RUN>/` (brief, registry, raw, final, qc, `waves/W1..`, REPORT), `outcomes/`, `adapters/`, `archive/` and `STATUS.md`. Each folder has a README that tells the agent what goes there and which commands to run. Skill and knowledge paths now use `workspace/runs/<RUN>/` and `python3 stock.py` from the repository root; a wave is `waves/W<n>/` with its own CSV and plan.
- Generation: knowledge `generation` gains "Build an adapter": the agent asks which generator the user has (API, CLI, MCP tool, web app) and builds a script, tool-call note or hand-off sheet in `workspace/adapters/<name>/` against one contract (`raw/<scenario-id>.<ext>` plus `generation_log.tsv`).
- `workspace/archive` is a protected marker: plans and staging refuse it. Protected markers now match with either path separator.
- INSTALL asks the person where to put the folder (suggests `~/agentic-stock-contributor`). `CLAUDE.md` imports `AGENTS.md`, which now routes by job and lists where every stage's files go.
- Personal settings: `config/local.json` (gitignored) is laid over `config/stock_analytics.json` one section deep for the running server and the CLI, so a user can keep, for example, the upload switches on or `stop.allow_agent_resume` true without changing the shipped defaults. Tests ignore it.

## Toolkit 0.12.1

- The MCP server reports the package version (it said 0.1.0); a test keeps `pyproject.toml` and the package version equal. Install checked end to end from a fresh clone on macOS (all five connect targets, skills, token, MCP tools); the Chrome extension step was not automated.

## Toolkit 0.12.0

- Outcome analytics: `stock_outcome_report` / `outcome-report` joins Adobe's verdicts (Not accepted list with cause, accepted portfolio, downloads) with the user's groups and blind content tags; counts, accept rate with a Wilson 95% interval, quality vs similar refusals, pending files, `too_few` flag and a per-file ledger CSV. New knowledge topic `outcomes`: how to read patterns honestly, pre-registered predictions, canaries, and choosing the next sub-niche with the user.
- `upscale`: Real-ESRGAN `realesrgan-ncnn-vulkan` (model realesrgan-x4plus) then a Lanczos resize to the long edge (default 3840; 0 keeps the full x4 size), JPEG q95; dry run by default, never overwrites, never falls back to a plain resize, writes `upscale_manifest.json`. `qc-upscale` recommends it and lists alternatives; the user chooses.
- `similar`: look-alike screen (average hash, Hamming distance) within new finals and against earlier submitted folders; pairs and groups over 3 near-variants; a proxy, never auto-drops.
- Knowledge distilled from the authoring workspace's run reports (2026-08 to 10): QC prompt now fails upscale artifacts (waxy skin, halos, seams) and names the real tile files (`frame.jpg`, `r1c1.jpg`); "The post-upscale veto" with hash-matched Adobe outcomes per route; outcome evidence rules (identity, attested vs verified, calibration floor, one variable at a time); generation error kinds, output-to-job checks, prompt length and craft; metadata category and internal-word checks; portal limits, lags and routes; niche checks (top-by-downloads AI share, no Trends/count ratio, event rule).
- `lint-registry` adds soft SEO `warnings` (title over 70, keyword count outside 15-35, title words missing from keywords 1-10, camera specs); they never fail the check.
- `outcome-report --qc` / `qc_decisions`: tag `local_qc` compares the local QC verdict with Adobe's, so QC recall is measured per batch.
- INSTALL step 6: the person chooses to load the extension themselves or let the agent do it on screen.

## Toolkit 0.11.0

- Project name: Agentic Stock Contributor (repo `agentic-stock-contributor`). Main hosts: Claude Code, Codex, Cursor and Antigravity (`connect --agent antigravity`, `install-skill --agent antigravity`); OpenCode also works. INSTALL tells the agent to adapt to each computer and ask the person for every open choice.
- Agent-first install: root `INSTALL.md`, `connect` / `disconnect` (dry run by default; backs up; adds or removes only our entry; refuses unreadable or differing configs) for Codex, OpenCode, Cursor and Claude Code, `print-mcp-config --format json|toml|opencode`, `doctor` reports `mcp_registered_in`.
- Generation stage 6 is provider-neutral: knowledge topic `generation` and `check-decisions` make the agent ask the user (host question popup) until every choice is answered; the agent never picks provider, model, account or spend.
- End-to-end release: skill + know-how + MCP server + extension + local batch commands (`lint-registry`, `check-images`, `qc-tiles`, `check-qc`, `build-csv`, `prepare-plan`, `check-decisions`, `doctor`, `print-mcp-config`), setup and safety guides, templates in `examples/`, MIT license. `install-skill` takes `--agent claude|codex|opencode|agents`.

## Extension

Bump `extension/manifest.json` version on every change under `extension/`. `stock_status` shows the version the running extension reports (`extension_version`).

- 0.10.1: the after-load URL check also accepts `?isa0=<digits>` and no other query, because the portal sometimes redirects `/en/uploads` to `/en/uploads?isa0=1` (seen 2026-10-16; staging stopped as `restricted`). No new permissions.
- 0.10.0: portfolio read now covers every page. New `pager.js` with one guarded click on a plain page-number control inside `[data-t="core-pagination"]` (Next/Previous, anything outside that block and anything named submit, delete, remove, trash, publish, release, save or upload is refused). Cards of all pages are merged by asset id; names stay page 1 only (later pages have no embedded list). The payload records `page_numbers`, `pages_read` and `pager_error`. No new permissions.
- 0.9.1: `upload_metadata` can also tick the sidebar box "People and Property are fictional" (flag `people_property_fictional`) and reads its state back with the other flags. Same guarded click, no new permissions.
- 0.9.0: new `upload_metadata` kind and `meta.js`. For a user-enabled, ready plan it fetches the plan's one CSV from the bridge (sha256 re-checked), opens the portal's own Upload CSV dialog, hands it the CSV, selects all files in the New list, sets the common flags (generative AI, people/property answer, include in submission), clicks Save work, reloads and reads the counts back. This is the first version with clicks: exactly one `.click()`, inside `intelMetaClick`, which refuses anything not on a four-control allow list and anything named or labelled submit, delete, remove, trash, publish or release. Submit is never clicked. No new permissions.
- 0.8.4: `upload_stage` reads the All (N) count only after the list has finished loading (same value twice, no upload running) and takes the count that decides success from a fresh page load, because a background tab does not refresh its own list (measured: a staged file was in the portal but the stage result read 0 before and 0 after). No new permissions.
- 0.8.3: reloads itself when the bridge says so (`adobe-stock-analytics reload-extension` sets the flag; the extension calls `chrome.runtime.reload()` on its next poll), so a changed unpacked extension needs no click on `chrome://extensions` after this version is loaded once. No new permissions.
- 0.8.2: removes the guarded Upload-button click that 0.8.1 briefly had (measured: the uploader exists on `/en/uploads` without opening the panel, and the click changed the URL to `?upload=1`, outside the allowlist). Staging uses the drop zone only, as described in 0.8.1. Zero clicks again.
- 0.8.1: `upload_stage` now hands files to the Uploads page's own drop zone (`.uploader__drop`) with dragenter/dragover/drop events, because the page's uploader ignores a script-set file input (measured live 2026-10-12). Staging is verified by the portal's "File types: All (N)" count rising by the number of files, with no "Upload Remaining" text; "Submit N files" only counts files already included in a submission, so it is no longer used. Still never clicks, never touches Submit. No new permissions.
- 0.8.0: new `upload_stage` kind. Fetches each file of a user-enabled, ready plan from the bridge (`/v1/file`, only files of the dispatched job), re-checks sha256, puts them in the Uploads page's own file input (`stage.js`) in batches, and polls the Submit count read-only until it rose by the number staged. It never clicks and never touches the Submit button. No new permissions.
- 0.7.1: portfolio read also records original file name, status and creation time of the assets in the page's embedded list (page 1, up to 100) and the portfolio total, so accepted assets can be matched to local files. Same whitelist as `outcomes`; no new request.
- 0.7.0: new read-only `outcomes` kind for `/en/uploads/rejected`. Reads the page's embedded list (asset id, original name, status, size; nothing else) and, per asset, Adobe's own `GET /en/content/<id>/history` (cause fields only) with a 0.8-1.6 s pause, 10 assets per call, stop on 403/429. One extra host permission.
- 0.6.1: probe also records the uploads sub-menu entries (with link targets if they are links) and contributor-portal links, to learn how to reach the Not accepted list without clicking.
- 0.6.0: new read-only `probe` kind for two own-dashboard pages, `/en/portfolio` and `/en/uploads` (no query). Dumps page text, tab labels, `data-t` names and status lines for parser design. One extra host permission; no new API.
- 0.5.0: toolbar button opens the read-only localhost dashboard (asks the bridge for the link). No new permissions.
- 0.4.0: portfolio cards also record `thumb_url` (public thumbnail address, query removed) so asset ids can be matched to local files later.
- 0.3.0: records extension version and extract function hash (`_ext`) in every payload; sends `X-Intel-Ext`.
- 0.2.0: final URL must match the allowlist after load, otherwise `restricted` (sticky stop).
- 0.1.0: first working reader.
