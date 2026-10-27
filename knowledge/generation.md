---
description: Stage 6, image generation with any provider. The decision checklist the agent must ask the user (never decide), the provider-neutral contract, canary and failure rules.
---
# Generation (stage 6): any provider, the user decides

This tool does not generate images and is not tied to one generator. The user may use a ChatGPT bridge, Codex image
generation, any image API, Google Flow, a local model or anything else. Your job here is to **ask, record and
verify**, not to choose.

## Availability and fallback

Detect capability at the start of the run; do not infer it from a subscription name.

| What is available | Use |
|---|---|
| GPT Bridge is installed and its readiness check passes | Use its MCP adapter with the user's selected ChatGPT account. The Bridge does not add or bypass quota. |
| ChatGPT Free exposes **Create image** | GPT Bridge can use that account after local installation and pairing, subject to the account's smaller image limit. OpenAI says image creation is available on Free, while image generation has a separate limit and paid plans have higher limits. Stop on the in-product limit; never resend the prompt. [OpenAI Free Tier FAQ](https://help.openai.com/en/articles/9275245-chatgpt-free-tier-faq), read 2026-10-23. |
| ChatGPT is available but GPT Bridge is not | Offer the local [GPT Bridge installer](https://github.com/Grunte12/gpt-bridge#install-agent-integrations), or create a hand-off sheet if the user does not want to install it. Do not make installation a batch prerequisite. |
| No ChatGPT image access | Use another user-approved generator or a hand-off sheet. Keep the same scenario ids, filenames and generation log. |

The readiness check, not the plan label, decides whether the route is usable today. Limits change, so record a limit as
`unmeasured` until the provider reports it; never promise a fixed number of images.

## Grill the user until nothing is open (goal mode)

The method follows the "grilling" skill by Matt Pocock (MIT, `skills/productivity/grilling` in github.com/mattpocock/skills; `grill-me` is its short trigger): treat the choices as a tree, ask in rounds,
recommend an answer, look up facts yourself, leave decisions to the user, and finish only when nothing is left open.

1. Copy `examples/generation_decisions.example.json` to `workspace/runs/<RUN>/generation_decisions.json`.
2. Run `python3 stock.py check-decisions workspace/runs/<RUN>/generation_decisions.json`. Its `open` list is every question
   still unanswered.
3. **Ask in rounds, by dependency.** A round holds only questions you can ask now: ones whose earlier answers are already known.
   Typical order: round 1 `provider`; round 2 `model`, `account`, `terms`, `spend`; round 3 `scenario_count`, `variants`, `size`,
   `output_folder`, `canary`, `on_failure`; last `go_ahead`. A provider change reopens round 2 and later.
4. **Give a recommended answer** with each question, worded so "yes" accepts it, and always allow "other". Ask through the host's
   question popup (for example `AskUserQuestion` in Claude Code, the question tool of another host; plain numbered chat if there is
   none). Up to 4 questions per popup; split a bigger round across popups.
5. **Find facts yourself, ask only decisions.** Look up anything checkable (is a CLI installed, is an account signed in, what the
   provider's documented limits are) with a cheap sub-agent or a read-only command, and show the finding next to the question. Do not
   ask the user what you can look up. Never use a lookup to decide for them.
6. Write only what the user answered: `{"value": ..., "decided_by": "user", "asked_on": "YYYY-MM-DD"}`. A recommended answer that
   the user did not accept is not an answer. If the user says "I do not know", keep the item open, explain the trade-off in two
   lines, and ask again.
7. Repeat from step 2. Stop when `check-decisions` returns `"ok": true` (it records dated answers; it cannot prove who typed them, so
   write only what the user said). `go_ahead` must be `yes`. A new run, a provider change or a failed canary reopens the items that
   changed. Do not generate anything until the user confirms the summary of their answers.

Never choose a provider, model, account, spend limit or count on your own, and never switch any of them silently mid-run.

### Optional: run it under a host goal command

Claude Code and Codex CLI have a `/goal` command that keeps the agent working until a checkable condition holds. A condition that
fits this stage: `check-decisions workspace/runs/<RUN>/generation_decisions.json prints "ok": true and the canary images were shown to the user`.
The goal loop must still stop and ask whenever an item is open; a goal never lets the agent answer for the user.

## Build an adapter (first run with a generator)

An adapter connects the user's generator to the kit. It lives in `workspace/adapters/<name>/` (never pushed). Look there first:
if an adapter for the chosen provider exists, read its `ADAPTER.md` and reuse it; only reopen the decisions that changed.

If none exists, build it with the user, one question at a time (host question popup, recommended answer first):

1. **Which generator?** Ask; do not assume. Examples: an image API (OpenAI, Gemini), Grok, Google Flow, a local model, an MCP
   tool the agent already has (for example a ChatGPT bridge). Then find the facts yourself (is the CLI installed, is the MCP
   tool listed, what the provider documents about limits and commercial use) and show them next to the next question.
2. **Which kind of adapter fits?** Script (API or CLI), tool call (MCP tool in the agent), or hand-off sheet (web app the user
   drives). Recommend the one that needs the least new software. Installing anything or creating an API key is the user's yes.
3. **Write `ADAPTER.md`**: provider, model, account name (never a key or password), the kind, the exact way to run one
   scenario, the canary size, the limits seen, and the dated answers. A script reads the key from the user's environment only.
4. **Prove it on the canary**: one or two scenarios into `workspace/runs/<RUN>/raw/`, a line each in `generation_log.tsv`,
   images shown to the user. Fix the adapter until the contract below holds, then continue on the user's go.

A hand-off sheet lists each scenario id with its prompt and the file name to save; the agent then checks that every expected
file exists, belongs to its scenario, and logs missing ones as failed. Never copy credentials, cookies or session files into
an adapter.

## Contract any provider must meet

- Input: the prompt of each scenario in `registry.json`. One output per prompt is the suggested default (Adobe wants distinct concepts); the user's `variants` answer decides.
- Output: raw images in the folder the user chose (suggested `workspace/runs/<RUN>/raw`), one per scenario, named `<scenario-id>.<ext>` (extension of the provider).
- Record per scenario: ok or failed, the provider's own error text (secrets removed), and the time. A table in the run report is enough.
- If your provider has a queue, receipts or a job runner, use it; if not, a plain loop is fine. The tool does not care.

## Rules

- **Readiness check first.** If the provider or adapter has a no-spend check (status, doctor, a paired tab), run it before any
  live call and stop on any blocker.
- **Canary first.** Generate only the canary size the user chose, open the images, and report. Continue only after the user says go.
  If the canary fails, stop and show the real error; do not run the rest. If the canary images fail QC the same way, change the
  prompts (a new run name and folder) before generating more. Replacements for terminal failures go in a new small run, so the
  original records stay intact.
- **Failure policy** is the user's answer. Default behaviour when unanswered is to stop and ask. A content failure means write a new,
  different concept, not a reroll of the same prompt.
- **Auth and quota errors** (sign-in, 401/403/404 from a session, rate or quota limits) are terminal for the run. Report cause and
  next fix; do not retry in a loop and do not try to read or move credentials.
- **Spend and terms** are the user's. Check that the provider's terms allow commercial stock use, and that Adobe's AI-content
  rules are met, only as the user states it; do not assert it.
- **Errors by kind** [REPO]: auth, quota, model-limit and "invalid output" (no image) are terminal for that job: keep the receipt,
  do not resend the same prompt. Rate limit, network and timeout are transient: retry once, then stop and ask. Stop the whole run
  after two terminal failures in a row and diagnose. A rate limit on the result poll can block a queue for about 2 hours.
- **Check every output belongs to its job**: the subject matches the scenario, and the file came from this request. A stale image
  from an older conversation or session is a failure, never a result. Start a fresh conversation per image when the provider is a chat.
- **Several images for one prompt**: keep one by a fixed rule (for example the first) and archive the rest; do not drop the call.
- **One failed image never blocks the batch**: quarantine per image; promote the passing ones.
- **Prompt length**: about 600-1000 characters worked; about 2000-character prompts returned text instead of an image (one chat
  provider, 2026-08) [REPO].
- **Prompt craft**: describe one observable business action, the physical relationships it needs, and the useful composition.
  For AI concepts, show the monitoring, verification or human sign-off action rather than relying on an invisible capability
  assigned to a generic box. Specify critical connections or routes (a sensor's dedicated cable connector; a continuous step-free
  path to the entrance). Add only constraints that prevent a concrete ambiguity; avoid blanket bans on props or long negative lists.
- **Distinct concepts**: compare the intended action and composition with earlier work before generating. A new customer problem,
  action or visual structure is more meaningful than changing only color or camera angle; it still does not guarantee acceptance.
  Repeating a prompt does not keep the same person across a series.
- Keep the provider name, model and settings in the run report. They do not go into titles or keywords [ADOBE].
- Generation success is not QC and not Adobe acceptance. Next: Source Gate on the raw, then transform and compare the final against it.
