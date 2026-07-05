import subprocess
import unittest
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


if __name__ == "__main__":
    unittest.main()
