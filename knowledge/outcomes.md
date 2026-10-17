---
description: Stage 10, learn from Adobe's verdicts. Read the accepted and Not accepted lists, group files by sub-niche, tag content blind, run stock_outcome_report, read patterns honestly, and help the user choose which sub-niches to continue. Read after every reviewed batch and before planning the next one.
---
# Outcomes: what Adobe accepted, what it refused, and what to make next

Goal: turn Adobe's verdicts into the next decision. Code counts; you read and explain; **the user decides** which
sub-niches to continue, fix or drop.

## 1. Read the verdicts (read-only)

1. `stock_outcomes_scan` and `stock_portfolio`, then `stock_wait` on both job ids.
2. Note the read times. Files Adobe has not decided yet are pending; re-read weekly, not daily.

## 2. Group the files

A group is what you want to judge: usually the sub-niche (registry `family`), sometimes the batch or run.
Write a CSV with a `group` column and one of:

| column | matches | use when |
|---|---|---|
| `asset_id` | exact Adobe asset id | best; works for accepted files with no name |
| `name` | exact original file name | file names you kept |
| `name_contains` | part of the file name | file names carry a scenario or series prefix |

Never guess a group. If the grouping is unclear, ask the user (question tool, your proposal first).
Groups imported earlier with `stock_import_groups` are used for files the CSV does not match.

## 3. Tag content (optional, blind)

Patterns usually sit in **what the picture shows**, not in pixel statistics (see 6). To see them, tag each local final:

- A cheap vision reviewer looks at each image at about 1000 px with a neutral file name, in shuffled order, and does not see the outcome.
- Suggested columns: `people` (none, hands, small, large), `face` (yes/no), `subject` (object, flatlay, room, person, landscape),
  `style` (photo, illustration, 3d), `bokeh` (none, light, heavy), `copy_space` (yes/no), `text_like` (yes/no).
- One row per file: `name` or `asset_id`, then the tag columns, then `tagger` (who tagged). Tags are model output; say so.

## 4. Run the report

```
stock_outcome_report(groups_csv=..., tags_csv=..., submitted_folder=<the batch folder>, ledger_out=<run>/outcome_ledger.csv)
```

CLI: `python3 stock.py outcome-report --groups g.csv --tags t.csv --submitted <folder> --ledger <run>/outcome_ledger.csv`.
Add `qc_decisions=<run>/qc_decisions.json` (CLI `--qc`) to measure your local QC against Adobe: tag `local_qc`
shows Adobe's verdicts for files your QC passed and failed; `rej_quality` under `pass` are refusals the QC missed. Do this for
every batch: it is the only honest test of the QC prompt (one account's cheap-reviewer pass caught 0 of 9 quality refusals).
Per group and per tag value you get: files, decided, accepted, rej_quality ("Tech problems"), rej_similar, pending,
accept_rate with a 95% interval, downloads, and `too_few` (fewer than `min_n` decided, default 5).

## 5. Read it honestly

- `too_few` true: no conclusion. Say "too few decided files".
- A wide interval means the rate is uncertain. Compare intervals, not single rates.
- **Quality** refusals point at content or rendering (people, skin, hands, upscale texture, artefacts).
  **Similar** refusals point at near-variants in one submission: next time vary concept and composition; never resubmit the same file.
- Batches change several things at once (content, date, size, upscaler, reviewer). Say which ones changed before you name a cause.
- The more cuts you look at, the more chance patterns you find. Treat every pattern as a hypothesis.
- Before the pending files are decided, **write a prediction** in the run report (which files you expect refused and why).
  When they resolve, count hits and misses. This is the cheapest real test you have.
- For a new style or content type, propose a **canary**: 4-5 representative files first, the rest after the verdict.

## 6. What one account found (2026-08 to 2026-10, about 200 decided files) [REPO, one account, hypotheses]

- Verdicts clustered by batch: one batch was refused 13 of 13 for quality while other batches of the same weeks were accepted about 70-80%.
- Blind content tags: scenes with a large or full-body person were refused for quality 9 of 9 (3 of 3 outside that batch);
  scenes without people about 13%; object close-ups about 5%; flatlays about 24%; hands-only scenes 0 of 8 outside that batch.
- Pixel measures did **not** predict refusals: sharpness (Laplacian), noise, FFT, file size, 36 features with ML, and five
  no-reference IQA models (MUSIQ, CLIP-IQA, NIQE, BRISQUE) were at chance across batches. Do not build a gate from them without a held-out test.
- Resolution alone was not the cause: 2400, 3500, 3840 and 4200 px files all appear among quality refusals.
  A plain resize alone was no fix (2 of 5 accepted, no control); used after a strict artifact veto it did as well as the
  AI route (22 of 24 vs 22 of 26 accepted, one batch; topic `qc-upscale`, "The post-upscale veto").
- The two batches with the best rates had a strict post-upscale artifact veto; the batch refused 13 of 13 had none.
- Generation yield by shot type (local QC pass, 120 scenarios, 2026-08): top-down 8 of 10, material sample 6 of 10, copy-space
  hero 5 of 10; detail pair 1 of 10, macro 2 of 10, portrait 2 of 10. Track yield per family and shot type, move volume toward
  what passes, keep a small exploration lane, redesign zero-yield families before spending more.

## 6b. Evidence rules (what counts)

- A verdict joins a file only by asset id, or by the name **and** the SHA-256 of the exact bytes you submitted. Keep the package
  digest and CSV of every submitted batch; never delete them as cleanup.
- Unknown is not "not submitted" and not "accepted". A user saying "I uploaded them" is attested, not verified, until the portal shows the files.
- One refusal supports a note on that asset only. A general rule change needs repeated, independent cases, with the cases that
  contradict it reported, and the user's yes.
- Do not report an acceptance probability until there are enough outcomes in both classes (as a floor: 20 identity-bound
  outcomes across at least 2 batches, 5+ accepted and 5+ refused). Below that, say "not calibrated".
- Test one variable at a time: same generator, upscaler and settings across arms so content (or size, or upscaler) is the only
  difference. Never send two versions of one raw (cause 8). Write the decision rule before the verdicts arrive.

## 7. Choose what to make next (the user decides)

Put these side by side per sub-niche and give one recommendation; the user picks:

| input | from |
|---|---|
| accept rate and interval, quality vs similar | `stock_outcome_report` |
| downloads per accepted file | the same report (portfolio read) or `stock_report(portfolio=true)` |
| supply, AI share, season window | `stock_report` (knowledge topic `niche-research`) |

Starting rules (community and this account; adjust to the user's own results):
- A sale: make new, different images in the same sub-niche, then go one level deeper.
- High acceptance, no sales yet: unmeasured; keep a small series and wait, or test a nearby sub-niche.
- Low acceptance with a clear content pattern (for example large people): keep the sub-niche, change the content (objects, hands, flatlays) and canary it.
- Low acceptance with no pattern: drop it or canary 4-5 files before spending more.
- Similar refusals: fewer, more distinct images per submission.

## 8. Write it down

The run report gets the read times and obs ids, the group and tag tables (pasted from the tool), the prediction and its result,
and the user's decision. Never write an acceptance rate the tool did not print.
