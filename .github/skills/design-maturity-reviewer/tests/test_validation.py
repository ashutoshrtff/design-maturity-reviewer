"""
Tests for validate_report.py (Anti-hallucination gate)
"""

import unittest
from pathlib import Path

from scripts.git_context import resolve_git_context
from scripts.validate_report import validate_assessment_report
from tests.helpers import TempGitRepo


class TestValidationReport(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = TempGitRepo()
        code = (
            "def handle_payment():\n"
            "    print('real code')\n"
            "    return True\n"
        )
        self.repo.commit_file("src/pay.py", code, "Add real pay")
        self.repo.push_to_origin("main")
        self.ctx = resolve_git_context(repo_root=self.repo.path, no_fetch=True)

    def tearDown(self) -> None:
        self.repo.cleanup()

    def test_implemented_without_evidence_fails_loudly(self) -> None:
        assessments = [
            {
                "requirement_id": "R-001",
                "status": "Implemented",
                "evidence": [],  # Empty evidence!
            }
        ]
        passed, errors = validate_assessment_report(assessments, self.ctx)
        self.assertFalse(passed)
        self.assertTrue(any("without any code evidence" in e for e in errors))

    def test_fabricated_file_fails(self) -> None:
        assessments = [
            {
                "requirement_id": "R-001",
                "status": "Implemented",
                "evidence": [
                    {
                        "file_path": "src/fabricated_nonexistent.py",
                        "line_number": 10,
                        "snippet": "some code",
                    }
                ],
            }
        ]
        passed, errors = validate_assessment_report(assessments, self.ctx)
        self.assertFalse(passed)
        self.assertTrue(any("does not exist" in e for e in errors))

    def test_fabricated_line_number_fails(self) -> None:
        assessments = [
            {
                "requirement_id": "R-001",
                "status": "Implemented",
                "evidence": [
                    {
                        "file_path": "src/pay.py",
                        "line_number": 9999,  # file only has 3 lines!
                        "snippet": "print('real code')",
                    }
                ],
            }
        ]
        passed, errors = validate_assessment_report(assessments, self.ctx)
        self.assertFalse(passed)
        self.assertTrue(any("out of bounds" in e for e in errors))

    def test_mismatched_snippet_fails(self) -> None:
        assessments = [
            {
                "requirement_id": "R-001",
                "status": "Implemented",
                "evidence": [
                    {
                        "file_path": "src/pay.py",
                        "line_number": 2,
                        "snippet": "fabricated_function_call_not_in_file()",
                    }
                ],
            }
        ]
        passed, errors = validate_assessment_report(assessments, self.ctx)
        self.assertFalse(passed)
        self.assertTrue(any("does not match content" in e for e in errors))

    def test_genuine_evidence_passes(self) -> None:
        assessments = [
            {
                "requirement_id": "R-001",
                "status": "Implemented",
                "evidence": [
                    {
                        "file_path": "src/pay.py",
                        "line_number": 2,
                        "snippet": "def handle_payment():\n    print('real code')",
                    }
                ],
            }
        ]
        passed, errors = validate_assessment_report(assessments, self.ctx)
        self.assertTrue(passed)
        self.assertEqual(len(errors), 0)


if __name__ == "__main__":
    unittest.main()
