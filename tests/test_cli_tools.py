import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from argus_server.tools.cli_tools import CLIToolsAdapter


class CLIToolsAdapterTest(unittest.TestCase):
    def _completed(self, stdout="", stderr="", returncode=0):
        return subprocess.CompletedProcess(
            args=["xhs", "status", "--yaml"],
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )

    def test_xhs_auth_status_reports_missing_install(self):
        adapter = CLIToolsAdapter()

        with patch("argus_server.tools.cli_tools.shutil.which", return_value=None):
            result = adapter.xhs_auth_status()

        self.assertTrue(result["success"])
        self.assertFalse(result["data"]["installed"])
        self.assertFalse(result["data"]["authenticated"])
        self.assertEqual(result["data"]["status"], "not_installed")
        self.assertEqual(result["data"]["action_required"], "install_xhs_cli")

    def test_xhs_auth_status_reports_cookie_storage_error(self):
        adapter = CLIToolsAdapter()
        stderr = (
            "Traceback (most recent call last):\n"
            "PermissionError: [Errno 1] Operation not permitted: "
            "'/Users/example/.xiaohongshu-cli/cookies.json'\n"
        )

        with patch("argus_server.tools.cli_tools.shutil.which", return_value="/usr/local/bin/xhs"), \
                patch("argus_server.tools.cli_tools.subprocess.run", return_value=self._completed(stderr=stderr, returncode=1)):
            result = adapter.xhs_auth_status()

        self.assertTrue(result["success"])
        self.assertTrue(result["data"]["installed"])
        self.assertFalse(result["data"]["authenticated"])
        self.assertEqual(result["data"]["status"], "needs_login")
        self.assertEqual(result["data"]["error"]["code"], "AUTH_STORAGE_UNAVAILABLE")
        self.assertNotIn("Traceback", result["data"]["error"]["message"])
        self.assertEqual(result["data"]["action_required"], "manual_login_or_local_cookie_permission")

    def test_run_xhs_maps_cookie_traceback_to_auth_error(self):
        adapter = CLIToolsAdapter()
        stderr = (
            "Traceback (most recent call last):\n"
            "PermissionError: [Errno 1] Operation not permitted: "
            "'/Users/example/.xiaohongshu-cli/cookies.json'\n"
        )

        with patch("argus_server.tools.cli_tools.shutil.which", return_value="/usr/local/bin/xhs"), \
                patch("argus_server.tools.cli_tools.subprocess.run", return_value=self._completed(stderr=stderr, returncode=1)):
            result = adapter.run_xhs("status")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "AUTH_STORAGE_UNAVAILABLE")
        self.assertNotIn("Traceback", result["error"]["message"])

    def test_run_xhs_uses_private_writable_runtime_home(self):
        with tempfile.TemporaryDirectory() as home:
            source_dir = Path(home) / ".xiaohongshu-cli"
            source_dir.mkdir()
            source_cookie = source_dir / "cookies.json"
            source_cookie.write_text('{"a1": "secret", "saved_at": 1}')
            stdout = yaml.safe_dump(
                {"ok": True, "schema_version": "1.0", "data": {"items": []}},
                allow_unicode=True,
            )

            with patch("pathlib.Path.home", return_value=Path(home)), \
                    patch("argus_server.tools.cli_tools.shutil.which", return_value="/usr/local/bin/xhs"), \
                    patch(
                        "argus_server.tools.cli_tools.subprocess.run",
                        return_value=self._completed(stdout=stdout),
                    ) as run:
                adapter = CLIToolsAdapter()
                result = adapter.run_xhs("search", ["人工智能"])

            runtime_home = Path(run.call_args.kwargs["env"]["HOME"])
            runtime_cookie = runtime_home / ".xiaohongshu-cli" / "cookies.json"
            self.assertTrue(result["success"])
            self.assertNotEqual(runtime_home, Path(home))
            self.assertEqual(runtime_cookie.read_text(), source_cookie.read_text())
            self.assertEqual(runtime_home.stat().st_mode & 0o777, 0o700)
            self.assertEqual(runtime_cookie.stat().st_mode & 0o777, 0o600)

    def test_run_xhs_without_saved_login_does_not_start_subprocess(self):
        with tempfile.TemporaryDirectory() as home, \
                patch("pathlib.Path.home", return_value=Path(home)), \
                patch("argus_server.tools.cli_tools.shutil.which", return_value="/usr/local/bin/xhs"), \
                patch(
                    "argus_server.tools.cli_tools.subprocess.run",
                    return_value=self._completed(stderr="No saved login", returncode=1),
                ) as run:
            result = CLIToolsAdapter().run_xhs("search", ["人工智能"])

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "AUTH_REQUIRED")
        self.assertEqual(result["error"]["action_required"], "manual_login_refresh")
        run.assert_not_called()

    def test_xhs_auth_status_reports_authenticated_user(self):
        adapter = CLIToolsAdapter()
        stdout = yaml.safe_dump(
            {
                "ok": True,
                "schema_version": "1.0",
                "data": {
                    "authenticated": True,
                    "user": {"nickname": "demo"},
                },
            },
            allow_unicode=True,
        )

        with patch("argus_server.tools.cli_tools.shutil.which", return_value="/usr/local/bin/xhs"), \
                patch("argus_server.tools.cli_tools.subprocess.run", return_value=self._completed(stdout=stdout)):
            result = adapter.xhs_auth_status()

        self.assertTrue(result["success"])
        self.assertTrue(result["data"]["installed"])
        self.assertTrue(result["data"]["authenticated"])
        self.assertEqual(result["data"]["status"], "ready")
        self.assertEqual(result["data"]["user"]["nickname"], "demo")
        self.assertIsNone(result["data"]["action_required"])

    def test_run_discord_is_policy_blocked_without_starting_subprocess(self):
        adapter = CLIToolsAdapter()

        with patch("argus_server.tools.cli_tools.subprocess.run") as run:
            result = adapter.run_discord("search", ["research"])

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "POLICY_UNSUPPORTED")
        self.assertEqual(result["error"]["binary"], "discord")
        self.assertEqual(result["error"]["replacement"], "discord_bot_or_oauth2")
        run.assert_not_called()

    def test_run_telegram_status_does_not_inherit_mcp_stdin(self):
        adapter = CLIToolsAdapter()
        stdout = yaml.safe_dump(
            {
                "ok": False,
                "schema_version": "1",
                "error": {
                    "code": "auth_error",
                    "message": "EOF when reading a line",
                },
            },
            allow_unicode=True,
        )

        with patch("argus_server.tools.cli_tools.shutil.which", return_value="/usr/local/bin/tg"), \
                patch(
                    "argus_server.tools.cli_tools.subprocess.run",
                    return_value=self._completed(stdout=stdout, returncode=1),
                ) as run:
            result = adapter.run_telegram("status", timeout=5)

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "auth_error")
        self.assertIs(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertNotIn("input", run.call_args.kwargs)

    def test_exec_preserves_explicit_input_text(self):
        adapter = CLIToolsAdapter()
        stdout = yaml.safe_dump(
            {"ok": True, "schema_version": "1", "data": {"deleted": True}},
            allow_unicode=True,
        )

        with patch("argus_server.tools.cli_tools.shutil.which", return_value="/usr/local/bin/bili"), \
                patch(
                    "argus_server.tools.cli_tools.subprocess.run",
                    return_value=self._completed(stdout=stdout),
                ) as run:
            result = adapter._exec(
                "bili",
                "dynamic-delete",
                ["123"],
                input_text="yes\n",
            )

        self.assertTrue(result["success"])
        self.assertEqual(run.call_args.kwargs["input"], "yes\n")
        self.assertNotIn("stdin", run.call_args.kwargs)

    def test_check_cli_auth_marks_discord_as_policy_unsupported(self):
        adapter = CLIToolsAdapter()

        with patch("argus_server.tools.cli_tools.shutil.which", return_value=None):
            result = adapter.check_cli_auth()

        discord = result["data"]["discord"]
        self.assertFalse(discord["supported"])
        self.assertIsNone(discord["auth"])
        self.assertEqual(discord["error_code"], "POLICY_UNSUPPORTED")
        self.assertNotIn("uv tool install", discord["hint"])


if __name__ == "__main__":
    unittest.main()
