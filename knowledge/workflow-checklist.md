---
description: Mandatory checklist for every Adobe session, handoff and context reset. Record session and gate timestamps, exact asset identities before/after the user's Submit, and first-observed outcomes without inventing review times.
---
# One session protocol, one evidence timeline

Purpose: another agent must be able to resume the same work and measure what happened from evidence, without reconstructing dates from chat. Apply the relevant gates below; a read-only status check does not authorize generation, staging, metadata or Submit.

## Every session

- [ ] Read `STATE.md`, matching `PLAYBOOK.md` choices and recent `LOG.md`; respect another agent's active claim.
- [ ] Read this checklist. Run `python3 stock.py checkpoint start --run <run-or-task> --agent <agent>`; save `session_id` in `STATE.md`. A new chat/context reset gets a new session; reuse the run/task label and retained `before_id` to link an earlier attempt.
- [ ] Call Adobe MCP `stock_status`. On STOP, CAPTCHA, sign-in, restriction or 403/429, report and stop portal actions. Logging a blocked milestone/end is still allowed.
- [ ] Inspect `previous_before_id` returned by start and the state/log for an unfinished user handoff. Reconcile that attempt before new staging; never resend generation or resubmit files automatically.

An existing before-ID must match the active attempt linked to this session. For intentional analysis/resume of an older attempt, select it explicitly with `checkpoint start --run <same-run> --agent <agent> --before <BID>`; do not silently substitute another attempt from the same run.

## Gates during work

- [ ] For each generation, source-QC, upscale, transform-QC or package gate actually performed, save the existing tool receipt/report/plan under the run. Record it once with `checkpoint milestone --session <SID> --stage <gate> --evidence <workspace/file>` (repeat `--evidence` as needed). It records the logging time and evidence hash; it does not backdate the event.
- [ ] Keep provider/model/account choices, raw→final hashes, QC decisions, registry/CSV/plan versions and exact failures in those existing artifacts. Store no credentials, raw page dumps or image bytes in `STATE.md` or model context.

## Before the user clicks Submit

- [ ] After the authorized metadata step, read both `stock_probe(page="uploads")` and `stock_probe(page="in_review")` through MCP. Wait on the same jobs, not replacement jobs. Keep their observation IDs.
- [ ] Run the command below. It requires successful, hash-verified observations from the last 15 minutes, complete unique names/IDs, New count equal to Submit count, no New/review overlap and no active STOP. Failed checkpoint = do not say "ready"; inspect the reason first.

```sh
python3 stock.py checkpoint before-submit --session <SID> --obs <NEW_OBS> --obs <REVIEW_OBS>
```

- [ ] Save the returned `event_id` as `before_id` in `STATE.md`, with target count and next action. Only now report that the measured files are ready. **The user clicks Submit.** Readiness never proves available quota or successful submission.

This readiness gate covers the complete New list. If the user intentionally wants only a subset, do not change their selection or declare the whole list ready: pause that handoff until per-file selection/readiness evidence supports the intended subset.

## After the user says they clicked

- [ ] Record their explicit report first, without inventing the exact click time:

```sh
python3 stock.py checkpoint user-submitted --session <SID> --before <BID> --user-confirmed
```

- [ ] Read fresh New and In review through MCP, then:

```sh
python3 stock.py checkpoint after-submit --session <SID> --before <BID> --obs <NEW_OBS> --obs <REVIEW_OBS>
```

- [ ] Report target IDs confirmed In review, target IDs remaining New, and unresolved IDs separately. Pre-existing review files are not newly submitted. An empty New list alone proves nothing. A partial attempt is not permission to retry; any STOP/restriction ends portal work.

Legacy handoff without a before-ID: omit `--before` on `user-submitted` and `after-submit`. The receipt records the report and observed counts with unknown target scope; it cannot prove how many entered review or infer a review duration. Do not manufacture a retrospective before checkpoint.

## Observe outcomes

- [ ] Read fresh `stock_portfolio` and `stock_outcomes_scan`; add a review probe when checking pending identities. Wait for completion; preserve STOPs. Record:

```sh
python3 stock.py checkpoint results --session <SID> --before <BID> --obs <PORTFOLIO_OBS> --obs <REFUSALS_OBS> --obs <REVIEW_OBS>
```

- [ ] For legacy/account-wide reads with no saved before-ID, omit `--before`; scope is observed identities, not an invented historical submission cohort. Missing outcomes are unknown until a direct New/review observation identifies them. Preserve refusal cause, first-observed time and source observation hash.
- [ ] Acceptance denominator is decided IDs only. Never merge accounts, count repeated snapshots as new files, or treat `creationDate`, staging time, user-report time or first-observed outcome time as exact Submit/decision time. A verified last-review snapshot and first-outcome snapshot give a decision interval; without those, review duration is `unmeasured`.

## Close or hand off

- [ ] `checkpoint end --session <SID>`; append `LOG.md`, update `STATE.md` with run/session/before IDs, next action and unresolved files; release the claim; run `python3 stock.py lint-workspace`.
- [ ] For analysis/export: `python3 stock.py checkpoint export --out workspace/outcomes/workflow_timeline.json`. The append-only events live in the existing private `data/stock_analytics/intel.sqlite`; receipts stay compact. Full exports go to a fresh-context analyst, not the lead context. Do not commit private history.

The command enforces evidence gates and session linkage, not chat detection: agents must run start at every session. It never clicks, navigates, uploads, infers a click timestamp or repairs missing history by backfilling dates.
