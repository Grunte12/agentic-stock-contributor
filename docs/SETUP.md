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
