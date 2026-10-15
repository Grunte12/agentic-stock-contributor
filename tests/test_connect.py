import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import CFG  # noqa: F401  (adds src to sys.path)
from adobe_stock_analytics import connect as C


class ConnectTests(unittest.TestCase):
    def setUp(self):
        self.h = Path(tempfile.mkdtemp())
        p = mock.patch.dict(os.environ, {"HOME": str(self.h), "USERPROFILE": str(self.h)})
        p.start()
        self.addCleanup(p.stop)

    def test_dry_run_writes_nothing(self):
        for agent in ("codex", "opencode", "cursor", "antigravity"):
            r = C.plan(agent)
            self.assertEqual(r["action"], "create")
            self.assertFalse(r["written"])
        self.assertEqual(list(self.h.rglob("*")), [])

    def test_claude_prints_command_only(self):
        r = C.plan("claude", confirm_write=True)
        self.assertEqual(r["action"], "manual")
        self.assertIn("claude mcp add-json", r["run"])
        self.assertEqual(list(self.h.rglob("*")), [])

    def test_json_merge_keeps_other_servers_and_backs_up(self):
        f = self.h / ".cursor" / "mcp.json"
        f.parent.mkdir()
        f.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}, "keep": 1}))
        r = C.plan("cursor", True)
        self.assertEqual((r["action"], r["written"]), ("merge", True))
        data = json.loads(f.read_text())
        self.assertEqual(data["mcpServers"]["other"], {"command": "x"})
        self.assertEqual(data["keep"], 1)
        self.assertIn(C.SERVER, data["mcpServers"])
        self.assertTrue(Path(r["backup"]).is_file())
        self.assertEqual(C.plan("cursor", True)["action"], "unchanged")
        d = C.plan("cursor", True, remove=True)
        self.assertEqual(d["action"], "remove")
        after = json.loads(f.read_text())
        self.assertEqual(after["mcpServers"], {"other": {"command": "x"}})

    def test_refuses_unparseable_or_different_entry(self):
        f = self.h / ".config" / "opencode" / "opencode.json"
        f.parent.mkdir(parents=True)
        f.write_text('{ // comment\n "mcp": {} }')
        r = C.plan("opencode", True)
        self.assertEqual((r["action"], r["written"]), ("refused", False))
        self.assertEqual(f.read_text(), '{ // comment\n "mcp": {} }')
        f.write_text(json.dumps({"mcp": {C.SERVER: {"type": "local", "command": ["elsewhere"]}}}))
        self.assertEqual(C.plan("opencode", True)["action"], "refused")

    def test_toml_append_preserves_text_and_round_trips(self):
        import tomllib
        f = self.h / ".codex" / "config.toml"
        f.parent.mkdir()
        original = '# my notes\nmodel = "x"\n\n[mcp_servers.other]\ncommand = "y"\n'
        f.write_text(original)
        r = C.plan("codex", True)
        self.assertEqual((r["action"], r["written"]), ("append", True))
        text = f.read_text()
        self.assertTrue(text.startswith(original))
        t = tomllib.loads(text)
        self.assertEqual(t["mcp_servers"][C.SERVER]["args"], ["-m", "adobe_stock_analytics", "serve"])
        self.assertIn("PYTHONPATH", t["mcp_servers"][C.SERVER]["env"])
        self.assertEqual(C.plan("codex", True)["action"], "unchanged")
        C.plan("codex", True, remove=True)
        self.assertEqual(f.read_text().strip(), original.strip())

    def test_toml_refuses_foreign_table_and_bad_toml(self):
        f = self.h / ".codex" / "config.toml"
        f.parent.mkdir()
        f.write_text('[mcp_servers.adobe-stock-analytics]\ncommand = "mine"\n')
        self.assertEqual(C.plan("codex", True)["action"], "refused")
        self.assertEqual(C.plan("codex", True, remove=True)["action"], "refused")
        f.write_text("not = [valid")
        self.assertEqual(C.plan("codex", True)["action"], "refused")

    def test_windows_style_path_is_valid_toml(self):
        import tomllib
        with mock.patch.object(C, "spec", return_value={"command": "C:\\Python 3\\python.exe", "args": ["-m", "adobe_stock_analytics", "serve"],
                                                          "env": {"PYTHONPATH": "C:\\Users\\a b\\repo\\src"}}):
            t = tomllib.loads(C.toml_block())
        self.assertEqual(t["mcp_servers"][C.SERVER]["command"], "C:\\Python 3\\python.exe")

    def test_registered_reports_connected_agents(self):
        self.assertEqual(C.registered(), {})
        C.plan("cursor", True)
        self.assertIn("cursor", C.registered())


    def test_antigravity_merges_into_existing_servers(self):
        f = self.h / ".gemini" / "config" / "mcp_config.json"
        f.parent.mkdir(parents=True)
        f.write_text(json.dumps({"mcpServers": {"other": {"command": "x", "args": [], "env": {}}}}))
        r = C.plan("antigravity", True)
        self.assertEqual(r["action"], "merge")
        d = json.loads(f.read_text())
        self.assertEqual(set(d["mcpServers"]), {"other", C.SERVER})
        self.assertIn("antigravity", C.registered())
        C.plan("antigravity", True, remove=True)
        self.assertEqual(set(json.loads(f.read_text())["mcpServers"]), {"other"})


