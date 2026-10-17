# adapters/ (your image generator, stage 6)

The kit does not generate images and is not tied to one generator. This folder holds **your** adapter: the small piece that
takes the prompts in a run's `registry.json` and puts images in that run's `raw/` folder. Each user has their own; it is never
pushed. Full rules: knowledge topic `generation`, section "Build an adapter".

```text
adapters/<name>/
  ADAPTER.md       what it is, how to run it, what the user decided (provider, model, account name only, limits)
  run.py | run.sh  optional: a script, when the generator has an API or a CLI
```

Kinds of generator and what the adapter usually is:

| Generator | Adapter |
|---|---|
| Image API (OpenAI, Gemini, others) | a script that reads `registry.json` and calls the API; the key stays in the user's environment, never in a file here |
| CLI or local model | a script that calls the CLI per scenario |
| An MCP tool in the agent (for example a ChatGPT bridge) | no script: `ADAPTER.md` says which tool to call per scenario and how to save the result |
| Web app only (Google Flow, Grok, others) | no script: `ADAPTER.md` is a hand-off sheet; the user generates, saves files as `<scenario-id>.<ext>` in `raw/`, and the agent checks names and logs results |

Every adapter must meet the same contract: one image per scenario in `workspace/runs/<RUN>/raw/<scenario-id>.<ext>`, and one
line per scenario in `workspace/runs/<RUN>/generation_log.tsv` (`scenario_id`, `status` ok|failed, `error`, `time`). Stage 7
starts from `raw/` and does not care which adapter made it.
