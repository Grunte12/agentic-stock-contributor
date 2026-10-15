"""Register this checkout's MCP server in an agent's user-level config. Dry run unless confirm_write; add or remove only our own entry."""
import json
import os
import re
import shlex
import shutil
import stat
import sys
import tempfile
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from .config import ROOT

SERVER = "adobe-stock-analytics"
BEGIN = "# >>> adobe-stock-analytics (managed) >>>"
END = "# <<< adobe-stock-analytics (managed) <<<"
# agent -> (config file under the home folder, kind). Claude Code keeps its user config in a large file it manages itself, so we print its command instead.
# Antigravity: path and shape seen in its app files and a working config on macOS (2026-10-15); not tested on Windows or Linux.
TARGETS = {"codex": (".codex/config.toml", "toml"), "opencode": (".config/opencode/opencode.json", "opencode"), "cursor": (".cursor/mcp.json", "mcpServers"),
           "antigravity": (".gemini/config/mcp_config.json", "mcpServers")}
AGENTS = ["claude", *TARGETS]


def spec():
    return {"command": sys.executable or "python3", "args": ["-m", "adobe_stock_analytics", "serve"], "env": {"PYTHONPATH": str(ROOT / "src")}}


def opencode_spec():
    s = spec()
    return {"type": "local", "command": [s["command"], *s["args"]], "environment": s["env"], "enabled": True}


def toml_block():
    s = spec()
    q = json.dumps  # a JSON string is a valid TOML basic string (Windows backslashes are escaped)
    return (f"{BEGIN}\n[mcp_servers.{SERVER}]\ncommand = {q(s['command'])}\nargs = {json.dumps(s['args'])}\n"
            f"env = {{ PYTHONPATH = {q(s['env']['PYTHONPATH'])} }}\n{END}\n")


def render(fmt):
    if fmt == "toml":
        return toml_block()
    if fmt == "opencode":
        return {"mcp": {SERVER: opencode_spec()}}
    return {"mcpServers": {SERVER: spec()}}


def claude_argv(remove=False):
    if remove:
        return ["claude", "mcp", "remove", "--scope", "user", SERVER]
    return ["claude", "mcp", "add-json", "--scope", "user", SERVER, json.dumps(spec())]


def home():
    return Path(os.path.expanduser("~"))


def _backup(path):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    dest = path.with_name(f"{path.name}.bak-{stamp}")
    n = 0
    while dest.exists():  # never overwrite an earlier backup
        n += 1
        dest = path.with_name(f"{path.name}.bak-{stamp}-{n}")
    shutil.copy2(path, dest)
    return str(dest)


def _write(path, text, crlf=False):
    path = path.resolve()  # a symlinked config (dotfiles) keeps its link; the target is updated
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
    if crlf:
        text = text.replace("\n", "\r\n")
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _read(path):
    """Text with LF newlines, and whether the file used CRLF."""
    raw = ""
    if path.exists():
        with open(path, encoding="utf-8", newline="") as f:
            raw = f.read()
    return raw.replace("\r\n", "\n"), "\r\n" in raw


class _Refuse(ValueError):
    pass


def _no_dupes(pairs):
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise _Refuse("duplicate keys")
    return dict(pairs)


def _no_const(name):
    raise _Refuse(f"unsupported number {name}")


def _float(text):
    v = float(text)
    if v != v or v in (float("inf"), float("-inf")):
        raise _Refuse(f"number {text} is out of range")
    return v


def _load_json(text):
    return json.loads(text, object_pairs_hook=_no_dupes, parse_constant=_no_const, parse_float=_float)


def _json_plan(path, kind, remove):
    key, want = ("mcp", opencode_spec()) if kind == "opencode" else ("mcpServers", spec())
    text, crlf = _read(path)
    data = {}
    if text.strip():
        if text.startswith("\ufeff"):
            return "refused", f"{path} starts with a byte-order mark; remove it or edit the file by hand", None, crlf
        try:
            data = _load_json(text)
        except (ValueError, _Refuse) as e:
            return "refused", f"{path} is not plain JSON ({e}; comments, duplicate keys or syntax); edit it by hand", None, crlf
        if not isinstance(data, dict) or not isinstance(data.get(key, {}), dict):
            return "refused", f"{path} has an unexpected shape (expected an object with an object under '{key}')", None, crlf
    servers = data.get(key, {})
    have = servers.get(SERVER)
    if remove:
        if have is None:
            return "unchanged", "entry not present", None, crlf
        del servers[SERVER]
        data[key] = servers
        return "remove", "the file is rewritten with 2-space indentation", json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n", crlf
    if have == want:
        return "unchanged", "entry already present", None, crlf
    if have is not None:
        return "refused", f"{path} already has an '{SERVER}' entry that differs; run disconnect first or edit it by hand", None, crlf
    servers[SERVER] = want
    data[key] = servers
    return ("merge" if path.exists() and text.strip() else "create"), "the file is rewritten with 2-space indentation", json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n", crlf


