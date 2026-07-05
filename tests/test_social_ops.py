import unittest

from argus_server.tools.social_ops import SocialOpsTools


class FakeXHSCLI:
    def __init__(self, status_result):
        self.status_result = status_result
        self.status_calls = 0
        self.xhs_calls = []

    def xhs_auth_status(self):
        self.status_calls += 1
        return self.status_result

    def run_xhs(self, subcommand, args):
        self.xhs_calls.append((subcommand, args))
        return {
            "success": True,
            "summary": {"binary": "xhs", "subcommand": subcommand},
            "data": {"args": args},
        }


def _ready_status():
    return {
        "success": True,
        "summary": {"binary": "xhs"},
        "data": {
            "installed": True,
            "authenticated": True,
            "status": "ready",
            "action_required": None,
        },
    }


def _auth_required_status():
    return {
        "success": True,
        "summary": {"binary": "xhs"},
        "data": {
            "installed": True,
            "authenticated": False,
            "status": "needs_login",
            "action_required": "manual_login_refresh",
            "error": {
                "code": "AUTH_REQUIRED",
                "message": "manual login refresh required",
            },
        },
    }


class SocialOpsToolsTest(unittest.TestCase):
    def test_xhs_feed_runs_after_auth_ready(self):
        cli = FakeXHSCLI(_ready_status())
        tool = SocialOpsTools(cli_adapter=cli)

        result = tool.xhs_feed(limit=3)

        self.assertTrue(result["success"])
        self.assertEqual(cli.status_calls, 1)
        self.assertEqual(cli.xhs_calls, [("feed", ["--limit", "3"])])

    def test_xhs_feed_blocks_when_auth_not_ready(self):
        cli = FakeXHSCLI(_auth_required_status())
        tool = SocialOpsTools(cli_adapter=cli)

        result = tool.xhs_feed(limit=3)

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "AUTH_REQUIRED")
        self.assertEqual(result["error"]["action_required"], "manual_login_refresh")
        self.assertEqual(result["error"]["auth_status"]["status"], "needs_login")
        self.assertEqual(cli.status_calls, 1)
        self.assertEqual(cli.xhs_calls, [])

    def test_xhs_comment_requires_confirm_before_auth_check(self):
        cli = FakeXHSCLI(_auth_required_status())
        tool = SocialOpsTools(cli_adapter=cli)

        result = tool.xhs_comment(note_id="note-1", text="hello", confirm=False)

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "CONFIRM_REQUIRED")
        self.assertEqual(cli.status_calls, 0)
        self.assertEqual(cli.xhs_calls, [])

    def test_xhs_comment_runs_after_confirm_and_auth_ready(self):
        cli = FakeXHSCLI(_ready_status())
        tool = SocialOpsTools(cli_adapter=cli)

        result = tool.xhs_comment(note_id="note-1", text="hello", confirm=True)

        self.assertTrue(result["success"])
        self.assertEqual(cli.status_calls, 1)
        self.assertEqual(cli.xhs_calls, [("comment", ["note-1", "--text", "hello"])])

    def test_xhs_invalid_param_skips_auth_check(self):
        cli = FakeXHSCLI(_ready_status())
        tool = SocialOpsTools(cli_adapter=cli)

        result = tool.xhs_like(note_id="")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "INVALID_PARAM")
        self.assertEqual(cli.status_calls, 0)
        self.assertEqual(cli.xhs_calls, [])


if __name__ == "__main__":
    unittest.main()
