import tempfile
import unittest
from pathlib import Path

import yaml

from argus_server.tools.config_mgmt import ConfigManagementTools


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_TEMPLATE = PROJECT_ROOT / "config" / "config.example.yaml"


class ConfigInitializationTest(unittest.TestCase):
    def _tools(self, tmpdir, template_text=None):
        config_dir = Path(tmpdir) / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        if template_text is not None:
            (config_dir / "config.example.yaml").write_text(
                template_text,
                encoding="utf-8",
            )
        return ConfigManagementTools(tmpdir)

    def test_initialize_config_creates_valid_config_from_template(self):
        template_text = PROJECT_TEMPLATE.read_text(encoding="utf-8")
        template_data = yaml.safe_load(template_text)
        with tempfile.TemporaryDirectory() as tmpdir:
            tools = self._tools(tmpdir, template_text)

            response = tools.initialize_config()

            target = Path(tmpdir) / "config" / "config.yaml"
            self.assertTrue(response["success"])
            self.assertTrue(response["summary"]["created"])
            self.assertEqual(response["summary"]["status"], "created")
            self.assertEqual(response["data"]["config_path"], "config/config.yaml")
            self.assertEqual(response["data"]["template_path"], "config/config.example.yaml")
            self.assertEqual(response["data"]["platform_count"], len(template_data["platforms"]["sources"]))
            self.assertEqual(response["data"]["rss_feed_count"], len(template_data["rss"]["feeds"]))
            self.assertEqual(target.read_text(encoding="utf-8"), template_text)
            self.assertEqual(yaml.safe_load(target.read_text(encoding="utf-8")), template_data)

    def test_initialize_config_is_idempotent_and_never_overwrites_existing_config(self):
        template_text = PROJECT_TEMPLATE.read_text(encoding="utf-8")
        existing_text = """app: {}
platforms:
  sources:
    - id: custom
report: {}
notification: {}
advanced: {}
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tools = self._tools(tmpdir, template_text)
            target = Path(tmpdir) / "config" / "config.yaml"
            target.write_text(existing_text, encoding="utf-8")

            response = tools.initialize_config()

            self.assertTrue(response["success"])
            self.assertFalse(response["summary"]["created"])
            self.assertEqual(response["summary"]["status"], "exists")
            self.assertEqual(target.read_text(encoding="utf-8"), existing_text)

    def test_initialize_config_rejects_invalid_existing_config_without_overwrite(self):
        template_text = PROJECT_TEMPLATE.read_text(encoding="utf-8")
        existing_text = "platforms: []\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            tools = self._tools(tmpdir, template_text)
            target = Path(tmpdir) / "config" / "config.yaml"
            target.write_text(existing_text, encoding="utf-8")

            response = tools.initialize_config()

            self.assertFalse(response["success"])
            self.assertEqual(response["error"]["code"], "CONFIG_EXISTS_INVALID")
            self.assertEqual(target.read_text(encoding="utf-8"), existing_text)

    def test_initialize_config_reports_missing_template(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tools = self._tools(tmpdir)

            response = tools.initialize_config()

            self.assertFalse(response["success"])
            self.assertEqual(response["error"]["code"], "TEMPLATE_NOT_FOUND")
            self.assertFalse((Path(tmpdir) / "config" / "config.yaml").exists())

    def test_initialize_config_reports_invalid_template_without_creating_target(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tools = self._tools(tmpdir, "platforms: []\n")

            response = tools.initialize_config()

            self.assertFalse(response["success"])
            self.assertEqual(response["error"]["code"], "TEMPLATE_INVALID")
            self.assertFalse((Path(tmpdir) / "config" / "config.yaml").exists())

if __name__ == "__main__":
    unittest.main()
