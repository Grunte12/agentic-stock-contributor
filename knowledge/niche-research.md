---
description: Method for choosing a market and sub-niche: buyer questions, niche-down prompt, demand/supply measurement, scoring, shortlist, seasonal queue.
---
# Niche Research Method

Stages 1-4 of the playbook. Tags as in `SKILL.md`. Sources:
`community-evidence.md`.

## 1. Buyer questions (fill for every candidate)

| Field | Question | Bad answer | Good answer |
|---|---|---|---|
| Buyer | Which business or role licenses it? | "companies" | "small physiotherapy clinic" |
| Placement | Where does the image appear? | "marketing" | "service page hero, Facebook ad" |
| Message | What must a viewer understand in 1 second? | "health" | "treatment is professional, not scary" |
| Gap | Why is a real photo hard or rare? | none | "patient privacy; few Asian clinic photos" |
| Timing | Is there a date when demand peaks? | none | "Diwali, November" |

The Adobe buyer is mostly a subscriber who licenses many assets (often teams
and companies that need licensed images). [SINGLE, author's inference]

## 2. Niche-down prompt (use with any LLM, then validate)

Give the model the method before asking for ideas. Do not ask "what sells?".

```
You help plan Adobe Stock images. Think as the person who licenses images,
not as the artist.
Market: <market, e.g. elderly care>.
1. List 5 buyer types in this market and where each places images.
2. For each buyer, list 3 images they need that are hard to photograph.
3. Niche down each image 2 levels (market -> service -> specific procedure,
   object or moment).
4. For each sub-niche give 2-3 exact English search phrases a buyer would type.
Do not state search volumes or image counts; I will measure them myself.
Avoid brands, logos, real people, artists, landmarks and news events.
```

The last instruction matters: models invent numbers confidently. [MULTI]

## 3. Measure demand and supply

Record each observation with date, source and exact phrase.

| Signal | How | Who can do it |
|---|---|---|
| Adobe supply | Search the exact phrase on Adobe Stock; note result count | User, or agent in the in-app browser if the page renders |
| What already sells | Same search, sort by downloads; note subject, framing, style of top results | Same |
| Rising searches | Shutterstock contributor trend data | Agent in browser, read-only |
| Search demand | Vecteezy keyword statistics (photo/vector/video split) | Agent in browser, read-only |
| Season | Event date and region; submit 12 weeks before, last useful 8 (`stock_report lead_as_of`) | Tool |

A top result that sells may be old and ranked first for that reason;
copying it does not guarantee sales. [SINGLE]

Supply bands (one author's heuristic, not Adobe data) [SINGLE]:

| Results for the exact phrase | Band |
|---|---|
| < 2,000 | high niche |
| 2,000-14,999 | medium niche |
| 15,000-49,999 | moderate |
| >= 50,000 | saturated |

### Community demand/supply methods (Thai X, 2026-10-10) [SINGLE each]

- **Trends × count** (Author H): compare 3–4 candidate keywords in Google Trends
  (worldwide, 12 months, all categories, web), then read each Adobe count. Pick
  the one with similar interest but the fewest results. Example: "digital skin
  analysis salon" 386 vs "men skincare salon" 44,073.
- **Agent reads the page** (Author J): an AI controls Chrome, searches
  Adobe, and reads the "N results for …" text plus the top 20–30 results.
  - Count all assets and the Generative AI filter separately.
  - On a CAPTCHA, record unknown, never 0.
- **Never trust an AI's counts** (Author B). Every number comes from a
  page read.
- **Lead time 4–8 weeks** (Author K): Oct → Nov–Dec themes; Nov–Dec → Jan–Feb
  (resolutions, detox, Valentine's, Lunar New Year).
- **White-space mockup sets**: the same logo-ready blank area across
  contexts (clinic, pilates, office) sold as a set.

## 4. Score and choose

Score 0-2 on each; keep sub-niches scoring 7+ of 10, and say the score is a
planning aid, not a forecast.

| Factor | 0 | 1 | 2 |
|---|---|---|---|
| Market need | no clear buyer | generic buyer | named business type with a repeating content need |
| Buyer use case | decorative only | one placement | several placements (ads, web, social, deck) |
| Timing | off-season event, or `lead_window` late | evergreen | `lead_window` upcoming or open, or growing trend |
| Search signal | none observed | weak or indirect | trend/keyword data shows it |
| Supply | saturated | moderate | high or medium niche band |

## 5. Market shortlist from the community record (hypotheses)

Reported as selling or recommended in 2026 posts. Each needs stage 3 before use.

| Market | Sub-niche examples | Tag |
|---|---|---|
| Beauty and medical clinics | chemical peel, HIFU face, PRP face, before/after layouts, clean clinic theme | [SINGLE, repeated across 5+ posts by one author] |
| Medical and senior care | medical foot care, elderly care home activities, caregiver support | [SINGLE] |
| Pets | cat supplements (omega-3 capsule, wet/dry food), vet check-up, grooming, pet hotel | [SINGLE] |
| Festivals | Oktoberfest, Diwali (diya lamps, rangoli, sweets), Lunar New Year food, Halloween party food | [MULTI] |
| Physiotherapy | manual technique, shockwave/ultrasound device, neck and back pain shown calmly | [SINGLE] |
| Home services | deep cleaning, mattress vacuuming, sanitizing spray, moving and packing | [SINGLE] |
| Boutique fitness | pilates reformer studio, calm yoga, studio details | [SINGLE] |
| Mental health and child development | counselling room, play therapy | [SINGLE] |
| Hair and scalp clinics | scalp analysis camera, hair-thinning comparison | [SINGLE] |
| Food | appetising close-up, restaurant context with hands, festival context; specific dishes | [SINGLE] |
| Product mockups | blank-label product held by hands; white surfaces for the buyer's logo | [SINGLE] |
| Seasonal backgrounds | autumn, fall, halloween, christmas backgrounds (rising on Shutterstock trends 2026-10-02) | [SINGLE] |

Low-evidence markets: no post in the sample reports sales for
"AI agents / enterprise AI" concept images. Treat that market as unmeasured.

## 6. Seasonal queue (generate 13, submit 12, last useful 8 weeks before the event)

Work backwards from the event. Check dates each year; do not rely on this list.

| Plan by | Event (typical month) |
|---|---|
| Jun | Oktoberfest (Sep-Oct) |
| Late Jul | Halloween (Oct) |
| Aug | Diwali (Oct-Nov), Black Friday (Nov) |
| Late Sep | Christmas (Dec) |
| Early Oct | New Year (Jan 1) |
| Nov | Lunar New Year (Jan-Feb), Ramadan/Eid, Valentine's Day (Feb) |
| Dec | Women's Day (Mar), Easter, spring/sakura (Mar-Apr) |

Plan by = event minus 13 weeks. Event dates other than the tool's config come from
calendar knowledge, not measurement; Ramadan moves with the moon. Check each year.

For a crowded event, pick the adjacent angle: food, preparation, decoration,
gifts, or a regional variant. [SINGLE]

## 7. Demand Score (measured part and judgment part kept apart)

Idea from Author D (2026-10-02, no results reported) [SINGLE]; formula below is ours and uncalibrated.

- M (measured, 0-1) = the tool's `opportunity_score`: supply from `stock_scan` then `stock_report` (results, supply band, AI share, top creator share) plus attention from `stock_import_trends` or `stock_fetch_attention`.
- T (timing gate): `lead_window` upcoming or open, or the subject is evergreen. Late = no-go.
- J (judgment, 0-4, write it down): market need 0-2 plus buyer use case 0-2.
- Go if M >= 0.6, J >= 3 and T is open. These cut-offs are starting guesses; check them against own sales (`stock_report` calibration) and drop a group with 2 or more Similar refusals (`stock_outcomes`).
- Supply check: read the top 20-30 results for 2-3 exact phrases in downloads order.
- Similar content: 6-10 distinct concepts per series, one prompt per image; vary subject, action or setting, never colour, crop or angle. Before generating, search Adobe with the concept's first 5-8 keywords and compare with page one (u/jsycra 2026-04-26, untested) [SINGLE].
- Not measurable by us: buyer search volume on Adobe, other contributors' sales, acceptance probability, Adobe's similarity index.

How to fill it (exact calls: `analytics-tools.md` sections 4-6):

1. M: scan the 3 requests per phrase, add an attention series, then
   `stock_report(opportunities=[{"keyword": ..., "term": ...}])`. Write the
   score with its metric id on the same line (the shape is M = <score from the
   table> [m:<metric_id>]), so `stock_verify_doc` can trace it. If the report
   shows no score (`no_input`), M is `unmeasured`.
2. T: read `lead_window.state` for the event from `stock_report(lead_as_of=<today>)`.
   Evergreen subjects need no event row; write "evergreen".
3. J: write market need (0-2) and buyer use case (0-2) with one sentence of
   reason each, using the table in section 4.
4. Decide per sub-niche and write one line: `go`, `no-go` or `hypothesis`
   (M unmeasured, user told).
