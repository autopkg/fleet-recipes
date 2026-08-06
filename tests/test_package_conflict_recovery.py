#!/usr/bin/env python3
"""
Unit tests for FleetImporter's recovery from a 409 Conflict when uploading a
new software package version to a title that already has an installer.

Background: POST /api/v1/fleet/software/package only ever creates a title's
*first* installer. If the title already has one - from an earlier AutoPkg
run, or a manual upload in the Fleet UI - Fleet returns 409, even when the
new package is a genuinely different version (different hash and filename).
FleetImporter recovers by parsing the existing title's name out of Fleet's
error body and looking it up via the software/titles API, then replacing the
installer with PATCH .../software/titles/:id/package instead of skipping.

Tests cover:
1. Parsing the software title name out of Fleet's 409 error body
2. Selecting the exact-match title from a fuzzy `query` search's results

Note: These tests replicate the core logic from FleetImporter without
requiring AutoPkg dependencies, matching the pattern used by
test_auto_update.py.
"""

import json
import re
import sys
import unittest


def parse_existing_title_name(error_body):
    """
    Extract the software title name Fleet reports in a 409 error body.

    Replicated from FleetImporter._fleet_upload_package()'s 409 handling.

    Fleet's error body is JSON whose "reason" string has its embedded quotes
    escaped, e.g. raw bytes:
      {"errors": [{"reason": "SoftwareInstaller \"google-chrome-stable\"
       already exists with fleet \"Team 1\"."}]}
    We must json.loads() first to get the unescaped reason string before
    regexing it - regexing the raw JSON bytes directly would capture the
    literal backslash along with the name.
    """
    reason = error_body
    try:
        reason = json.loads(error_body).get("errors", [{}])[0].get("reason", error_body)
    except (json.JSONDecodeError, IndexError, AttributeError):
        pass
    match = re.search(r'"([^"]+)"\s+already exists', reason)
    return match.group(1) if match else None


def find_exact_match_title_id(title_name, software_titles):
    """
    Pick the title whose name exactly matches title_name from a fuzzy
    `query` search's results.

    Replicated from FleetImporter._find_software_title_id_by_name().
    """
    for title in software_titles:
        if title.get("name") == title_name:
            return title.get("id")
    return None


class TestParseExistingTitleName(unittest.TestCase):
    """Test extracting the title name from Fleet's 409 error body."""

    @staticmethod
    def _fleet_error_body(reason):
        """Build a realistic raw Fleet JSON error body for the given reason text."""
        return json.dumps(
            {
                "message": "Resource Already Exists",
                "errors": [{"name": "base", "reason": reason}],
            }
        )

    def test_parses_name_with_team_name(self):
        body = self._fleet_error_body(
            'SoftwareInstaller "google-chrome-stable" already exists with fleet "Team 1".'
        )
        self.assertEqual(parse_existing_title_name(body), "google-chrome-stable")

    def test_parses_name_without_team_name(self):
        # WithTeamName()/WithTeamID() aren't always called - the identifier
        # is still the first quoted segment immediately before "already exists".
        body = self._fleet_error_body(
            'SoftwareInstaller "Google Chrome.app" already exists.'
        )
        self.assertEqual(parse_existing_title_name(body), "Google Chrome.app")

    def test_parses_name_with_special_characters(self):
        body = self._fleet_error_body(
            'SoftwareInstaller "1Password 8 (Team)" already exists with fleet "Workstations".'
        )
        self.assertEqual(parse_existing_title_name(body), "1Password 8 (Team)")

    def test_returns_none_when_body_has_no_match(self):
        body = json.dumps({"message": "Internal Server Error"})
        self.assertIsNone(parse_existing_title_name(body))

    def test_returns_none_on_empty_body(self):
        self.assertIsNone(parse_existing_title_name(""))

    def test_returns_none_on_non_json_body(self):
        # Defensive fallback: an unexpected non-JSON body (e.g. from a proxy
        # in front of Fleet) shouldn't raise, just fail to find a name.
        self.assertIsNone(parse_existing_title_name("<html>502 Bad Gateway</html>"))

    def test_picks_identifier_immediately_before_already_exists(self):
        # Guards against a naive regex grabbing the wrong quoted substring
        # when multiple quoted segments are present.
        body = self._fleet_error_body(
            'SoftwareInstaller "google-chrome-stable" already exists with fleet "Team 1".'
        )
        self.assertEqual(parse_existing_title_name(body), "google-chrome-stable")


class TestFindExactMatchTitleId(unittest.TestCase):
    """Test picking the exact-name match out of a fuzzy title search."""

    def test_finds_exact_match_among_multiple_results(self):
        titles = [
            {"id": 10, "name": "google-chrome-stable-beta"},
            {"id": 11, "name": "google-chrome-stable"},
            {"id": 12, "name": "google-chrome-unstable"},
        ]
        self.assertEqual(find_exact_match_title_id("google-chrome-stable", titles), 11)

    def test_returns_none_when_no_exact_match(self):
        titles = [
            {"id": 10, "name": "google-chrome-stable-beta"},
        ]
        self.assertIsNone(find_exact_match_title_id("google-chrome-stable", titles))

    def test_returns_none_for_empty_results(self):
        self.assertIsNone(find_exact_match_title_id("google-chrome-stable", []))

    def test_is_case_sensitive(self):
        # Fleet's Name column comparison is exact; a case-insensitive match
        # here could resolve to the wrong title.
        titles = [{"id": 1, "name": "Google-Chrome-Stable"}]
        self.assertIsNone(find_exact_match_title_id("google-chrome-stable", titles))


def run_tests():
    """Run all tests and print results."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestParseExistingTitleName))
    suite.addTests(loader.loadTestsFromTestCase(TestFindExactMatchTitleId))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
