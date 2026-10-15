---
description: The 10-stage batch workflow (buyer, sub-niche, demand check, series brief, prompts, generate, upscale, QC, metadata and package, report) with an exit gate per stage and the exact commands this tool provides.
---
# Production workflow (10 stages)

Each stage has an exit gate. Stop and report if a gate fails. Stages 1-4 and 10 use the MCP tools (`stock_*`). Stages 5, 8
and 9 use this tool's local commands (`python3 <kit>/stock.py <command>`, stdlib only). Stage 6 needs
**the user's own** image generator: the tool does not generate and does not care which one is used (a question loop with the user,
see `generation`). Stage 7 can use `stock.py upscale` (Real-ESRGAN, the recommended route) or any upscaler the user chooses.
Details: `generation`, `niche-research`, `analytics-tools`, `qc-upscale`, `metadata-seo`, `upload-and-portal`, `outcomes`.

`<kit>` below is the folder where the toolkit is installed (`~/agentic-stock-contributor` by default). Run the commands from your batch's parent folder.

Keep one folder per batch (a "run"), for example:

```text
runs/<RUN>/registry.json      prompts + title + keywords + category per scenario (stage 5)
runs/<RUN>/generation_decisions.json  the user's answers for stage 6
runs/<RUN>/raw/               generator output (stage 6)
runs/<RUN>/final/             upscaled JPEGs, named NN_<scenario-id>.jpg (stage 7)
runs/<RUN>/qc_decisions.json  who looked, pass/fail per image (stage 8)
runs/<RUN>/package/           passed finals + adobe_stock_upload.csv (stage 9)
runs/<RUN>/plan.json          the verified upload plan (stage 9)
runs/<RUN>/REPORT.md          dated report (stage 10)
```

Templates for the JSON files are in `examples/`.

**Before you plan:** read what you inherit: the newest run report and the state of every earlier batch (submitted, pending,
accepted, refused, held, superseded; `stock_outcomes`, `outcome-report`). Do not plan a concept that repeats a refused or held one.

**Approval points** (each covers one step of one run; never carry it to the next run): the number of pages a stage 3 scan reads;
live generation (canary first, then the rest); any external vision provider call; writing the CSV and plan; portal staging.

1. **Buyer and use case.** Buyer, placement, message, why a real photo is hard. Gate: filled for every candidate.
2. **Niche down.** One market to 3-8 sub-niches, each with a buyer sentence. AI may brainstorm; its numbers are not evidence.
3. **Demand and supply.** Measure with `stock_scan` / `stock_wait` / `stock_report` (3 scans per phrase; season via `lead_as_of`;
   see `analytics-tools`). Gate: counts or `unmeasured` per sub-niche, dated, with source; the decision doc passes
   `stock_verify_doc`; a seasonal theme needs `lead_window` state `open` or `upcoming` (read it, never compute it).
4. **Series brief.** One sub-niche, one buyer, 6-10 images, each a different concept; one shared visual style. No colour, flip or
   crop variants [ADOBE]. One prompt gives one image. A 24-image batch is 3-4 briefs, not one.
   Distinctness test: two images with the same subject, action and setting are one concept; merge them or change one of the three.
   Brief fields: buyer; placement and the copy-space side; the message readable in one second; why a real photo is hard; season state
   (from the tool); the supply table it rests on; one shared style line (light, surfaces, palette, aspect, no text or logos, face rule);
   then numbered concepts, each with its own subject, action and setting.
5. **Prompts and registry.** No artist or real-person names, brands, logos, trademarked products, text, letters, numbers, UI or
   watermark; copy space; natural anatomy. Scenario ids are lowercase words with dashes, unique, and no id is the start of another.
   Describe scene content only (subject, light, placement, copy space): quality boosters such as "8k" or "best quality" and
   style requests add nothing. Seasonal traps: greeting lettering, a year number or a branded character break the text and IP
   rules; ask for blank cards, unlabeled gifts and plain ornaments.
   Check it: `python3 <kit>/stock.py lint-registry runs/<RUN>/registry.json` (read `"ok"` and `"problems"`; `"warnings"` are soft SEO conventions).
6. **Generate** with the user's chosen generator (any provider; see `generation`). Ask the user every open decision (provider, model,
   account, count, variants, size, folder, spend, terms, canary, failure policy, go-ahead) with the host's question popup until
   `check-decisions runs/<RUN>/generation_decisions.json` returns `"ok": true`; never decide for the user and never switch provider,
   model or account silently. Generate the canary first, look at it, and continue only on the user's go. If a scenario fails for
   content reasons, write a new, different concept instead of rerolling the same prompt. Gate: decisions ok, and every scenario
   has an output or a recorded failure.