class InstallDocTests(unittest.TestCase):
    def test_every_command_in_install_md_exists(self):
        import re
        from adobe_stock_analytics import cli
        text = (Path(__file__).resolve().parents[1] / "INSTALL.md").read_text(encoding="utf-8")
        cmds = set(re.findall(r"stock\.py ([a-z-]+)", text))
        self.assertTrue({"doctor", "connect", "install-skill", "write-extension-token", "print-mcp-config"} <= cmds)
        for c in cmds:
            with self.assertRaises(SystemExit) as e:  # --help exits 0 only for a known command
                cli.main([c, "--help"])
            self.assertEqual(e.exception.code, 0, c)


class HardeningTests(ConnectTests):
    def test_backup_never_overwritten(self):
        f = self.h / ".cursor" / "mcp.json"
        f.parent.mkdir()
        f.write_text("{}")
        a = C.plan("cursor", True)["backup"]
        b = C.plan("cursor", True, remove=True)["backup"]
        self.assertNotEqual(a, b)
        self.assertEqual(Path(a).read_text(), "{}")

    def test_symlink_and_mode_preserved(self):
        real = self.h / "dotfiles" / "mcp.json"
        real.parent.mkdir()
        real.write_text("{}")
        os.chmod(real, 0o644)
        link = self.h / ".cursor" / "mcp.json"
        link.parent.mkdir()
        link.symlink_to(real)
        C.plan("cursor", True)
        self.assertTrue(link.is_symlink())
        self.assertIn(C.SERVER, real.read_text())
        self.assertEqual(oct(real.stat().st_mode & 0o777), "0o644")

    def test_crlf_kept(self):
        f = self.h / ".codex" / "config.toml"
        f.parent.mkdir()
        f.write_bytes(b'model = "x"\r\n')
        C.plan("codex", True)
        raw = f.read_bytes()
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))
        C.plan("codex", True, remove=True)
        self.assertEqual(f.read_bytes(), b'model = "x"\r\n')

    def test_duplicate_keys_and_infinity_refused(self):
        f = self.h / ".cursor" / "mcp.json"
        f.parent.mkdir()
        f.write_text('{"mcpServers": {"a": {}}, "mcpServers": {"b": {}}}')
        self.assertEqual(C.plan("cursor", True)["action"], "refused")
        f.write_text('{"x": 1e400}')
        self.assertEqual(C.plan("cursor", True)["action"], "refused")
        f.write_text("   \n")
        self.assertEqual(C.plan("cursor")["action"], "create")

    def test_disconnect_refuses_hand_edited_block_and_bad_markers(self):
        f = self.h / ".codex" / "config.toml"
        f.parent.mkdir()
        C.plan("codex", True)
        text = f.read_text().replace(C.END, '[mcp_servers.mine]\ncommand = "z"\n' + C.END)
        f.write_text(text)
        self.assertEqual(C.plan("codex", True, remove=True)["action"], "refused")
        self.assertIn("mine", f.read_text())
        f.write_text(f"{C.END}\n{C.BEGIN}\n")
        self.assertEqual(C.plan("codex", True)["action"], "refused")

    def test_claude_argv_and_registered(self):
        r = C.plan("claude")
        self.assertEqual(r["argv"][:5], ["claude", "mcp", "add-json", "--scope", "user"])
        self.assertEqual(json.loads(r["argv"][-1])["args"][-1], "serve")
        (self.h / ".claude.json").write_text(json.dumps({"mcpServers": {C.SERVER: {}}}))
        self.assertIn("claude", C.registered())




if __name__ == "__main__":
    unittest.main()
