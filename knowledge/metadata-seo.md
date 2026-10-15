---
description: Title and keyword rules for Adobe Stock metadata and CSV.
---
# Title and Keyword Method

Stage 9 of the workflow. Write metadata from the final image, not from the
prompt. Tags as in `mindset`. `lint-registry` and `build-csv` (this tool) enforce the title, keyword, category and
AI-word rules below that are marked [REPO]; the rest are your checklist.

## Hard rules (fail the package)

| Rule | Source |
|---|---|
| Title describes the main subject; no "generative AI" in the title | [ADOBE] |
| No artist names, real people, fictional characters, brands, trademarks, copyrighted works, government agencies, newsworthy events in title or keywords | [ADOBE] |
| Title 1-200 characters; 1-49 keywords; no duplicate keywords | [REPO] `package.py` |
| Title has no GenAI/model words ("ai generated", "ai image", "ai art", "midjourney", "firefly", "gpt", ...) | [REPO] `lint-registry` |
| First (strongest) keyword shares a 3+ letter word with the title | [REPO] `lint-registry` |
| Filename contains the scenario ID as an exact token | [REPO] |
| Portal: "Created using generative AI tools" ticked for every AI image | [ADOBE] |
| Portal: "People and Property are fictional" for fictional people; not illustrative editorial | [ADOBE] |
| No keyword containing an internal process term (`seasonal-campaign`, `commercial stock photograph`, `conceptual visual`, `editorial composition`) or a bare country name `us`, `u.s.`, `usa`, `united states` | [REPO] checklist (not enforced by code) |
| No malformed hyphen in a keyword (`- x`, `x -`, `--`, leading or trailing `-`) | [REPO] compiler |
| No two images with the same title and the same keyword set | [REPO] compiler |
| Category is a number 1-21 | [REPO] compiler |

### Adobe category numbers

1 Animals, 2 Buildings and Architecture, 3 Business, 4 Drinks, 5 The
Environment, 6 States of Mind, 7 Food, 8 Graphic Resources, 9 Hobbies and
Leisure, 10 Industry, 11 Landscapes, 12 Lifestyle, 13 People, 14 Plants and
Flowers, 15 Culture and Religion, 16 Science, 17 Social Issues, 18 Sports,
19 Technology, 20 Transport, 21 Travel.

Pick the category a buyer would browse for the main subject (a cookie tray is
7 Food, a family dinner scene is 12 Lifestyle, a decorated altar is 15 Culture
and Religion). Check the number against the portal's own category list before the first upload.

### Compiler messages and fixes

`metadata` stops with `metadata validation failed:` followed by every problem.
Fix all of them, then validate again.

| Message (part) | Fix |
|---|---|
| `no exact scenario ID in metadata registry` | the file name does not contain a scenario id as a whole token; check the id and the file name |
| `ambiguous scenario IDs [...]` | two ids match one file name; rename the shorter id in a new registry |
| `title contains forbidden GenAI/model/technical phrase '<x>'` | remove the phrase (for example "ai image", "midjourney", "upscaler") |
| `title exceeds 200 characters` | shorten |
| `keyword count N exceeds 49` / `keywords are required` / `duplicate keywords` | fix the list |
| `strongest keyword '<k>' not present in title` | make keyword 1 share a word of 3+ letters with the title |
| `keyword contains banned internal/process term` / `unsupported geography` | remove that keyword |
| `malformed hyphen token in keyword` | fix the hyphen |
| `duplicate normalized (title, keywords) metadata` | two images have the same metadata; write each from its own pixels |
| `CSV filename missing from folder` / `image not listed in CSV` | the CSV and the folder disagree; rebuild from the package folder |

## Soft conventions (warnings, from the community)

Soft conventions (your checklist). Breaking one is allowed with
a reason. `lint-registry` lists the checkable ones under `"warnings"` (title length, keyword count, title words in
keywords 1-10, camera specs); warnings never set `"ok"` to false.

