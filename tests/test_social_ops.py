import unittest

from argus_server.tools.social_ops import SocialOpsTools


class FakeXHSCLI:
    def __init__(self, status_result, data_by_subcommand=None):
        self.status_result = status_result
        self.data_by_subcommand = data_by_subcommand or {}
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
            "data": self.data_by_subcommand.get(subcommand, {"args": args}),
        }


class FakeBiliCLI:
    def __init__(self, data_by_subcommand=None):
        self.data_by_subcommand = data_by_subcommand or {}
        self.bili_calls = []

    def run_bilibili(self, subcommand, args):
        self.bili_calls.append((subcommand, args))
        return {
            "success": True,
            "summary": {"binary": "bili", "subcommand": subcommand},
            "data": self.data_by_subcommand.get(subcommand, {"args": args}),
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
    def test_bili_read_commands_match_official_cli_contract_and_limit_results(self):
        source_items = [{"id": index} for index in range(5)]
        cli = FakeBiliCLI(
            {
                "my-dynamics": {"items": source_items},
                "history": {"items": source_items},
                "following": {"items": source_items},
                "feed": {"items": source_items},
                "hot": {"items": source_items},
            }
        )
        tool = SocialOpsTools(cli_adapter=cli)

        results = [
            tool.bili_my_dynamics(limit=2),
            tool.bili_history(limit=2),
            tool.bili_following(limit=2),
            tool.bili_feed(limit=2),
            tool.bili_hot(limit=2),
        ]

        self.assertEqual(
            cli.bili_calls,
            [
                ("my-dynamics", ["--max", "2"]),
                ("history", ["--max", "2"]),
                ("following", []),
                ("feed", []),
                ("hot", ["--max", "2"]),
            ],
        )
        for result in results:
            self.assertEqual(len(result["data"]["items"]), 2)

    def test_bili_interactions_match_official_cli_contract(self):
        cli = FakeBiliCLI()
        tool = SocialOpsTools(cli_adapter=cli)

        self.assertTrue(tool.bili_like("BV1test12345")["success"])
        self.assertTrue(tool.bili_triple("BV1test12345")["success"])

        self.assertEqual(
            cli.bili_calls,
            [
                ("like", ["BV1test12345"]),
                ("triple", ["BV1test12345"]),
            ],
        )

    def test_bili_writes_require_confirmation_and_use_noninteractive_contract(self):
        cli = FakeBiliCLI()
        tool = SocialOpsTools(cli_adapter=cli)

        publish_blocked = tool.bili_publish_dynamic("hello", confirm=False)
        delete_blocked = tool.bili_delete_dynamic("123456", confirm=False)
        self.assertEqual(publish_blocked["error"]["code"], "CONFIRM_REQUIRED")
        self.assertEqual(delete_blocked["error"]["code"], "CONFIRM_REQUIRED")
        self.assertEqual(cli.bili_calls, [])

        self.assertTrue(tool.bili_publish_dynamic("hello", confirm=True)["success"])
        self.assertTrue(tool.bili_delete_dynamic("123456", confirm=True)["success"])
        self.assertEqual(
            cli.bili_calls,
            [
                ("dynamic-post", ["hello"]),
                ("dynamic-delete", ["123456", "--yes"]),
            ],
        )

    def test_bili_invalid_identifier_does_not_start_cli(self):
        cli = FakeBiliCLI()
        tool = SocialOpsTools(cli_adapter=cli)

        result = tool.bili_like("")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "INVALID_PARAM")
        self.assertEqual(cli.bili_calls, [])

    def test_xhs_feed_runs_after_auth_ready(self):
        cli = FakeXHSCLI(_ready_status())
        tool = SocialOpsTools(cli_adapter=cli)

        result = tool.xhs_feed(limit=3)

        self.assertTrue(result["success"])
        self.assertEqual(cli.status_calls, 1)
        self.assertEqual(cli.xhs_calls, [("feed", [])])

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
        self.assertEqual(cli.xhs_calls, [("comment", ["note-1", "--content", "hello"])])

    def test_xhs_read_commands_match_installed_cli_contract_and_limit_locally(self):
        source_items = [{"id": index} for index in range(5)]
        cli = FakeXHSCLI(
            _ready_status(),
            data_by_subcommand={
                "my-notes": {"notes": source_items},
                "notifications": {"items": source_items},
                "favorites": {"notes": source_items},
                "feed": {"items": source_items},
                "hot": source_items,
                "comments": {"comments": source_items},
            },
        )
        tool = SocialOpsTools(cli_adapter=cli)

        results = [
            tool.xhs_my_notes(limit=2),
            tool.xhs_notifications(limit=2),
            tool.xhs_favorites(limit=2),
            tool.xhs_feed(limit=2),
            tool.xhs_hot(category="travel", limit=2),
            tool.xhs_comments(note_id="note-1", limit=2),
        ]

        self.assertEqual(
            cli.xhs_calls,
            [
                ("my-notes", []),
                ("notifications", ["--num", "2"]),
                ("favorites", []),
                ("feed", []),
                ("hot", ["--category", "travel"]),
                ("comments", ["note-1"]),
            ],
        )
        for result in results:
            data = result["data"]
            if isinstance(data, list):
                self.assertEqual(len(data), 2)
            else:
                values = next(value for value in data.values() if isinstance(value, list))
                self.assertEqual(len(values), 2)

    def test_xhs_confirmed_write_commands_match_installed_cli_contract(self):
        cli = FakeXHSCLI(_ready_status())
        tool = SocialOpsTools(cli_adapter=cli)

        self.assertTrue(tool.xhs_comment("note-1", "hello", confirm=True)["success"])
        self.assertTrue(
            tool.xhs_publish_note(
                ["one.jpg", "two.jpg"], "title", "body", confirm=True
            )["success"]
        )
        self.assertTrue(tool.xhs_delete_note("note-1", confirm=True)["success"])

        self.assertEqual(
            cli.xhs_calls,
            [
                ("comment", ["note-1", "--content", "hello"]),
                (
                    "post",
                    [
                        "--title",
                        "title",
                        "--body",
                        "body",
                        "--images",
                        "one.jpg",
                        "--images",
                        "two.jpg",
                    ],
                ),
                ("delete", ["note-1", "--yes"]),
            ],
        )

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
