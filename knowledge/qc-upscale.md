---
description: Source, transform and ship gates for image QC, plus resize and upscale rules; read before any image QC.
---
# QC and Transform Checklist

Stages 7-9 use three gates. **Source Gate** blocks concrete defects in the raw.
**Transform Gate** compares the final with that raw and blocks regressions.
**Ship Gate** checks file rules, similarity and truthful metadata. Concept
strength and buyer fit are strategic notes, not technical failures. Every local
verdict is evidence, never Adobe acceptance.

## Source and Transform Gates

Look at each image on its own at full size, then at native-size crops of
faces, hands, edges and any small detail. Record pass, fail or uncertain with a
one-line reason and localize concerns. Do not QC from contact sheets: a batch is 20-50 stills, not
video frames, and finger, seam and pseudo-text defects disappear in thumbnails.
Contact sheets are fine only for spotting look-alikes across the batch.

At Source Gate, distinguish technical defects from hard brief misses (such as occupied required copy space)
and strategic notes. Record brief misses separately in the existing notes; do not call them technical defects.
An unfamiliar mechanism or unclear business meaning alone does not prove impossible geometry. At Transform Gate, compare
the same raw and final regions at the same normalized display scale first. Hide the
transform name, factor and prior verdict from the reviewer. Then inspect the final
at native size for absolute deliverability. Fail only a localized defect that is
absent or materially weaker in the matched raw and clearly worse in the final;
added resolution by itself is not a regression. A transform failure gets one
user-approved safer transform from the same raw before the source is discarded.

### Who looks: a visual reviewer; the lead keeps compact evidence

The look is volume work (the defects are visible), so a vision-capable
reviewer at the cheapest capable tier the host offers takes one image per job; the lead
keeps the JSON evidence and project decision context. `adobe-stock-analytics qc-tiles <folder> --out <dir>` (needs Pillow; any other tool that crops works too) saves
the 1600 px frame and 3x3 native tiles. Reviewer prompt ("Read tool" means whatever local
file read the reviewer has):

```text
QC one Adobe Stock image. Use only the Read tool. Read: [folder]/frame.jpg, then
all 9 r{1-3}c{1-3}.jpg (native-resolution tiles, r = row from top).
Intended subject: [scenario one-liner].
FAIL only for a defect you can point to: wrong finger count or a broken joint,
an extra or ghost limb, melted or duplicated objects, letters/numbers/logos or
garbled pseudo-text, a brand-like product, an oil-paint smear on the main subject,
or other demonstrably impossible geometry. Report hard-brief misses separately in
strategic_notes with a "brief:" prefix; do not label unclear AI meaning a technical defect.
Also FAIL for upscale artifacts on the main subject: waxy or plastic skin,
painted or smeared texture, halos or bright outlines around edges, tiling seams,
wiry hair outlines, invented texture on flat surfaces.
NOT a defect: depth-of-field blur, a soft background, intended bokeh,
intended glow lines or light overlays, plausible wear, casting texture or keyed contacts.
If a material suspected defect has a plausible physical explanation you cannot resolve, use
uncertain and state what needs checking; do not infer a defect from an Adobe rejection label.
Do not tighten QC or prescribe a prompt/upscaler fix from a broad rejection category alone; localize the defect first.
Reply with JSON only:
{"file": "...", "verdict": "pass|fail|uncertain", "reason": "one line",
 "defects": [{"tile": "r?c?", "what": "..."}],
 "strategic_notes": ["optional concept-strength or buyer-fit note"]}
```

`[scenario one-liner]` comes from the registry (or the CSV title), never from the file name: a name is a weak description and
makes "subject does not match" verdicts unreliable.

For Transform Gate, give the reviewer both raw and final frames plus matching
tiles, without naming the model or scale. The first pass compares normalized
views of the same scene area at the same display size; the second pass checks the
final at 100%. This prevents a 4x final from being penalized merely because it is
shown at twice the linear magnification of a 2x final.

