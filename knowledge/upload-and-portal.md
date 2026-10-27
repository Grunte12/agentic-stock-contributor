---
description: How files get from a verified package to the Adobe Uploads page (plan, stage, human Submit), the gates, what is automated and what is never, and how to read outcomes.
---
# Upload and portal flow

The agent prepares, verifies and stages. The human clicks Submit. Staging puts files in the portal's **New** list only.
Stage only when the user asked for it in chat for this run and turned the switch on; the agent never uploads on its own initiative.

## Flow

1. **Package** a set of final images with its CSV and QC record (`build-csv`, `check-qc`; see `production-workflow` stage 9).
2. **Plan**: `python3 stock.py prepare-plan <package> --csv <csv> --qc <qc_decisions.json> --out <plan.json>` checks the
   package and writes the plan JSON (`ready_for_upload`, `failures`, `package_digest`, `folder`, `files[path, sha256]`,
   `created_at`). Staging refuses a plan older than `max_plan_age_hours` (48), more than `max_files` (20) or `max_total_mb` (200)
   (config `upload_stage`), so run `prepare-plan` again right before staging and stage in waves of at most 20.
   Gates: protected-folder block, image check (JPEG, 4-100 MP, at most 45 MB, no exact duplicates), exactly one CSV with a row per
   file (title, 5-49 unique keywords, numeric category), and the visual-QC record (`qc_decisions.json`: every package image in `pass`,
   none in `fail`, reviewer and mode set, confirmed_by when there are fails, any recorded sha256 equal to the current bytes).
   This tool has no similarity screen: compare look-alike concepts and recommend keeping the stronger distinct image; different waves do not make duplicates distinct.
   `ready_for_upload: true` means local package gates pass. It is not Adobe acceptance.
3. **Fast path**: `stock_upload_stage(plan_path, with_metadata=true)` (or CLI `upload-ready`) validates the metadata switch,
   CSV and flags before staging a complete wave into an empty New list, then applies metadata. Extension 0.10.4 refuses
   non-empty New before fetching image bytes. Partial staging stops before metadata. Use separate staging with `only` for recovery;
   the combined path does not accept subsets. Never Submit.
4. **Stage**: `stock_upload_stage(plan_path, only?)` (or CLI `upload-stage`). The tool re-validates the plan and re-hashes every file;
   the extension fetches each file from the local bridge, re-checks sha256, drops it on the Uploads page's own drop zone, and reads the
   "File types: All (N)" count back (read only). Result: `expected`, `added`, `before`, `after`, `names_not_seen`.
   Success means the All (N) count rose by exactly the number of files staged.
5. **Metadata**: `stock_upload_metadata(plan_path)` (or CLI `upload-metadata`). Needs the user's switch `upload_metadata.enabled`. The tool checks
   the plan, the one CSV (sha256, one row per file, title, 5-49 unique keywords, numeric category). The extension (0.9.0) opens the
   portal's own Upload CSV dialog with that CSV, selects all files in the New list, sets generative AI, the people/property answer
   (`upload_metadata.people_property`, the user's decision) and include-in-submission, clicks Save work, reloads and reads the state back.
   Success = All (N) == Submit N == files in the plan, every tile has keywords, AI and include are checked. It refuses when the New list
   holds a different number of files than the plan (Select All would touch them).
   Do not widen this count guard to include unrelated files. If New contains earlier files, use a user-reviewed complete plan
   for that list or keep metadata paused; a measured total alone does not authorize changing their flags.
6. **Human**: the user looks at the New list and clicks Submit.
7. **Outcomes**: `stock_outcomes_scan` then `stock_outcomes` read the Not accepted list with Adobe's cause per asset
   (9 = Tech problems, shown as Quality Issues; 8 = Similar content). Accepted ids come from `stock_portfolio`.

## What is never automated

- Clicking Submit or Delete. The only clicks in the extension are inside `meta.js` (`intelMetaClick`): a four-control allow list
  (Upload CSV, generative AI box, include box, Save work) plus Select All and the People/property answer; anything named or
  labelled submit, delete, remove, trash, publish or release is refused; tests check this.
- Staging a protected folder (`DO_NOT_UPLOAD`, `quarantine`, `holdout`), a plan that is not ready,
  a plan older than `max_plan_age_hours`, or a file whose sha256 no longer matches the plan.
- Staging when the user's switch `upload_stage.enabled` (in `config/stock_analytics.json`) is off. The switch is read on every use,
  so turning it off takes effect at once, in a running server too. The user turns it on for a run and off after.
- Re-staging a file already staged (by sha256). Stage the rest with `only`. If the user cleared the New list, they run `reset-staged`.

## Stop rules

A failed or partial stage or metadata run stops the queue (sticky): `metadata_error:*`, `metadata_incomplete`, `flags_not_set`, `stage_incomplete`, `stage_sha_mismatch`, `no_upload_input`, `no_stage_shape`,
CAPTCHA, sign-in, restriction. Do not retry. Look at the New list by hand, then the user runs `resume`.
Adobe's weekly submission limit or pending-review cap can pause the portal; do not invent the quota. Stage in waves.
`metadata_error:count_mismatch` means the New list holds more files than the plan, for example a file left there by an
earlier wave that hit the submission limit [REPO 2026-10-16]. Fix: a metadata-only plan that lists every file in New (reuse
the earlier file's CSV row unchanged), then resume. Plan files must be real files inside the plan folder; a symlink that points
outside it is refused. If the user explicitly instructs resume in the current chat and set `stop.allow_agent_resume` true in
`config/local.json`, the agent may call `stock_resume` after reporting the stop reason. The MCP server reads that value at start,
so a switch change needs a restart.

## Limits, routes and lags (facts and lessons)

- Adobe has no contributor API for upload, status, reasons or sales [ADOBE]. Lightroom and Bridge publish still need a manual
  finish in the portal; SFTP is for qualified video and vector accounts, not a photo route [ADOBE, read 2026-08-21].
- Two caps, no published numbers: weekly submissions and files pending review [ADOBE announcement 2025-05-20]. Rough read: a high
  In Review count points to the pending cap; a low one right after submitting points to the weekly cap (opinion). Deleting and
  re-uploading does not reset a cap (community). Never state a reset day; log your own submissions and pacing.
  One account (2026-10-16): "Submission limit reached" after 9 of 10 staged files went in; the 10th stayed in New with its metadata.
- Review can take up to about 6 weeks when queues are heavy (Adobe help page); one account saw at most about 15 days in 2026.
- Do not drive the portal with Playwright, a CDP attach to the user's Chrome or an automated sign-in: Google refused the sign-in
  and the attach failed (2026-09) [REPO]. Use the user's own browser and this kit's extension. Stop if the portal URL changes
  away from the uploads page.
- Archive superseded packages beside the upload folder with a `DO_NOT_UPLOAD` marker and an index row; never delete them, so
  old and new versions are not both uploaded and outcomes can still be matched.

## Reporting

After any stage, record in a dated report: the plan path and `package_digest`, files expected and added, the All (N) count before and
after, `names_not_seen`, and the Adobe action status ("staged, not submitted"). Say "staged" only when the All (N) count rose. "Submit N files" counts only files already included in a submission (needs title and category), so it stays 0 right after staging.
Never say "uploaded" or "accepted" without portal evidence.
