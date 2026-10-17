# runs/ (one folder per batch, stages 4-10)

Workflow and gates: knowledge topic `production-workflow`. Templates: `examples/`.

```text
runs/<RUN>/
  brief.md                    stage 4: buyer, placement, style line, numbered concepts
  registry.json               stage 5: prompt + title + keywords + category per scenario (examples/registry.example.json)
  generation_decisions.json   stage 6: the user's answers (examples/generation_decisions.example.json)
  generation_log.tsv          stage 6: one line per scenario: ok or failed, error text, time
  raw/                        stage 6: generator output, <scenario-id>.<ext>
  final/                      stage 7: upscaled JPEGs, NN_<scenario-id>.jpg
  qc/                         stage 8: tiles from qc-tiles, reviewer replies
  qc_decisions.json           stage 8: reviewer, mode, pass/fail and sha256 per final
  waves/W1/                   stage 9: copied passed finals + adobe_stock_upload.csv + plan.json (at most 20 files)
  waves/W2/                   next wave, same shape
  REPORT.md                   stage 10: dated report (examples/REPORT.template.md)
```

Commands, from the repository root (`R=workspace/runs/<RUN>`):

```bash
python3 stock.py lint-registry $R/registry.json
python3 stock.py check-decisions $R/generation_decisions.json
python3 stock.py upscale $R/raw --out $R/final --bin <realesrgan-ncnn-vulkan>     # dry run, then --confirm-write
python3 stock.py check-images $R/final
python3 stock.py qc-tiles $R/final --out $R/qc
python3 stock.py check-qc $R/qc_decisions.json $R/final
python3 stock.py similar $R/waves/W1 --against workspace/runs/<earlier RUN>/waves/W1
python3 stock.py build-csv $R/registry.json $R/waves/W1 --out $R/waves/W1/adobe_stock_upload.csv
python3 stock.py prepare-plan $R/waves/W1 --csv $R/waves/W1/adobe_stock_upload.csv --qc $R/qc_decisions.json --out $R/waves/W1/plan.json
```

Then `stock_upload_stage` and `stock_upload_metadata` with `$R/waves/W1/plan.json`. The user clicks Submit.

Rules:
- Only these names. An experiment (two upscale settings, two prompt styles) is a column in `registry.json` and a section in
  `REPORT.md`, not a second `final_x/` folder. If a step must be redone, overwrite inside the same folder only after the old
  output is no longer referenced, or start a new run.
- A wave folder holds real copies of its files, its CSV and its plan, nothing else. `prepare-plan` and staging read only files
  directly inside it.
- When the portal still holds files from an earlier wave (for example after a submission limit), the metadata step stops with
  `count_mismatch`; make a wave folder that lists every file in New (knowledge topic `upload-and-portal`).
