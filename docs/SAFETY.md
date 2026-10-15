# Safety, limits and terms

- **Unofficial.** This project is not made by, affiliated with or endorsed by Adobe. "Adobe" and "Adobe Stock" are trademarks of Adobe Inc.
- **Your account, your responsibility.** The extension reads Adobe Stock pages in your own browser and, only when you switch it on, puts
  files into your Uploads page. Read Adobe's Contributor Terms and the Adobe Stock generative-AI content guidelines yourself. Automated
  access can conflict with a site's terms. The defaults are conservative: one page every 25 s or more, at most 150 pages a day, no
  retries, stop on CAPTCHA, sign-in, restriction, 403 or 429, and only the user can resume.
- **The tool never clicks Submit or Delete**, never reads cookies or passwords, never solves CAPTCHAs, and never uploads a protected
  folder. Staging and metadata are off until you turn the switch on in `config/stock_analytics.json`.
- **No guarantees.** Local checks (`check-images`, `check-qc`, `prepare-plan`) are not Adobe acceptance. A reviewer pass is not an Adobe
  forecast. Market numbers describe public search pages on the day they were read. Nothing here predicts sales or acceptance.
- **Generation is yours to license.** If you use a ChatGPT/Gemini/etc. web session or another account for image generation, check that
  service's terms. This project does not include or recommend any session-capture tool.
- **Privacy.** Data stays on your machine in `data/` (git-ignored): raw page observations, your portfolio, the pairing token. The
  dashboard link and the pairing token are private. Do not commit `data/`, `extension/token.js`, `runs/` or your own `.mcp.json`.
- **Community tips** in `knowledge/` are dated anecdotes with a strength tag, not Adobe rules.

## Known limits of the extension
- The metadata step can only answer "No" to "Add recognizable people or property?"; for "Yes" or "Later" set it by hand (the tool refuses those settings).
- The portal's page structure can change; the extension stops on an unknown shape. Try one file first.
- `doctor` creates the local pairing token in `data/` if it does not exist. `print-mcp-config` ignores `--data-dir` (it prints this checkout's paths).
