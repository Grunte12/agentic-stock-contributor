---
description: How to use the stock_* tools correctly: session start, pacing (25 s + jitter, 150 pages a day), the 3 scans per phrase, the wait loop, season and attention, stock_verify_doc rules, config restart, portfolio and outcomes, stop reasons. Read before any scan.
---
# Using the adobe-stock-analytics tools correctly

The `adobe-stock-analytics` tools (`stock_*`) read Adobe Stock pages through a
Chrome extension and turn them into numbers with ids. Code makes every number;
you choose keywords, read tables and decide. Facts below were read from this tool's code
and `config/stock_analytics.json` on 2026-10-13; the config file wins if it
changed.

## 1. The rules that never bend

1. Every market number comes from tool output with an id (`obs_id`,
   `metric_id`). Never type a count, volume, rate or sale from memory, from a
   web search snippet, or from an earlier run you remember. Missing = write
   `unmeasured`. Reason: a remembered number has no provenance and the
   verifier cannot check it.
2. Paste `stock_report` tables unchanged. Cite any other number as
   `[m:<metric_id>]`. Check the decision doc with `stock_verify_doc`.
3. Stop on any stop state. Only the user resumes. Never retry, rotate or
   bypass. Reason: a CAPTCHA, sign-in wall or HTTP 403/429 means Adobe is
   limiting the session; pushing on risks the user's account.
4. Never click Submit. Staging and metadata fill work only when the user
   turned their switches on.
5. If a document (README, a doc, this file) disagrees with the tool's printed
   output, trust the output. Example: on 2026-10-13 the tool README said the
   lead window default was 8 to 4 weeks while the config said 13 to 8; the
   printed table follows the config.

## 2. Start of every session

1. Call `stock_status`. Read:
   - `bridge_connected`: true means the extension is paired and polling.
   - `extension_version`: the version the running extension reports.
   - `stop`: null, or `{"reason": ..., "at": ...}` when the queue is stopped.
   - `jobs`: counts by state (`queued`, `dispatched`, `done`, `failed`).
   - `pages_today` and `daily_cap`: page reads used today (UTC day) and the cap.
2. If `bridge_connected` is false: say so. Market numbers are `unmeasured`
   until the user opens Chrome with the extension loaded (setup steps are in
   the tool README). Stored data from earlier scans can still be reported with
   `stock_report`, with their dates.
