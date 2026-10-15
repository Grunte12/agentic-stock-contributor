# Instructions for AI agents working in this repository

This repo is an Adobe Stock contributor toolkit: a Chrome extension, an MCP server (`stock_*` tools), local batch commands, a skill
and a know-how library. If a user asks you to help with Adobe Stock work, load the skill and follow it.

1. Read `skills/adobe-stock/SKILL.md`, then call `stock_knowledge` (topic `index`, then `mindset`) if the MCP server is connected;
   otherwise read `knowledge/*.md` directly.
2. Installing for a user (they may not be technical): follow `INSTALL.md` exactly. Manual setup details: `docs/SETUP.md`. First check: `python3 stock.py doctor`.
3. Hard rules: never click Submit or upload on your own; never invent a number (write `unmeasured`); stop on CAPTCHA, sign-in, 403/429
   and never retry; stage files only when the user asked in chat for that run and turned the config switch on.
4. When changing this repo: run `cd tests && python3 -m unittest discover -p 'test_*.py'` (stdlib only, no network). Bump
   `extension/manifest.json` and add a line to `CHANGELOG.md` for any change under `extension/`. Do not commit tokens, `data/`,
   `runs/` or your own `.mcp.json`.
