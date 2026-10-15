---
description: Mindset, logic and decision rules for Adobe Stock work: buyer-first, measure don't guess, sets over singles, what code does versus what AI does. Read first.
---
# Mindset and decision logic

Evidence tags: **[ADOBE]** official policy (wins every conflict) · **[REPO]** measured or enforced in this project ·
**[MULTI]** repeated by several community authors (strong hypothesis) · **[SINGLE]** one author (experiment only) ·
**[RULE]** a default operating rule of this workflow (the owner of the install may change it). Community tips are dated anecdotes, never Adobe rules, acceptance rates or sales forecasts.

## 1. Think like the buyer, not the artist [MULTI]

Ask "who licenses this and where does it go?" before "is it pretty?". For every candidate write: buyer (a business type,
not "companies"), placement (ad, clinic web page, deck, blog header), the message in one second, and why a real photo is hard
or rare. No buyer sentence, no generation.

## 2. Measure, never guess [REPO]

- Every market number comes from a tool result with an id (`obs_id`, `metric_id`). An AI never types a count, a volume, a rate
  or a sales figure from memory. Models invent numbers confidently [MULTI].
- A missing number is `unmeasured` (null plus a reason). It is never 0 and never an estimate.
- Public Adobe pages show result count, AI flag, creator, category and keywords. They do not show downloads, views or upload dates.
  So there is no gap score and no demand figure from supply pages alone. Demand comes from Trends, attention series and your own sales.
- `supply_rating` (GO / MAYBE / SKIP) is about supply only. Say so every time you show it.

## 3. Sets beat singles, and "similar" is the main enemy [MULTI][REPO]

- One brief = one sub-niche, one buyer, 6-10 images with different concept, action, setting, framing and subject. Colour, flip,
  crop or filter variants are not different images [ADOBE].
- In one contributor account (2026-10), 25 of 54 not-accepted assets were "Similar content" (cause 8); the rest had other causes, including quality
  (cause 9, "Tech problems", shown to the contributor as Quality Issues). Treat look-alikes as a first-class risk: check them before upload, keep near pairs in different waves.
- Stage upload in waves (about 15-20 of the strongest, most distinct). The wave size is a precaution, not an Adobe rule.

## 4. Local QC is a filter, not a forecast [REPO]

A blind cheap-tier reviewer pass caught 0 of the 9 images Adobe rejected for quality. So: local review removes obvious defects
(anatomy, pseudo-text, melted objects, off-subject). It never predicts acceptance; Adobe's own checks decide. Say "passed local review", never "will be accepted".
Keep the sentence "technical pass is not visual approval, visual approval is not Adobe acceptance" true in every report.

## 5. What code does and what AI does (the token rule) [RULE]

| Work | Who | Why |
|---|---|---|
| Counting, hashing, gating, pacing, parsing, staging, verifying files | code (tool) | exact, repeatable, ~0 tokens |
| Rendering tables with cited numbers | code (`stock_report`) | the agent pastes it unchanged |
| Choosing niches and keywords, reading evidence, deciding, explaining | the lead agent (strong model) | judgment |
| Collecting posts, reading threads, one look per image | the cheapest capable worker the host has (small model, sub-agents, or a fresh pass) | volume, not intelligence |
| Confirming a reported fail, final decisions | the lead | judgment |

Rules that follow:
- One tool call per job. Batch scans (up to 20 requests per `stock_scan`). Read the rendered report, never raw observations or page dumps.
- Do not do by reasoning what a tool can do by code. Do not let code decide taste.
- Workers get one job, the exact route, a limit, and a fixed compact output (JSON rows). The lead reads only those rows.
  No sub-agents: do the jobs yourself in batches, rows first, and say a QC run was `single-pass`.
- Use whatever the host has (image provider, vision reviewer, search route); a missing one is `unmeasured` or `BLOCKED`, never faked.

## 6. Stop, do not push through [REPO]

Stop and report at: CAPTCHA, restriction, sign-in wall, HTTP 403/429, an unknown page shape, repeated parse failures,
a hash mismatch, a partial stage. Never retry, rotate, or bypass. Only the user resumes. A partial stage must never be retried
blindly, because it can add files twice.

## 7. The human clicks Submit [RULE]

The agent can prepare, verify and stage. It never clicks Submit, never edits portal fields on its own, never uploads protected,
holdout, quarantine or superseded folders, and never says "uploaded" or "accepted" without evidence of that state.

## 8. Learn from outcomes, honestly [MULTI][REPO]

- A rejection: read the cause (quality, similar, IP, metadata), fix the root cause or drop the concept, never resubmit the same file.
- A sale: add at least one new, different image in the same sub-niche, then niche further.
- Judge a sub-niche on its own results. Calibration against your own downloads is an association in your own portfolio, not a cause.
- Do not copy keywords from sold assets onto new images: keywords must match the pixels.

## 9. Decision flow for a new batch

1. Pick a market; brainstorm 3-8 sub-niches (AI may brainstorm; its numbers are not evidence).
2. Measure supply for 2-3 exact phrases per sub-niche (`stock_scan`, `stock_wait`, `stock_report`). Add season (`lead_as_of`) and
   attention series if useful.
3. Keep sub-niches with a buyer sentence plus a measured band, or an explicit `unmeasured` the user accepted.
4. Write a 6-10 image series brief, then prompts, generate, upscale, QC, metadata, package (see `production-workflow`).
5. Prepare the plan, stage it, the user submits (see `upload-and-portal`).
6. After outcomes arrive, read them (`stock_outcomes_scan`, `stock_outcomes`) and update the next brief.
