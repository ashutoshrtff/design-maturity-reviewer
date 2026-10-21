"""
Tests for doctor.py
"""

import unittest
from pathlib import Path

from scripts.config_loader import find_repo_root
from scripts.doctor import (
    check_atlassian_env,
    check_git,
    check_knowledge_index,
    check_python_packages,
    check_python_version,
    check_skill_folder,
    run_doctor,
)


class TestDoctor(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = find_repo_root()

    def test_git_check_passes(self) -> None:
        res = check_git(self.repo_root)
        self.assertEqual(res["status"], "PASS")

    def test_python_version_check_passes(self) -> None:
        res = check_python_version()
        self.assertEqual(res["status"], "PASS")

    def test_python_packages_check_passes(self) -> None:
        res = check_python_packages()
        self.assertEqual(res["status"], "PASS")

    def test_skill_folder_check_passes(self) -> None:
        res = check_skill_folder(self.repo_root)
        self.assertEqual(res["status"], "PASS")

    def test_knowledge_index_check_existing_page(self) -> None:
        res = check_knowledge_index(self.repo_root, "123456")
        self.assertEqual(res["status"], "PASS")

    def test_knowledge_index_check_missing_page(self) -> None:
        res = check_knowledge_index(self.repo_root, "000000")
        self.assertEqual(res["status"], "FAIL")
        self.assertIn("Fix:", f"Fix: {res['fix']}")

    def test_run_doctor_overall(self) -> None:
        passed, checks = run_doctor("123456", repo_root=self.repo_root)
        self.assertTrue(passed)
        self.assertGreaterEqual(len(checks), 5)


if __name__ == "__main__":
    unittest.main()