Then follow SKILL.md stage 8: merge into `qc_decisions.json`; an independent
visual second look confirms or overturns each fail without seeing the first
reviewer's verdict or defect description. Use that same second look for uncertainty that could change readiness;
match localized findings afterward. Unresolved uncertainty stays out of the package, not in the confirmed fail list.

### Pick your reviewer setup (by host capability)

Find the first row your host can do. Name the setup in `qc_decisions.json`
(`mode`) and in the run report.

| Your host can | Reviewer (first look) | Second look on fails | `mode` |
|---|---|---|---|
| start parallel workers (sub-agents, parallel tasks) on a cheap vision-capable tier that read local files | one worker per image, the prompt above, within the host's concurrency limit | a different visual worker at the named tile and its neighbours | `parallel` |
| start fresh contexts one after another (new session, new task, new chat) with vision | one fresh context per batch of a few images (one prompt per image, replies collected as rows) | a different fresh context, or the lead | `sequential` |
| only the current context can see images | the lead, one image at a time, using the same prompt and pass/fail rules | the lead again, re-opening the named tile | `single-pass` (say it in the report: one context anchors on its own verdicts) |
| see images only through an external provider call | ask the user to approve the provider call and the evidence write; without approval QC is `BLOCKED` | same | name the provider route |
| not see local images at all | QC is `BLOCKED`. Offer the user to review the tiles; if the user does, the reviewer is `user` | the user | `user` |

Rules for every setup:

1. One image per reviewer job. Reason: a reviewer that sees several images
   mixes them up and misnames files.
2. The reviewer reads `frame.jpg` and all 9 tiles of that image only.
3. The reviewer returns the JSON reply only. Keep every reply unchanged in
   `qc_reviewer_replies.json`.
4. A reply that is not valid JSON, names another file, or skips tiles is not a
   verdict. Run that image again in a fresh job once; if it fails again, the
   lead reviews it and the report says so.
5. Never change a visual verdict without an independent visual review of the named evidence.
6. A check that could not run (no reviewer, no Pillow, a screen that errored) leaves the image unknown and the package not ready.
   It is never a pass and never just a warning.

### Merging replies and confirming fails

1. Collect all replies. Count them: one per final. A missing reply means the
   image was not reviewed (not a pass).
2. Put technically passing files with no unresolved hard brief miss in `pass`. Keep unresolved `uncertain` files and brief holds
   outside the package, with the reason in the run report; neither is a confirmed technical fail.
3. For every `fail` or decision-relevant uncertainty, use the independent second look above. Decide:
   - confirmed: the defect is real and is in the fail list above. The file goes
     in `fail` with a one-line reason.
   - overturned: the defect is not there, or it is on the not-a-defect list.
     The file goes in `pass`, and `notes` records "overturned: <why>".
     Name the crop and visual evidence that resolved the concern; distinguish it from an unresolved hard brief miss.
     A technical pass does not resolve that separate hold, and an earlier reviewer's claim is not fresh visual confirmation.
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

   Keep the raw/source path, transform and any overturned finding with its reason in the existing notes or linked reviewer evidence;
   the final SHA-256 identifies which bytes the decision covers. Do not reuse a superseded verdict for a different final.
   `pass` + `fail` together must list every reviewed, resolved final exactly once; held files stay outside the package. Use file names,
   not scenario ids, because `check-qc` and `prepare-plan` match by file name.
5. Optional: measure sharpness with any tool you like (for example Laplacian variance); it gates nothing.

### The package gate reads this record

`python3 stock.py check-qc <qc_decisions.json> <final_dir>` (and `prepare-plan`, which runs it) passes visual QC only when:

1. every package image is in `pass` (by file name) and none is in `fail`;
2. `reviewer` is set and `mode` is one of `parallel`, `sequential`, `single-pass`, `user`;
3. `confirmed_by` is set when `fail` is not empty;
4. every `sha256` the record lists for a package image equals the current bytes.