def _toml_plan(path, remove):
    text, crlf = _read(path)
    try:
        before = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        return "refused", f"{path} is not valid TOML ({e}); fix it by hand first", None, crlf
    managed = text.count(BEGIN) == 1 and text.count(END) == 1 and text.index(BEGIN) < text.index(END)
    if managed:
        if remove:
            start, stop = text.index(BEGIN), text.index(END) + len(END)
            stop += 1 if text[stop:stop + 1] == "\n" else 0
            start -= 1 if text[:start].endswith("\n\n") else 0  # the blank line connect added
            new = text[:start] + text[stop:]
            expect = json.loads(json.dumps(before))
            expect.get("mcp_servers", {}).pop(SERVER, None)
            if not expect.get("mcp_servers", True):
                expect.pop("mcp_servers", None)
            try:
                after = tomllib.loads(new)
            except tomllib.TOMLDecodeError:
                after = None
            if after != expect:
                return "refused", f"{path}: the managed block holds more than this tool's table (hand edits?) or sits in a string; remove it by hand", None, crlf
            return "remove", "", new, crlf
        if toml_block() in text:
            return "unchanged", "entry already present", None, crlf
        return "refused", f"{path} has an older managed block; run disconnect first", None, crlf
    if BEGIN in text or END in text:
        return "refused", f"{path} has damaged markers; fix it by hand", None, crlf
    if SERVER in before.get("mcp_servers", {}):
        return "refused", f"{path} has an '{SERVER}' table that this tool did not write; edit it by hand", None, crlf
    if remove:
        return "unchanged", "entry not present", None, crlf
    new = text + ("" if not text or text.endswith("\n") else "\n") + ("\n" if text else "") + toml_block()
    try:
        tomllib.loads(new)
    except tomllib.TOMLDecodeError as e:
        return "refused", f"the result would not be valid TOML ({e})", None, crlf
    return ("append" if path.exists() else "create"), "", new, crlf


def plan(agent, confirm_write=False, remove=False):
    if agent == "claude":
        argv = claude_argv(remove)
        return {"agent": agent, "action": "manual", "written": False, "argv": argv, "run": " ".join(shlex.quote(x) for x in argv),
                "note": "Claude Code manages its own config file. Run argv without a shell (no quoting problems); `run` is the same line for a POSIX shell"}
    rel, kind = TARGETS[agent]
    path = home() / rel
    action, reason, text, crlf = _toml_plan(path, remove) if kind == "toml" else _json_plan(path, kind, remove)
    out = {"agent": agent, "file": str(path), "action": action, "reason": reason, "written": False, "backup": None,
           "note": ("dry run: nothing written. " if not confirm_write else "") + (reason if action not in ("refused", "unchanged") else "")}
    if text is not None and confirm_write:
        if path.exists():
            out["backup"] = _backup(path)
        _write(path, text, crlf)
        out["written"] = True
        out["note"] = "restart the agent so it loads the server"
    return out


def registered():
    """Which agents' config files hold our entry (a parse of the files, not a live connection test)."""
    found = {}
    for agent, (rel, kind) in TARGETS.items():
        p = home() / rel
        try:
            if not p.is_file():
                continue
            text = p.read_text(encoding="utf-8")
            if kind == "toml":
                hit = SERVER in tomllib.loads(text).get("mcp_servers", {})
            else:
                hit = SERVER in json.loads(text).get("mcp" if kind == "opencode" else "mcpServers", {})
            if hit:
                found[agent] = str(p)
        except (OSError, ValueError):
            pass
    cj = home() / ".claude.json"
    try:
        if cj.is_file() and SERVER in json.loads(cj.read_text(encoding="utf-8")).get("mcpServers", {}):
            found["claude"] = str(cj)
    except (OSError, ValueError, AttributeError):
        pass
    return found
