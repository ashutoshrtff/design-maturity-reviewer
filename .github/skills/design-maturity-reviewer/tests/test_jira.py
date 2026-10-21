"""
Tests for fetch_jira_ticket.py
"""

import unittest
from pathlib import Path

from scripts.config_loader import find_repo_root
from scripts.fetch_jira_ticket import fetch_from_file, parse_acceptance_criteria


class TestJiraFetch(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = find_repo_root()
        self.fixture_path = (
            self.repo_root
            / ".github"
            / "skills"
            / "design-maturity-reviewer"
            / "examples"
            / "fixtures"
            / "jira_PAY-123.json"
        )

    def test_parse_checkbox_acceptance_criteria(self) -> None:
        text = (
            "h3. Acceptance Criteria\n"
            "- [x] Validate presence of Idempotency-Key header\n"
            "- [ ] Return HTTP 409 Conflict if duplicate request\n"
        )
        acs = parse_acceptance_criteria(text)
        self.assertEqual(len(acs), 2)
        self.assertIn("Validate presence of Idempotency-Key header", acs[0])
        self.assertIn("Return HTTP 409 Conflict if duplicate request", acs[1])

    def test_parse_gherkin_acceptance_criteria(self) -> None:
        text = (
            "Scenario: Concurrent settlement request\n"
            "Given a pending settlement for idempotency key 'ABC-123'\n"
            "When another request arrives with the same key\n"
            "Then return HTTP 409 with IDEMPOTENCY_CONCURRENT_REQUEST\n"
        )
        acs = parse_acceptance_criteria(text)
        self.assertGreaterEqual(len(acs), 3)
        self.assertTrue(any("Given a pending settlement" in a for a in acs))

    def test_fetch_from_file_fixture(self) -> None:
        ticket = fetch_from_file(self.fixture_path)
        self.assertEqual(ticket["key"], "PAY-123")
        self.assertEqual(ticket["status"], "In Progress")
        self.assertGreater(len(ticket["acceptance_criteria"]), 0)
        self.assertIn("payments", ticket["labels"])


if __name__ == "__main__":
    unittest.main()