| Convention | Tag |
|---|---|
| Title about 70 characters or fewer; natural sentence; Subject + Action + Setting (+ optional mood) | [MULTI] |
| 15-35 keywords; quality over filling all 49 | [MULTI] |
| Keywords 1-10: what the image visibly is (subject, main action, main objects) | [MULTI] |
| Keywords 11-25: setting, mood, concepts, "no people" when true | [SINGLE] |
| Keywords 26-35: broad category, style ("top view", "close-up", "copy space") | [SINGLE] |
| Main nouns of the title appear in keywords 1-10 | [SINGLE] |
| Singular nouns; no camera specs ("4k", "ISO", camera brands) | [SINGLE] |
| Only keywords that match the image; no "might sell" padding | [MULTI] |
| Add place names the model cannot know (e.g. a real city) only when true and allowed | [SINGLE] |

## Checks learned on real runs [REPO]

- **Category**: never let a default pass. One run filed every row under one default category; another put food under People.
  Pick the category from the visible subject, row by row.
- **No internal words**: scenario ids, campaign names, "recovery", "replacement", treatment names do not go into titles or keywords.
- **Concept images**: describe them as conceptual or staged ("concept of ..."), never as a real, live product or event.

## The word "AI"

One author says never use "AI" in title or keywords [SINGLE]. Adobe's pages
ban "generative AI" in the title and list prohibited names/IP; they do not ban
the word "AI" [ADOBE]. Repo decision until the user changes it: use "AI" or
"artificial intelligence" only when the image depicts AI as its subject, never
to describe how the image was made.

## Metadata prompt (our template; give it the final image)

```
Write Adobe Stock metadata for this image.
Look first, then list: main subject, action, setting, light, style, and any
visible brand or text (describe generically, e.g. "smartphone").
Title: one natural English sentence, about 70 characters or fewer,
Subject + Action + Setting. Do not mention how the image was made.
Keywords: 15-35, ordered by importance.
  1-10  what is visibly in the image (subject, action, main objects).
  11-25 setting, mood, concepts; add "no people" if there are none.
  26-35 broad category and style.
Put the title's main nouns in keywords 1-10. Singular nouns. No brands,
trademarks, real names, artists, camera specs, or "generative AI".
Output exactly:
title: ...
keywords: k1, k2, ...
```

Then check by eye that every keyword in 1-10 is visible in the image.

## Worked example (from the 2026-10-10 run)

Before (90 chars, keyword 1 is a concept):
`Businessman watching AI agents split one task into four parallel workflows on a glass wall`
keywords start `AI agents, businessman, task decomposition, ...`

After (69 chars; soft conventions applied; meaning unchanged):
`Businessman at glass wall watching glowing task lines split four ways`
keywords start `businessman, glass wall, glowing lines, office, rear view, city skyline, sunset, workflow, AI agents, task delegation, ...`

The "after" version is an example only; it was not applied to the staged CSV.

## Seasonal example (illustration, not from a run)

Image: overhead view of hands placing iced star cookies on a baking tray,
flour on a wooden table, blank space at the top.

Bad title: `Merry Christmas 2026 AI generated holiday cookies, best festive image for your brand`
(greeting and year are text the image does not show; "AI generated" is
forbidden; "best ... for your brand" is padding; 84 characters).

Bad keywords: `christmas, xmas, holiday, festive, merry christmas, santa, santa claus, gift, present, snow, ...`
(keyword 1 shares no word with a good title; Santa, gifts and snow are not in
the image; padding to 49).

Good title: `Hands placing iced star cookies on a baking tray with flour, top view`
(69 characters; Subject + Action + Setting; every noun is visible).

Good keywords (22): `cookies, hands, baking tray, star cookie, icing, flour, wooden table,
baking, homemade, christmas baking, top view, copy space, holiday season,
bakery, dessert, kitchen, preparation, winter, festive food, flat lay,
no face, food`
(1-10 are visible things; seasonal words come after the visible ones; "copy
space" and "top view" describe the frame; no brands or greetings). Then check
by eye: every keyword in 1-10 is in the picture.
