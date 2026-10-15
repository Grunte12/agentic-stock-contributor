---
description: How to QC final images (a cheap-tier vision reviewer per image over native tiles, a second look confirms only fails) and upscale rules; read before any image QC.
---
# QC and Upscale Checklist

Stages 7-8 of the playbook: upscale every OK raw, then QC the finals once.
QC is a local visual defect screen. Its verdicts are evidence, never visual
approval or Adobe acceptance; Adobe's own checks decide acceptance.

## Final QC (after upscale)

Look at each image on its own at full size, then at native-size crops of
faces, hands, edges and any small detail. Mark pass or fail with a
one-line reason. Do not QC from contact sheets: a batch is 20-50 stills, not
video frames, and finger, seam and pseudo-text defects disappear in thumbnails.
Contact sheets are fine only for spotting look-alikes across the batch.

### Who looks: a cheap reviewer per image; the lead sees fails only

The look is volume work (the defects are visible), so a vision-capable
reviewer at the cheapest tier the host offers takes one image per job; the lead
opens no tile except a named fail. `adobe-stock-analytics qc-tiles <folder> --out <dir>` (needs Pillow; any other tool that crops works too) saves
the 1600 px frame and 3x3 native tiles. Reviewer prompt ("Read tool" means whatever local
file read the reviewer has):

```text
QC one Adobe Stock image. Use only the Read tool. Read: [folder]/full.jpg, then
all 9 tile_r{1-3}c{1-3}.jpg (native-resolution tiles, r = row from top).
Intended subject: [scenario one-liner].
FAIL only for a defect you can point to: wrong finger count or a broken joint,
an extra or ghost limb, melted or duplicated objects, letters/numbers/logos or
garbled pseudo-text, a brand-like product, an oil-paint smear on the main subject,
or a subject that does not match the intended one.
NOT a defect: soft fingers or soft skin from depth of field or upscaling,
background blur, intended glow lines or light overlays.
Reply with JSON only:
{"file": "...", "verdict": "pass|fail", "reason": "one line",
 "defects": [{"tile": "r?c?", "what": "..."}]}
```

Then follow SKILL.md stage 8: merge into `qc_decisions.json`, a second look
confirms or overturns each fail at its named tile, passes are not re-opened.

### Pick your reviewer setup (by host capability)

Find the first row your host can do. Name the setup in `qc_decisions.json`
(`mode`) and in the run report.

| Your host can | Reviewer (first look) | Second look on fails | `mode` |
|---|---|---|---|
| start parallel workers (sub-agents, parallel tasks) on a cheap vision-capable tier that read local files | one worker per image, the prompt above, within the host's concurrency limit | the lead, at the named tile and its neighbours | `parallel` |
| start fresh contexts one after another (new session, new task, new chat) with vision | one fresh context per batch of a few images (one prompt per image, replies collected as rows) | a different fresh context, or the lead | `sequential` |
| only the current context can see images | the lead, one image at a time, using the same prompt and pass/fail rules | the lead again, re-opening the named tile | `single-pass` (say it in the report: one context anchors on its own verdicts) |
| see images only through an external provider call | ask the user to approve the provider call and the evidence write; without approval QC is `BLOCKED` | same | name the provider route |
| not see local images at all | QC is `BLOCKED`. Offer the user to review the tiles; if the user does, the reviewer is `user` | the user | `user` |

Rules for every setup:

1. One image per reviewer job. Reason: a reviewer that sees several images
   mixes them up and misnames files.
2. The reviewer reads `full.jpg` and all 9 tiles of that image only.
3. The reviewer returns the JSON reply only. Keep every reply unchanged in
   `qc_reviewer_replies.json`.
4. A reply that is not valid JSON, names another file, or skips tiles is not a
   verdict. Run that image again in a fresh job once; if it fails again, the
   lead reviews it and the report says so.
5. Never change a verdict without opening the image yourself.

### Merging replies and confirming fails

1. Collect all replies. Count them: one per final. A missing reply means the
   image was not reviewed (not a pass).
2. Put every `pass` file name in `pass`.
3. For every `fail`, the second look opens `full.jpg` and the named tile, then
   the neighbouring tiles if the defect is not there. Decide:
   - confirmed: the defect is real and is in the fail list above. The file goes
     in `fail` with a one-line reason.
   - overturned: the defect is not there, or it is on the not-a-defect list.
     The file goes in `pass`, and `notes` records "overturned: <why>".
4. Write `qc_decisions.json`:

   ```json
   {
     "run": "<RUN>",
     "stage": "post_upscale",
     "pass": ["01_<id>.jpg", "02_<id>.jpg"],
     "fail": ["05_<id>.jpg"],
     "notes": {
       "05_<id>.jpg": "confirmed: six fingers on left hand, tile r3c1",
       "09_<id>.jpg": "overturned: soft fingers from depth of field, not a defect"
     },
     "sha256": {"01_<id>.jpg": "<64 hex>", "02_<id>.jpg": "<64 hex>", "05_<id>.jpg": "<64 hex>"},
     "reviewer": "<model or worker name as the host reports it>, full frame + 9 native tiles",
     "confirmed_by": "<who did the second look>",
     "mode": "parallel",
     "reviewed_at": "YYYY-MM-DD",
     "boundary": "Local defect screen only; not Adobe acceptance."
   }
   ```

   `pass` + `fail` together must list every final exactly once. Use file names,
   not scenario ids, because `check-qc` and `prepare-plan` match by file name.