3. If `stop` is not null: report the reason; do not queue work. The user runs
   `PYTHONPATH=src python3 stock.py resume` in the tool repo
   (`stock_resume` refuses unless the user's config allows it).
4. First time with the tool: `stock_knowledge(topic="index")`, read `mindset`,
   then only the topic you need.

## 3. Pacing, daily cap and time planning

From `config/stock_analytics.json` (`pacing`):

| Setting | Value | Meaning |
|---|---|---|
| `min_gap_seconds` | 25 | at least 25 s between two page reads |
| `jitter_seconds` | 10 | plus a random 0-10 s |
| `daily_cap` | 150 | at most 150 page reads per UTC day |

Plan before you scan:

- One search request = one page read. One asset read = one page read. One
  `stock_portfolio` = one. One `stock_outcomes_scan` = one page load plus one
  paced read per asset, counted as one page by the cap.
- A full supply rating for one phrase needs 3 requests (section 4), so about
  1.5-2 minutes per phrase.
- Example arithmetic: 6 sub-niches x 3 phrases x 3 requests = 54 page reads,
  about 25-32 minutes, about a third of the daily cap. Tell the user the page
  count before you queue it (approval point).
- When `pages_today` reaches `daily_cap`, the queue holds the rest until the
  next UTC day. It does not fail them. Do not try to go faster: no tool takes a
  pacing value.

## 4. Supply scan: request shape and the wait loop

`stock_scan(requests=[...])` takes 1-20 requests. Each request:

```json
{"keyword": "christmas bakery cookies", "media_type": "photo", "ai_filter": "all", "order": "relevance"}
```

- `media_type`: `photo` | `illustration` | `vector` | `video` (default `photo`).
- `ai_filter`: `all` | `only_ai` | `no_ai` (default `all`).
- `order`: `relevance` | `downloads` | `creation` | `undiscovered` (default `relevance`).
- `keyword`: the exact phrase a buyer would type, up to 100 characters.

For each phrase send these three; `supply_rating` stays `UNMEASURED` without
all three:

1. `ai_filter: "all"`, `order: "relevance"` -> `results`, `supply_band`.
2. `ai_filter: "only_ai"`, `order: "relevance"` -> `ai_share`.
3. `ai_filter: "all"`, `order: "downloads"` -> top-by-downloads rows,
   `dl_top1_creator_share`, `dl_top_ai_share`.

Optional fourth: `ai_filter: "no_ai"` (gives `ai_split_gap`).

The call returns `{"job_ids": [...]}` at once. Then wait:

1. Call `stock_wait(job_ids=[...], timeout_seconds=120)` (120 is the maximum).
2. Read each job's `state`. `done` = read and parsed; `failed` = read failed;
   `queued` or `dispatched` = not finished.
3. If any job is still `queued` or `dispatched` and `stop` is null, call
   `stock_wait` again with the unfinished ids. Do this in a loop; each call
   waits at most 120 s. Do not queue the same requests again (a duplicate of a
   queued request returns the same job id anyway).
4. If `stop` is not null, stop the loop and report the reason.

Then render the table:

```text
stock_report(keywords=["christmas bakery cookies", "..."], media_type="photo", lead_as_of="<today YYYY-MM-DD>")
```

It returns `markdown` (paste it unchanged), `render_sha256` and `metric_ids`.
Use `stock_observation(obs_id)` only to check one stored read; do not paste raw
observations into documents.

What the columns mean (tool README): `results` and `supply_band` (<2k high
niche, <15k medium, <50k moderate, else saturated); `ai_share` (AI-only count /
all count); `dl_top_ai_share`; `dl_distinct_creators`; `dl_top1_creator_share`;
`supply_rating` GO / MAYBE / SKIP / UNMEASURED. `supply_rating` is about supply
only. Say so every time you show it. Demand comes from attention series and
own sales.

## 5. Season and attention

- Season: `stock_report(lead_as_of="YYYY-MM-DD")` adds a `lead_window` row per
  event in the config (`events`), with `event`, `start`, `end` and `state`:
  `upcoming` (before the window), `open` (inside), `late` (after). Window =
  event date minus `lead.start_weeks` (13) to minus `lead.end_weeks` (8).
  Moving holidays use only the dates listed in the config; an event with no
  listed future date shows `no_future_date_in_config`, never a guessed date.
  Christmas and "New Year (resolutions)" are in the config today.
- Attention: `stock_fetch_attention(source="wikipedia", query="<article title>", term="<label>", weeks=20)`
  stores weekly page views; `source="gdelt"` stores news volume. GDELT may
  answer HTTP 429: wait, do not loop. Google Trends CSVs the user exported:
  `stock_import_trends(path)`, related queries: `stock_import_related(path, seed)`.
  Attention measures interest, not stock-image demand.
- Combined score: `stock_report(opportunities=[{"keyword": "<phrase>", "term": "<attention term>"}])`
  gives `opportunity_score` = M in the Demand Score (`niche-research.md`
  section 7). The weights are uncalibrated starting guesses (config note).

## 6. The decision doc and `stock_verify_doc`

Write the stage 3 decision doc as its own file (for example
`docs/<RUN>_DEMAND_<YYYYMMDD>.md`) and run `stock_verify_doc(path)`. It returns
`{"ok": true}` or a list of `problems`.

What the verifier checks (`verify.py`):

- Every pasted table block must match the tool's render byte for byte
  (`table_mismatch` otherwise).
- Outside tables, every number must be cited on the same line as
  `[m:<metric_id>]` with a value that metric holds (`untraceable_number`
  otherwise).
- Not checked: dates in `YYYY-MM-DD` form, text inside backticks, heading lines,
  list numbering at the start of a line, fenced code blocks.

So keep run counts (images, jobs) out of the decision doc; they belong in the
run report, which is not verified by this tool. Your own judgment scores (the J
part of the Demand Score) are not tool numbers: write them inside backticks
(as `J=3`) so the verifier skips them, and label them as judgment. Never put a
market number in backticks to get past the check. The verifier checks digits only;
a number spelled as a word is not checked, so do not write numbers as words to
pass it.

## 7. Config changes need a server restart

The MCP server reads `config/stock_analytics.json` once when it starts.
Pacing, events, lead weeks, bands, rating rules and opportunity weights change
only after the MCP server process restarts (restart the host's MCP connection
or the host). Exceptions: `upload_stage.enabled` and `upload_metadata.enabled`
(and the rest of those two sections) are read again on every use, so the
user's switch works at once. After a restart, call `stock_status` again. Never
edit the config yourself; the user owns it.

## 8. Own portfolio, groups and outcomes (stage 10)

| Job | Call | Notes |
|---|---|---|
| Downloads and earnings | `stock_portfolio`, then `stock_wait`, then `stock_report(portfolio=true)` | read-only; one page read |
| Downloads from a CSV export | `stock_import_portfolio(path)` | when the user exported a CSV |
| Label assets by sub-niche | `stock_import_groups(path)` | CSV with columns `asset_id,group` |
| Phrase per group (calibration) | `stock_import_group_keywords(path)`, then `stock_report(calibration=true)` | CSV `group,keyword[,media_type]`; association, not a forecast |
| Not accepted list with cause | `stock_outcomes_scan`, `stock_wait`, then `stock_outcomes` | cause 9 = Tech problems (Quality Issues), 8 = Similar content |
| Rates per sub-niche and content tag | `stock_outcome_report(groups_csv, tags_csv, submitted_folder, ledger_out)` | method and reading rules: knowledge topic `outcomes` |
| Keywords of sold assets | `stock_asset([ids])`, then `stock_report(own_keywords=true)` | never copy keywords onto new images |
| Visual summary | `stock_dashboard` | returns a localhost link for the user |

Mapping new asset ids to local files after an upload:

1. Run `stock_portfolio` (and `stock_outcomes_scan`) after the user's batch
   has been processed.
2. Call `stock_outcomes`. Its `accepted` list has `asset_id` and
   `original_name` for page 1 of the portfolio (up to 100). Compare its length
   with `accepted_total`; older assets may be on later pages.
3. A row whose `original_name` equals a file name in the batch package is a
   high-confidence match. Thumbnail matching (`thumb_url`) is the fallback.
4. Write a CSV `asset_id,group` with high-confidence rows only, where `group`
   is the series `family` from the registry, and import it with
   `stock_import_groups`. Leave the rest unlabeled. Never guess a group.

## 9. Staging (only on the user's instruction)

The agent never uploads (playbook hard rule 1). The staging tools exist for
the user's own workflow; run them only when the user asked for it in chat for
this run and turned the switch on.

- `stock_upload_stage(plan_path, only=[...])` puts the plan's files in the
  portal New list. Needs `upload_stage.enabled` true, a plan with
  `ready_for_upload: true`, at most 20 files and 200 MB, younger than 48 hours,
  no protected folder. Success: `status` `ok` and the All (N) count rose by
  exactly the number staged.
- `stock_upload_metadata(plan_path)` applies the plan's CSV and the AI,
  people/property and include flags. Needs `upload_metadata.enabled` true and
  the New list holding exactly the plan's files.
- A failed or partial stage stops the queue (sticky). Do not retry. The user
  looks at the New list by hand, then runs `resume`. A file already staged (by
  sha256) is refused; stage the rest with `only`.
- Say "staged, not submitted" only when the count rose. The user clicks Submit.
  Details: tool knowledge `upload-and-portal`.

## 10. Stop reasons you may see

| `stop.reason` | Cause | Your action |
|---|---|---|
| `captcha`, `signin`, `restricted` | Adobe page asked for a human or blocked the read | stop; tell the user; never try to solve it |
| `http_403`, `http_429` | access refused or rate-limited | stop; the user decides when to resume |
| `unknown_page_shape:<reason>` | the page layout changed | stop; report; a parser update is needed |
| `repeated_parse_failures` | more than 2 parse failures in a row | stop; report |
| `dispatch_timeout` | the extension took a job and never answered | stop; ask the user to check Chrome |
| `url_not_allowlisted` | a page outside the allowlist | stop; report (should not happen) |
| `upload_stage:<reason>`, `upload_metadata:<reason>` | a stage or metadata run did not verify | stop; the user checks the New list, then resumes |
| `agent_requested` | you called `stock_stop` | the user resumes |

Not a stop: `daily_cap` (wait for the next UTC day), `pacing:<s>` (normal gap),
`upload_stage_off` / `upload_metadata_off` (the user's switch is off; the job is
marked failed; ask the user, do not work around it).