Otherwise it names the failed rule. Extra `pass` names (finals held for a later wave) are reported, so keep one record per package.
Never write the record by hand without a reviewer's replies behind it.

First use (wave 1, 2026-10-10) [REPO]: native tiles caught 3 defects that a
downscaled review missed (cuff pseudo-text, book-spine pseudo-text, a smeared
robot arm). The first prompt allowed "hold", and the reviewer put 16 of 18 on
hold, mostly for "soft fingers". Keep the explicit not-a-defect list and reserve uncertainty
for a localized concern that could change the decision. The reviewer also named the wrong tile once, so
search neighbouring tiles when a named defect is not where it said.

Why upscale artifacts are on the fail list (2026-10-16) [REPO, one account]: the earlier prompt called soft skin
from upscaling "not a defect". The batches with a strict post-upscale artifact veto did best at Adobe (see
"The post-upscale veto" below); the batch reviewed with the lenient prompt was refused 13 of 13 for quality.
That batch was also all people scenes, so this is a hypothesis: count what the new rule fails and compare outcomes.

More reviewer rules from real runs [REPO]:
- A zero-fail batch is not itself suspicious; judge localized evidence, not an expected rejection quota.
- Rear or side views lower face risk, not hair, ear, hand and body defects; check those tiles.
- Validate every reply yourself (JSON shape, file name, all tiles read). Never trust a model's bare "pass".
- Scores from another rubric or scale are not comparable; keep one rubric per project.

| Check | Fail when | Tag |
|---|---|---|
| Anatomy | extra/fused fingers, wrong joints, distorted face, odd proportions | [ADOBE][MULTI] |
| Objects | melted or duplicated objects, impossible geometry, seams | [MULTI] |
| Text-like marks | letters, numbers, sign-like pseudo-text, logos, watermarks | [ADOBE][REPO] (night-tower held for rooftop pseudo-text) |
| IP | recognizable product design, brand-like shape, character, landmark | [ADOBE][MULTI] (a redrawn credit-card line art was still refused for IP) |
| Hard brief constraint (separate hold) | literal wrong subject; no required copy space; required route/action not shown | [MULTI] |
| Distinctness (Ship Gate) | compare concept, action and composition with earlier work; a technical pass does not settle similarity | [ADOBE][MULTI] |
| Realism | plastic skin, painterly hair, light that does not match the scene | [REPO] |

Reject rather than repair: heavy AI editing of a weak image rarely helps.
Small stray text or a logo may be removed with an inpainting tool (one author
uses IOPaint, open source) [SINGLE]; installing a new tool needs the user's OK.

Never keep two near-identical images to "be safe". Choose the stronger one.

Record weak concept clarity, buyer fit and marketability separately. They may
change ranking or prompt strategy, but they do not turn a technically clean file
into a QC failure.

## Measured limit of this QC [REPO]

A blind cheap-tier pass over 137 images caught 0 of the 9 images Adobe rejected
as "Quality Issues" and 2 of 4 lead-confirmed fails; a Laplacian sharpness probe
and other local proxies did not separate them either
(one contributor account, 2026-10; unmeasured elsewhere). So QC removes obvious defects; it
does not predict acceptance. Never write "passed QC, so it will be accepted".
A later Luna Max blind audit (2026-10-27, one account) likewise found no definite technical failures among six
quality refusals and nine accepted controls; three in each group were uncertain. All three similarity refusals
technically passed. These selected samples do not establish Adobe's hidden cause or support a blanket stricter gate.

## Upscale

### Runtime availability and fallback

The transform decision and the place it runs are separate. Pick the least-transformative acceptable transform first, then use the
first runtime that can execute it without changing the chosen method.

