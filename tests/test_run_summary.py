#!/usr/bin/env python3
"""
Unit tests for FleetImporter._build_run_summary().

This method builds the AutoPkg summary result ("fleet_importer_summary_result")
that appears at the end of every run, so regressions here are visible to every
recipe consumer. It previously crashed with a TypeError in GitOps mode by
indexing the report_fields *list* as if it were a dict
("report_fields"]["data"]["git_branch"]), which took down every GitOps run at
the summary step.

Unlike the other test modules, these import the real FleetImporter so the actual
implementation is exercised; AutoPkg is stubbed so it can run without AutoPkg
installed.
"""

import os
import sys
import types
import unittest

# PyYAML's libyaml C-extension currently segfaults on import under Python 3.14+
# (see test_style_guide_compliance.py). FleetImporter imports yaml, so guard.
if sys.version_info >= (3, 14):
    sys.stderr.write(
        "ERROR: Python {}.{} is not supported for this test suite. "
        "Use Python 3.13 (see .python-version).\n".format(
            sys.version_info.major, sys.version_info.minor
        )
    )
    sys.exit(1)

# Stub the autopkglib module so FleetImporter imports without AutoPkg installed.
if "autopkglib" not in sys.modules:
    _stub = types.ModuleType("autopkglib")

    class _Processor:
        def __init__(self):
            self.env = {}

        def output(self, msg):
            pass

    class _ProcessorError(Exception):
        pass

    _stub.Processor = _Processor
    _stub.ProcessorError = _ProcessorError
    sys.modules["autopkglib"] = _stub

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "FleetImporter"))

import FleetImporter  # noqa: E402

# The fields always present in the summary, in the documented order.
BASE_REPORT_FIELDS = [
    "name",
    "version",
    "pkg_name",
    "pkg_sha256",
    "categories",
    "icon",
    "gitops_mode",
]
# Appended only in direct mode (populated from the Fleet API response).
DIRECT_ONLY_FIELDS = ["title_id", "installer_id"]
# Appended only in GitOps mode (populated from S3/Git artifacts).
GITOPS_ONLY_FIELDS = ["git_branch", "pull_request_url", "cloudfront_url"]
SUMMARY_TEXT = "The following new items were imported into Fleet:"


