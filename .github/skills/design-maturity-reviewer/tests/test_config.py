"""
Tests for config_loader.py
"""

import tempfile
import unittest
from pathlib import Path

from scripts.config_loader import find_repo_root, load_config


class TestConfigLoader(unittest.TestCase):
    def test_default_config_fallback(self) -> None:
        cfg = load_config(config_path="nonexistent_config.yml")
        self.assertIn("design_pages", cfg)
        self.assertEqual(cfg["code"]["default_ref"], "origin/main")
        self.assertEqual(cfg["design_context"]["top_k"], 8)
        self.assertEqual(cfg["status_dir"], "design-status")

    def test_custom_config_loading(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False) as f:
            f.write(
                "design_pages:\n"
                "  - page_id: '999999'\n"
                "code:\n"
                "  default_ref: 'origin/master'\n"
            )
            temp_path = f.name

        try:
            cfg = load_config(config_path=temp_path)
            self.assertEqual(cfg["design_pages"][0]["page_id"], "999999")
            self.assertEqual(cfg["code"]["default_ref"], "origin/master")
            self.assertEqual(cfg["knowledge"]["index_dir"], "knowledge-index")
        finally:
            Path(temp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