| Runtime available | Guidance |
|---|---|
| Local machine | Default fallback. A deterministic resize needs no cloud GPU; Real-ESRGAN/Upscayl needs compatible local hardware. Verify one canary and record the backend. |
| Colab Free | It can provide free GPU/TPU access, but expensive resources are heavily restricted, hardware and limits vary, and runtimes may terminate. Use it interactively for an occasional canary or small batch; do not build unattended remote control around the free managed runtime. |
| Paid Colab / positive compute-unit balance | Suitable for a batch when local processing is materially slower. Hardware remains subject to availability. Upload once, process the batch, download and verify every file, then release the runtime and confirm no assignment remains active. |
| No usable GPU | Use a deterministic resize only when the clean raw still holds enough detail at the required size. Otherwise hold the image or choose another user-approved service. |

Google states that Colab Free is available without charge and may provide GPUs, but resources are neither guaranteed nor unlimited;
limits and GPU types vary and free notebooks can run for at most 12 hours depending on availability and usage. Paid users also have
dynamic availability. [Google Colab FAQ](https://research.google.com/colaboratory/faq.html), read 2026-10-23. Google currently states
that eligible paid Google AI Pro members receive 200 Colab compute units; verify the live plan before relying on that number.
[Google AI Pro benefits](https://support.google.com/googleone/answer/14534406), read 2026-10-23.

| Item | Rule | Tag |
|---|---|---|
| Engine | use the least-transformative route that reaches the file gate; never silently switch between resize and AI upscale. Recommend, then let the user choose | [REPO] |
| Size | 3840 px long edge, JPEG quality 95 (the size this project used). Keeping the full x4 output (about 25 MP from a 1448x1086 raw) is an option the user may choose; see "Which size" | [REPO] |
| Minimum | Adobe minimum resolution is stated differently across older pages; check the live page before upload | [ADOBE] unresolved |
| Factor | do not always use 4x; 2x-3x is enough for a ~1024x1536 source to pass 4 MP; 4x can make hair and skin look unnatural | [MULTI] |
| Size (official) | Adobe help pages read 2026-10-13: JPEG, sRGB, 4-100 MP, file <= 45 MB; view at 100%; no watermark. Our gate matches. A 2026-10-10 post (Author E) says "45 MP / 100 MB" (wrong against Adobe) and recommends 4000x2667+, 6000x4000 premium; our 3840 px long edge (11.8-17.6 MP) is above it. Larger files need a real upscale, not a bigger 4x | [ADOBE] + [SINGLE] |
| Model | for hair-, fur- or skin-heavy images, test 2x and a second model on one sample | [MULTI] |
| Zoom check | inspect finals at 100-200% on hair, skin, hands, fabric, foliage | [MULTI] |
| Source | Source Gate first; transform only technical passes; compare finals with raws; package only final passes | [REPO] |

Alternatives reported by the community: Upscayl
(free, local), Photoshop 2026 built-in 2x/4x (Firefly or Topaz). [SINGLE]

### Which transform (recommend; the user chooses)

First check what is installed (`realesrgan-ncnn-vulkan` on PATH, the Upscayl app, Photoshop, Topaz). Then ask with the question tool,
recommended option first. Installing anything needs the user's yes; download only from the official release page.

| option | for whom | evidence |
|---|---|---|
| **Deterministic high-quality resize** | a technically clean raw that already has enough detail and crosses 4 MP at 2x-3x | least likely to invent detail; label it as a resize. Local technical evidence exists, but Adobe acceptance for that recovery set is still unmeasured [REPO, one account] |
| **Real-ESRGAN `realesrgan-ncnn-vulkan`, model `realesrgan-x4plus`, plus the post-upscale veto** | a source that needs detail enhancement after a canary comparison | used for every batch of this project 2026-08 to 10. In the best batch, finals that survived a strict artifact veto were accepted 22 of 26; the batch refused 13 of 13 used the same upscaler without the veto [REPO, one account]. About 27-30 s per 1254-1448 px raw on an Apple M5. Free, local, macOS/Windows/Linux, no Python. Releases: github.com/xinntao/Real-ESRGAN |
| Upscayl (free desktop app built on the same Real-ESRGAN-family models; similar output and speed, no terminal) | a user who prefers clicking; the user runs it, then `check-images` | one Adobe Community post (2025-12-23) reported approval falling with Upscayl; no confirmed cause [SINGLE] |
| Topaz Gigapixel, Photoshop Super Resolution (paid) | users who already own them | community advice; not tested here [SINGLE] |

### The post-upscale veto (keep it) [REPO, one account]

x4 output can look worse than the raw: plastic smoothing, seams, halos, missing micro-detail. A strict reviewer
failed 24 of 50 and 30 of 50 x4 finals in two batches (2026-08). Those were replaced by a plain high-quality resize of the
raw (`sips`, 2400-3000 px long edge) or by a new, simpler scene. Adobe's verdicts on the batch that did this (hash-matched, 2026-10):

| route | accepted | quality | similar |
|---|---|---|---|
| Real-ESRGAN finals that passed the veto | 22 | 2 | 2 |
| plain resize, replacing vetoed finals | 22 | 2 | 0 |

A later batch (2026-10-16, 3840 px): Haiku reviewers plus the lead failed 4 of 11 Real-ESRGAN finals (glitter-like bubbles with
pseudo-text, smeared wood, oversharpened peel with a seam, wiry hair halo); the next 6 (2 at 3840, 4 at full x4) failed 0.
Adobe outcomes for both are unmeasured yet.

So both routes did well **after the veto**; a plain resize of five other files without a matched control was 2 of 5.
Rules: run the artifact checks in the QC prompt on every final; for a vetoed final, compare its crop with the same crop of
the raw at a matched display scale first (a defect may already be in the raw), then either regenerate a simpler scene or, with the user's yes, use a
plain resize and **label it as a resize** in the lineage (`upscale_manifest.json` records the backend). Never call a resize an AI upscale.
Check the license of any other model weights before using them commercially; no stated license, do not use.

### Which size

Adobe accepts 4-100 MP [ADOBE]. Some sellers recommend about 24 MP (for example 6000x4000) as "best quality" [SINGLE, user report 2026-10-15];
that is a camera-sized file, not an Adobe rule. An x4 upscale of a 1448x1086 raw gives 5792x4344 (about 25 MP) with `--long-edge 0`;
this project used 3840 px (about 11 MP) and saw no link between size and refusals. Adobe reviewers look at 100%, and a bigger
upscale also shows its texture bigger ("Don't increase resolution in ways that degrade quality", Adobe FAQ). Untested here: if the user
wants 24 MP, propose a canary of a few files at full x4 size beside 3840 px files of similar content, and compare verdicts.

## After upscale

```bash
python3 stock.py check-images <final_dir>
```

Record mean difference final vs raw if you compute it. The native-tile review
is the zoom check. Screen look-alikes: `python3 stock.py similar <final_dir> --against <earlier submitted folder> [--against ...]`
(needs Pillow; average hash, Hamming distance 8 or less). Include folders whose upload state is unknown: treat them as possibly
submitted. Also compare the business action and composition against earlier work; pixel hashes alone miss semantic similarity.
Cosmetic changes or splitting near-duplicates across waves do not establish distinctness. It is a proxy [REPO]: Adobe refused a file as similar whose nearest local pair a screen had rated clear (2026-08),
and Adobe compares against its whole collection, not only yours. For each pair recommend keeping the stronger distinct image after a look;
more than 3 near-variants of one concept go to the user. Never drop files automatically. Record each pair decision in the run
report with both files' SHA-256; replacing either file makes that decision stale, so screen again.
A technical-gate failure (size, format, file size) is fixed by finding why the upscale step produced it and rerunning that step,
not by re-encoding the file by hand.