5. Optional: measure sharpness with any tool you like (for example Laplacian variance); it gates nothing.

### The package gate reads this record

`python3 <kit>/stock.py check-qc <qc_decisions.json> <final_dir>` (and `prepare-plan`, which runs it) passes visual QC only when:

1. every package image is in `pass` (by file name) and none is in `fail`;
2. `reviewer` is set and `mode` is one of `parallel`, `sequential`, `single-pass`, `user`;
3. `confirmed_by` is set when `fail` is not empty;
4. every `sha256` the record lists for a package image equals the current bytes.

Otherwise it names the failed rule. Extra `pass` names (finals held for a later wave) are reported, so keep one record per package.
Never write the record by hand without a reviewer's replies behind it.

First use (wave 1, 2026-10-10) [REPO]: native tiles caught 3 defects that a
downscaled review missed (cuff pseudo-text, book-spine pseudo-text, a smeared
robot arm). The first prompt allowed "hold", and the reviewer put 16 of 18 on
hold, mostly for "soft fingers". That is why the prompt is now pass/fail with
an explicit not-a-defect list. The reviewer also named the wrong tile once, so
search neighbouring tiles when a named defect is not where it said.

| Check | Fail when | Tag |
|---|---|---|
| Anatomy | extra/fused fingers, wrong joints, distorted face, odd proportions | [ADOBE][MULTI] |
| Objects | melted or duplicated objects, impossible geometry, seams | [MULTI] |
| Text-like marks | letters, numbers, sign-like pseudo-text, logos, watermarks | [ADOBE][REPO] (night-tower held for rooftop pseudo-text) |
| IP | recognizable product design, brand-like shape, character, landmark | [ADOBE][MULTI] (a redrawn credit-card line art was still refused for IP) |
| Buyer fit | message not readable in 1 second; no copy space when the brief asked for it | [MULTI] |
| Distinctness | looks like another image in this batch or a common catalog image | [ADOBE][MULTI] |
| Realism | plastic skin, painterly hair, light that does not match the scene | [REPO] |

Reject rather than repair: heavy AI editing of a weak image rarely helps.
Small stray text or a logo may be removed with an inpainting tool (one author
uses IOPaint, open source) [SINGLE]; installing a new tool needs the user's OK.

Never keep two near-identical images to "be safe". Choose the stronger one.

## Measured limit of this QC [REPO]

A blind cheap-tier pass over 137 images caught 0 of the 9 images Adobe rejected
as "Quality Issues" and 2 of 4 lead-confirmed fails; a Laplacian sharpness probe
and other local proxies did not separate them either
(one contributor account, 2026-10; unmeasured elsewhere). So QC removes obvious defects; it
does not predict acceptance. Never write "passed QC, so it will be accepted".
Untested hypothesis: Adobe's "Tech problems" cause may be softness or upscale
artifacts that the prompt tells the reviewer to ignore.

## Upscale

| Item | Rule | Tag |
|---|---|---|
| Engine | a local AI upscaler (Real-ESRGAN x4plus, Upscayl or similar); do not silently fall back to a plain resize. This toolkit has no upscaler: check what is already installed, then ask the user which one to use; installing one needs their yes | [REPO] |
| Size | 3840 px long edge, JPEG quality 95 | [REPO] |
| Minimum | Adobe minimum resolution is stated differently across older pages; check the live page before upload | [ADOBE] unresolved |
| Factor | do not always use 4x; 2x-3x is enough for a ~1024x1536 source to pass 4 MP; 4x can make hair and skin look unnatural | [MULTI] |
| Size (official) | Adobe help pages read 2026-10-13: JPEG, sRGB, 4-100 MP, file <= 45 MB; view at 100%; no watermark. Our gate matches. A 2026-10-10 post (Author E) says "45 MP / 100 MB" (wrong against Adobe) and recommends 4000x2667+, 6000x4000 premium; our 3840 px long edge (11.8-17.6 MP) is above it. Larger files need a real upscale, not a bigger 4x | [ADOBE] + [SINGLE] |
| Model | for hair-, fur- or skin-heavy images, test 2x and a second model on one sample | [MULTI] |
| Zoom check | inspect finals at 100-200% on hair, skin, hands, fabric, foliage | [MULTI] |
| Source | upscale every OK raw, QC the finals, package only passed finals; build the CSV only from final bytes | [REPO] |

Alternatives reported by the community: Upscayl
(free, local), Photoshop 2026 built-in 2x/4x (Firefly or Topaz). [SINGLE]

## After upscale

```bash
python3 <kit>/stock.py check-images <final_dir>
```

Record mean difference final vs raw if you compute it. The native-tile review
is the zoom check. Look for look-alike pairs by eye on a contact sheet (this tool has no similarity screen); the pairs that matter are the ones
inside one upload wave.