class TestBuildRunSummary(unittest.TestCase):
    """Tests for FleetImporter._build_run_summary."""

    def setUp(self):
        self.fi = FleetImporter.FleetImporter()
        self.fi.env = {
            "display_name": "Island",
            "version": "1.2.3",
            "pkg_path": "/path/to/Island-1.2.3.pkg",
            "hash_sha256": "abc123",
            "categories": ["Productivity", "Developer Tools"],
            "icon": "island.png",
            "fleet_title_id": 42,
            "fleet_installer_id": 100,
        }

    def _summary(self):
        return self.fi.env["fleet_importer_summary_result"]

    # --- Direct mode -----------------------------------------------------

    def test_summary_structure_direct_mode(self):
        """Direct mode produces base fields plus title/installer IDs."""
        self.fi._build_run_summary()
        summary = self._summary()
        self.assertEqual(summary["summary_text"], SUMMARY_TEXT)
        self.assertEqual(
            summary["report_fields"], BASE_REPORT_FIELDS + DIRECT_ONLY_FIELDS
        )
        self.assertEqual(
            summary["data"],
            {
                "name": "Island",
                "version": "1.2.3",
                "pkg_name": "/path/to/Island-1.2.3.pkg",
                "pkg_sha256": "abc123",
                "categories": "Productivity,Developer Tools",
                "icon": "island.png",
                "gitops_mode": False,
                "title_id": "42",
                "installer_id": "100",
            },
        )

    def test_report_fields_data_have_matching_keys(self):
        """Every value in report_fields has a corresponding entry in data."""
        self.fi._build_run_summary()
        data = self._summary()["data"]
        for field in self._summary()["report_fields"]:
            self.assertIn(field, data)

    def test_categories_joined_with_commas(self):
        self.fi.env["categories"] = ["A", "B"]
        self.fi._build_run_summary()
        self.assertEqual(self._summary()["data"]["categories"], "A,B")

    def test_categories_default_to_empty_string(self):
        self.fi.env["categories"] = []
        self.fi._build_run_summary()
        self.assertEqual(self._summary()["data"]["categories"], "")

    def test_ids_coerced_to_string(self):
        """title_id/installer_id must be strings for AutoPkg summaries."""
        self.fi._build_run_summary()
        data = self._summary()["data"]
        self.assertIsInstance(data["title_id"], str)
        self.assertIsInstance(data["installer_id"], str)

    def test_optional_fields_default_to_empty_string(self):
        self.fi.env["display_name"] = ""
        self.fi.env["icon"] = ""
        self.fi._build_run_summary()
        data = self._summary()["data"]
        self.assertEqual(data["name"], "")
        self.assertEqual(data["icon"], "")

    def test_gitops_mode_absent_equals_false(self):
        """Omitting gitops_mode behaves the same as setting it false."""
        self.fi.env["gitops_mode"] = False
        self.fi._build_run_summary()
        summary_with_false = self._summary()

        self.fi.env.pop("gitops_mode", None)
        self.fi._build_run_summary()
        self.assertEqual(self._summary(), summary_with_false)

    # --- State hygiene ----------------------------------------------------

    def test_clears_preexisting_summary(self):
        """Any pre-existing summary result is fully replaced, not stale."""
        self.fi.env["fleet_importer_summary_result"] = {"summary_text": "STALE"}
        self.fi._build_run_summary()
        self.assertEqual(self._summary()["summary_text"], SUMMARY_TEXT)

    # --- GitOps mode ------------------------------------------------------

    def test_gitops_mode_adds_fields(self):
        """GitOps mode appends git/PR/CDN fields to fields & data."""
        self.fi.env["gitops_mode"] = True
        self.fi.env["git_branch"] = "autopkg-island-1-2-3"
        self.fi.env["pull_request_url"] = "https://github.com/org/repo/pull/7"
        self.fi.env["cloudfront_url"] = "https://cdn.example.com/Island-1.2.3.pkg"
        self.fi._build_run_summary()
        summary = self._summary()
        self.assertEqual(
            summary["report_fields"], BASE_REPORT_FIELDS + GITOPS_ONLY_FIELDS
        )
        self.assertEqual(summary["data"]["git_branch"], "autopkg-island-1-2-3")
        self.assertEqual(
            summary["data"]["pull_request_url"], "https://github.com/org/repo/pull/7"
        )
        self.assertEqual(
            summary["data"]["cloudfront_url"], "https://cdn.example.com/Island-1.2.3.pkg"
        )
        self.assertEqual(summary["data"]["gitops_mode"], True)

    def test_gitops_mode_defaults_to_empty_strings(self):
        """Missing git_branch/pull_request_url/cloudfront_url become empty strings."""
        self.fi.env["gitops_mode"] = True
        self.fi._build_run_summary()
        self.assertEqual(self._summary()["data"]["git_branch"], "")
        self.assertEqual(self._summary()["data"]["pull_request_url"], "")
        self.assertEqual(self._summary()["data"]["cloudfront_url"], "")

    def test_gitops_mode_excludes_direct_fields(self):
        """GitOps summaries don't include the API-only title/installer fields."""
        self.fi.env["gitops_mode"] = True
        self.fi._build_run_summary()
        summary = self._summary()
        for field in DIRECT_ONLY_FIELDS:
            self.assertNotIn(field, summary["report_fields"])
            self.assertNotIn(field, summary["data"])

    def test_direct_mode_excludes_gitops_fields(self):
        """Direct summaries never expose git/PR/CDN fields."""
        self.fi.env["git_branch"] = "some-branch"
        self.fi.env["pull_request_url"] = "https://example.com/pr/1"
        self.fi.env["cloudfront_url"] = "https://cdn.example.com/x.pkg"
        self.fi._build_run_summary()
        summary = self._summary()
        for field in GITOPS_ONLY_FIELDS:
            self.assertNotIn(field, summary["report_fields"])
            self.assertNotIn(field, summary["data"])


if __name__ == "__main__":
    unittest.main()
