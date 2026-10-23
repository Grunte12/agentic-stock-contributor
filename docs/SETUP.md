# Setup (about 10 minutes)

An AI agent can do most of this for you: give it the repository link and ask it to follow [INSTALL.md](../INSTALL.md). The steps below are the manual version.

You need: Python 3.11+, Chrome 116+, an AI agent that supports MCP servers (Claude Code, Codex CLI, Cursor, Antigravity; also OpenCode or any
MCP client), and an Adobe Stock contributor account (only for portfolio, outcomes and upload staging; market scans work without login).

## 1. Get the code

```bash
git clone <this repository> adobe-stock-analytics
cd adobe-stock-analytics
python3 stock.py doctor
```

No `pip install` is needed (standard library only). Optional: `python3 -m pip install Pillow` for `qc-tiles`.
To get a `adobe-stock-analytics` command instead: `python3 -m pip install -e .`.

## 2. Connect the MCP server to your agent

Print the config for this checkout and paste it into your agent's MCP settings:

```bash
python3 stock.py print-mcp-config
```

| Agent | Where it goes |
|---|---|
| Claude Code | `claude mcp add-json adobe-stock-analytics '<the inner JSON>'`, or a project `.mcp.json` (see `.mcp.json.example`) |
| Codex CLI | `~/.codex/config.toml`: `[mcp_servers.adobe-stock-analytics]` with `command`, `args`, and `env = { PYTHONPATH = "..." }` |
| OpenCode | `opencode.json` under `"mcp"`: `{"type": "local", "command": ["python3","-m","adobe_stock_analytics","serve"], "environment": {"PYTHONPATH": "..."}}` |
| Cursor | `~/.cursor/mcp.json` under `"mcpServers"`, same `command`, `args`, `env` |
| Antigravity | `~/.gemini/config/mcp_config.json` under `"mcpServers"`, same `command`, `args`, `env` (seen on macOS) |
| other | the client's MCP JSON, same `command`, `args`, `env` |

Or let the tool do it (dry run first; backs up; adds only its own entry): `python3 stock.py connect --agent claude|codex|cursor|antigravity|opencode`, undo with `disconnect`.

Restart the agent session after changing MCP settings.

## 3. Load the Chrome extension

```bash
python3 stock.py write-extension-token
```

Chrome, then `chrome://extensions`, Developer mode, Load unpacked, choose the `extension/` folder. A Chrome profile that is signed out
of Adobe is recommended for market scans. Click the extension button to open the dashboard once the MCP server runs.

## 4. Install the skill (the playbook and know-how)

```bash
python3 stock.py install-skill --agent claude            # dry run: shows the target
python3 stock.py install-skill --agent claude --confirm-write
```

`--agent` is `claude` (`~/.claude/skills`), `codex` or `agents` (`~/.agents/skills`), or `opencode` (`~/.config/opencode/skills`);
`--dest DIR` sets any other folder. Agents without a skills folder can call the MCP tool `stock_knowledge` instead; it serves the same
know-how from the running server.

## 5. Check

In your agent, say: "Use the adobe-stock skill. Call stock_status." Expected: `bridge_connected: true`. Then try a scan:
"Measure supply for the phrase 'christmas baking' and show the report." (3 scans per phrase, one page every 25 s or more.)

## 6. Turn on upload staging (optional, per run)

Edit `config/stock_analytics.json`: `upload_stage.enabled` and `upload_metadata.enabled` are `false` by default. Turn them on only for a
run, and off after. Staging fills the portal's New list; **you** click Submit.

## Bring your own generator and upscaler

The workflow needs images, but this tool does not make them. Use any generator you are licensed to use. After Source Gate, test one
canary and choose the least-transformative resize or upscaler that reaches 4 MP without visible regression. The workflow only needs
the final JPEGs and a registry (see `examples/`). Read `docs/SAFETY.md` first.

Choose from what the user actually has; none of these services is required:

| Available capability | Route |
|---|---|
| GPT Bridge and a ChatGPT account with **Create image** available | Use the Bridge adapter. ChatGPT Free works, but image generation has a separate, stricter and changing limit; stop when ChatGPT reports the limit. Paid plans have higher limits, not a promised count. |
| ChatGPT, but no GPT Bridge | Either [install GPT Bridge](https://github.com/Grunte12/gpt-bridge#install-agent-integrations) locally or use the adapter's hand-off sheet and save each result under its scenario filename. Installation is optional. |
| Another generator | Use an API/CLI adapter when one already exists; otherwise use a hand-off sheet. The raw-file contract stays the same. |
| Google AI Pro or paid Colab compute | A Colab adapter may batch transforms, verify downloads, then release the runtime. Availability and consumption still vary. |
| Colab Free | An interactive notebook may receive a free GPU, but it is not guaranteed and free managed runtimes can terminate. Do not rely on it for unattended automation. |
| No Colab or cloud GPU | Resize locally when the clean source already has enough detail; otherwise use a local upscaler such as Real-ESRGAN/Upscayl when the machine supports it. If neither route preserves quality, keep the file out rather than enlarge it blindly. |

Current plan facts can change. Check [OpenAI's Free Tier FAQ](https://help.openai.com/en/articles/9275245-chatgpt-free-tier-faq),
[ChatGPT Images availability](https://help.openai.com/en/articles/11084440-images-in-chatgpt), and
[Google's Colab FAQ](https://research.google.com/colaboratory/faq.html) before promising capacity.
