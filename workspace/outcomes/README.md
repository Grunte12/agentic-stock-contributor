# outcomes/ (stage 10, after Adobe decides)

What Adobe decided and what sold, joined to your batches, so the next plan builds on results instead of guesses.

| File | Made by | Holds |
|---|---|---|
| `groups.csv` | you | `asset_id,group`: which sub-niche each uploaded asset belongs to (import with `stock_import_groups`) |
| `tags.csv` | you | file name to content tag (for example `people`, `food`, `copy-space`) for `outcome-report --tags` |
| `ledger_<YYYYMMDD>.csv` | `stock_outcome_report` / `outcome-report --ledger` | one row per submitted file with Adobe's result and cause |
| `REPORT_<YYYYMMDD>.md` | you | accept/reject per sub-niche and tag, pasted from the tool, and what to make next |

Order: `stock_outcomes_scan`, then `stock_portfolio`, then `stock_outcome_report` per sub-niche and tag (knowledge topic
`outcomes`). Map new asset ids to local files while the batch is fresh; leave unmatched assets unlabeled, never guess a group.
Judge a sub-niche on its own results, not on the whole batch.