7. **Upscale every OK raw** with a local AI upscaler to about 3840 px on the long edge, JPEG quality 95, sRGB (see `qc-upscale`,
   "Which upscaler": recommend, the user chooses). Recommended: `python3 <kit>/stock.py upscale <raw_dir> --out runs/<RUN>/final --bin <realesrgan-ncnn-vulkan>` (dry run, then `--confirm-write`).
   QC runs once, on the finals, because those are the bytes that get uploaded. Name files `NN_<scenario-id>.jpg`.
   Gate: `python3 <kit>/stock.py check-images runs/<RUN>/final` returns `"ok": true`
   (JPEG, 4-100 MP, at most 45 MB, no exact duplicates).
8. **QC the finals.** `python3 <kit>/stock.py qc-tiles runs/<RUN>/final --out <tmp>` (needs Pillow) writes a 1600 px frame
   and 3x3 native tiles per image. One reviewer job per image reads them with the prompt in `qc-upscale`; a second look (or you)
   opens only the flagged tiles. Pick the setup by host capability (`qc-upscale`, "Pick your reviewer setup"); no vision for local
   files = `BLOCKED`. Passes had one look and are not an Adobe forecast. Record reviewer, mode and each image's sha256 in
   `qc_decisions.json` (file names, not ids), then run
   `python3 <kit>/stock.py check-qc runs/<RUN>/qc_decisions.json runs/<RUN>/final`.
   Never write a QC record no reviewer produced.
9. **Metadata, CSV, plan, wave.** Write titles and keywords from the final pixels, not the prompt (update `registry.json`), copy the
   passed finals to `runs/<RUN>/package/`, then:
   ```bash
   python3 <kit>/stock.py lint-registry runs/<RUN>/registry.json
   python3 <kit>/stock.py build-csv runs/<RUN>/registry.json runs/<RUN>/package --out runs/<RUN>/package/adobe_stock_upload.csv
   python3 <kit>/stock.py prepare-plan runs/<RUN>/package --csv runs/<RUN>/package/adobe_stock_upload.csv \
       --qc runs/<RUN>/qc_decisions.json --out runs/<RUN>/plan.json
   ```
   `prepare-plan` re-runs the image check, the CSV check and the QC check and writes `"ready_for_upload": true` only when all pass
   and the folder is not protected. That flag means local gates passed; it is not Adobe acceptance. Rank the finals and hand the user
   a first wave of about 15-20 distinct images (staging takes at most 20 files); keep near-similar pairs in different waves (`python3 <kit>/stock.py similar runs/<RUN>/package --against <earlier submitted folders>`).
   Give each wave its own package folder, CSV and plan (copy files, never move or overwrite); keep no loose images in the parent
   folder. If wave 1 cannot reach the user before the season window closes, say so instead of planning a late wave.
   Portal fields: "Created using generative AI tools" always; "People and Property are fictional" for fictional people; never mark
   AI images as illustrative editorial [ADOBE]. Then `stock_upload_stage` and `stock_upload_metadata` (see `upload-and-portal`), only
   when the user asked for it in chat and turned the switch on. The user clicks Submit.
10. **Report and learn.** A dated report with fixed sections, writing `unmeasured` or `not run` instead of dropping a line:
    research and timing (season state from the tool); counts (concepts, generated OK, terminal failures, replacements, finals,
    technical pass, QC pass, confirmed fails, overturned, per wave); inputs and hashes; gates (technical, visual QC with reviewer,
    mode and confirmer, look-alike pairs, lint warnings); commands in order; Adobe action status ("staged, not submitted" /
    "submitted by the user"); unresolved risks. Write a prediction for the pending files. When Adobe has decided: outcomes
    (`stock_outcomes_scan`), own downloads (`stock_portfolio`), then `stock_outcome_report` per sub-niche and content tag, and help the
    user choose the next sub-niche (knowledge topic `outcomes`). Judge a sub-niche on its own results, not on the whole batch.

## Hard rules

- Live generation, paid calls, file writes outside the run folder and portal staging need the user's go-ahead for that run.
- Never invent demand, supply, acceptance or sales. Write `unmeasured`.
- Never stage or upload protected, holdout, quarantine or superseded folders (`upload_stage.protected_markers` in the config).
- Every run leaves a dated report.
