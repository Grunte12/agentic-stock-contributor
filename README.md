# Agentic Stock Contributor

> **Not technical? Paste this to your AI agent** (Claude Code, Codex, Cursor or Antigravity, running on your own computer; OpenCode also works):
>
> *Install and use this toolkit for me: `https://github.com/Grunte12/agentic-stock-contributor`. Read INSTALL.md and follow it. Explain each step in simple words and ask me before you change any settings.*
>
> The only thing you do yourself is load one Chrome extension (about 2 minutes); your agent walks you through it.

An end-to-end toolkit for working on **Adobe Stock** as a contributor **with an AI agent**: measure the market, plan sets, check and
package your images, stage a verified upload for your final click, and read the outcomes. It has four parts that install together:

| Part | What it gives the agent |
|---|---|
| **Skill + playbook** (`skills/adobe-stock/`) | The operating rules and the 10-stage workflow, loaded by any agent that supports skills |
| **Know-how library** (`knowledge/`) | Mindset, niche research, QC, metadata/SEO, upload flow, community evidence (also served by the `stock_knowledge` tool) |
| **MCP server** (`stock_*` tools) | Deterministic, traceable numbers: supply, season, own portfolio, Adobe's accept/reject outcomes, verified staging |
| **Chrome extension** | Reads Adobe Stock pages and your contributor dashboard for the server; never clicks Submit |

**You work inside this folder.** Clone it once; your research, batches, packages and results go in `workspace/` (never pushed,
see [workspace/README.md](workspace/README.md)), and every folder there has a guide the agent follows. Three files in it (`STATE.md`, `LOG.md`, `PLAYBOOK.md`) are the shared memory of
every agent you use, so Claude, Codex or Cursor can pick up where another left off, and lessons from Adobe's results carry over. `git pull` updates the
toolkit without touching your work.

Plus local commands (stdlib only) for the steps between "images exist" and "ready to stage": `lint-registry`, `check-images`, `qc-tiles`,
`check-qc`, `build-csv`, `prepare-plan`. You bring your own image generator and choose a resize or upscaler after a canary comparison;
the setup guide covers ChatGPT Free, no GPT Bridge, Colab Free and fully local fallbacks.

**Start:** [docs/SETUP.md](docs/SETUP.md) (about 10 minutes) · **Safety, limits, terms:** [docs/SAFETY.md](docs/SAFETY.md) ·
**Workflow:** [knowledge/production-workflow.md](knowledge/production-workflow.md) · **Agents:** [AGENTS.md](AGENTS.md) ·
**Templates:** [examples/](examples/). Unofficial; not affiliated with Adobe. MIT licensed.

## Details

Tools for AI agents that work on Adobe Stock. A Chrome extension reads Adobe Stock search pages and your own contributor dashboard; an MCP server turns what it reads into **deterministic, traceable numbers**: how crowded a keyword is, how your portfolio sells, and which uploads Adobe accepted or rejected (with Adobe's own cause).

The server gives an AI agent numbers about Adobe Stock supply. Code makes every number; the agent chooses keywords, reads tables and decides.

Mostly read-only. Its writes are **upload staging** and **upload metadata**, both off by default and only for a verified plan: staging drops files on the page's own drop zone (no clicks) to fill the portal's New list; metadata uses a short allow list of guarded clicks (Upload CSV, generative-AI box, include box, Save work, Select All, the People/Property answer 'No') and the portfolio read clicks plain page-number controls. It never clicks Submit or Delete (anything so named is refused in code), reads no cookies, automates no login and bypasses no CAPTCHA. Stdlib only (Python 3.11+, no dependencies).

## What it measures (and what it cannot)

Public Adobe Stock pages show: result count, AI flag (`is_gentech`), creator, category, size, and (asset page) keywords. They do **not** show download counts, views or upload dates (checked 2026-10-10). So there is no D/MO, no "new vs old" share and no gap score. Metrics (all in `src/adobe_stock_analytics/metrics.py`):

| Metric | Meaning |
|---|---|
| `results`, `supply_band` | count and band (<2k high niche, <15k medium, <50k moderate, else saturated) |
| `ai_share` | AI-only count ÷ all count |
| `dl_top_ai_share` | AI share among the top results sorted by downloads (do AI images win?) |
| `dl_distinct_creators`, `dl_top1_creator_share` | how concentrated the top-by-downloads results are |
| `keyword_freq` | keywords shared by top assets (asset pages; only the keywords visible without clicking) |
| `supply_rating` | GO / MAYBE / SKIP / UNMEASURED from rules in `config/stock_analytics.json` |
| `trend_mean`, `lead_window` | imported Google Trends CSV; event date minus `lead.start_weeks` to `lead.end_weeks` (default 13 to 8, community hypothesis); moving holidays use listed `dates`, never a guessed one |
| `pf_*`, `mg_*` | your own dashboard (`stock_portfolio`, read-only, `/en/portfolio`; `stock_probe` also reads `/en/uploads` as a raw structure dump, no parsing yet): downloads, earnings, per-asset downloads; per sub-niche group via an asset_id,group CSV (`stock_import_groups`). A dash on a card counts as zero only when the cards add up to the dashboard total |
| `upload_outcome` | Adobe's own accept/reject outcomes (`stock_outcomes_scan` then `stock_outcomes`): reads `/en/uploads/rejected` (asset id, original name) plus Adobe's cause per asset from the same `GET /en/content/<id>/history` the page makes when you select a tile. Cause 9 "Tech problems" is the portal's Quality Issues, 8 is Similar content. One scan = one page load + one paced read per asset, counted as one page by the daily cap. Moderator data in that reply is dropped in the browser and never stored. Accepted ids come from the portfolio read |
| `cal_group`, `cal_band`, `cal_rating` | do low-supply niches sell better for you? Joins each group's downloads with the supply rating of its keyword (`stock_import_group_keywords`, then `stock_report calibration=true`). An association in your own portfolio, not a forecast; a bucket under `calibration.min_assets_per_bucket` assets is null. Nothing changes a band or weight automatically |
| `own_kw_coverage`, `own_kw_sold` | keywords your sold assets share (`stock_report own_keywords=true`; read asset pages first with `stock_asset`). Shows only the keywords visible on each page. Association, not cause: use it to choose what to make next, never copy keywords onto new images (keywords must match the pixels) |
| `recency_cut_suggestion` | suggests `recency.min_asset_id` from your own upload dates (`stock_import_upload_dates`, then `stock_report calibration=true`). Interpolates between two of your own assets, never extrapolates, never edits the config |
| `related_top`, `related_rising` | Google Trends related queries for a seed (`stock_import_related`, then `stock_report related=[seed]`). Search demand relative to the seed, geo and period of the export; "Breakout" is not a volume; not stock-image demand. Pick queries here, then `stock_scan` them for supply |
| `trend_*` from `stock_fetch_attention` | Weekly attention series fetched by an agent: `source=wikipedia` (article page views) or `source=gdelt` (news volume intensity, weekly mean). GDELT answers HTTP 429 when called fast: calls are spaced and a 429 is reported, never retried. Measures interest, not stock-image demand; combine with supply through `opportunities` |

`supply_rating` is about **supply only**. Demand comes from Trends and your own sales.

## Upload staging, know-how and skill

- `stock_upload_metadata(plan_path)` / CLI `upload-metadata`: applies the plan's CSV through the portal's own Upload CSV dialog, then sets generative AI, people/property and include-in-submission for all staged files and saves; never clicks Submit. Needs `upload_metadata.enabled` (user's switch) and refuses when the New list does not hold exactly the plan's files. Verified by reading All (N), Submit N, per-tile keywords and the two checkboxes back.
- `stock_upload_stage(plan_path, only?)` / CLI `upload-stage`: plan = the JSON written by `prepare-plan` (`ready_for_upload: true`, no failures, fresh). Every file is re-hashed; the extension fetches each file from the bridge (`/v1/file`, dispatched job only), re-checks sha256, drops them on the Uploads page's own drop zone, and reads the portal's "File types: All (N)" count back. Success = the count rose by exactly the number staged. A failed or partial stage stops the queue (never retried blindly). Protected folders can never be staged. `upload_stage.enabled` in `config/stock_analytics.json` is the user's switch, read on every use. Details: `knowledge/upload-and-portal.md`.
- `stock_knowledge(topic)`: the know-how (mindset, niche method, workflow, QC, metadata, upload, community evidence) as markdown, served by the MCP itself; `index` lists topics. The MCP `initialize` reply carries the core rules as `instructions`.
- `skills/adobe-stock/SKILL.md` + `knowledge/`: `python3 stock.py install-skill --confirm-write` copies them to `~/.claude/skills/adobe-stock/` (dry run without the flag).
- Live-verified locally: staging and metadata have completed with count, keyword and flag verification while Submit remained untouched.
  Adobe can change its portal at any time, so first use on another account should still be a one-file canary.

## Rules

1. Every number has provenance (`obs_id` or `metric_id`). Missing = `null` + reason, never 0.
2. Tables are rendered by `stock_report`; `stock_verify_doc` fails a doc with edited tables or numbers that are not cited as `[m:<metric_id>]`.
3. No MCP tool accepts a URL, a number, a pacing value or a threshold. Pacing (25 s + jitter, 150 pages/day) and thresholds live in `config/stock_analytics.json`.
4. The queue stops on CAPTCHA, restriction, sign-in wall, HTTP 403/429, unknown page shape, or repeated filter failures. It never retries or bypasses. Only the user resumes: `python3 stock.py resume`.

The verifier checks digits only. A number spelled as a word is not checked, so it is a guard, not proof; the tables stay the source of truth.

## Setup

1. Add the MCP server (`print-mcp-config` prints the JSON; `.mcp.json.example` is a template).
2. Write the pairing token into the extension folder: `python3 stock.py write-extension-token` (creates the git-ignored `extension/token.js`).
3. Chrome → `chrome://extensions` → Developer mode → Load unpacked → `extension/`. No token typing needed. A Chrome profile signed out of Adobe is recommended for market scans (not required).
4. In an agent session call `stock_status`; `bridge_connected` should be true. Then `stock_scan`, `stock_wait`, `stock_report`.

Without the extension, `scripts/live_via_opencli.py <scans.json>` runs the same queue through OpenCLI in your Chrome (dev/fallback).

## Dashboard

Charts (opportunity ranking, niche map, attention over time, your downloads by sub-niche, posting windows) rendered from stored metrics as inline SVG. No scripts, no network.

- Agent: call `stock_dashboard`. It recomputes metrics from stored observations and returns a `http://127.0.0.1:<port>/dashboard?t=<token>` link for the user to open. The page reloads itself every minute.
- User: click the extension's toolbar button (0.5.0 or later). It asks the bridge for the same link and opens it in a tab.
- Offline copy: `adobe-stock-analytics dashboard --out file.html`.

The link token is derived from the pairing token but opens the dashboard only; it cannot pair an extension or post results. The route rejects a foreign Host header and any request with an Origin header, and sends `no-store`, `no-referrer` and a CSP that forbids scripts. Treat the link as private: the page shows your own downloads and earnings.

## Tests

```bash
cd tests && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -p 'test_*.py'
```

## Docs

`docs/` has the setup and safety guides. `CHANGELOG.md` tracks extension changes.
