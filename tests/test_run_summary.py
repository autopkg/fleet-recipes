#!/usr/bin/env python3
"""
Unit tests for FleetImporter._build_run_summary() and the main() gating that
decides when it runs.

fleet_importer_summary_result is picked up by AutoPkg's summary_results and
included in the --report-plist output, so regressions here are visible to
every recipe consumer (e.g. a post-run webhook). Beyond the structure of the
summary itself, these tests cover:

  - env states _build_run_summary() must survive without raising, notably
    hash_sha256 being absent (the state left behind by every "nothing was
    imported" early return in the direct and GitOps workflows).
  - the main() paths where a summary must NOT be built at all: the
    direct-mode "package already exists" / "could not resolve existing
    title" / "failed to replace installer" early returns, and the GitOps
    "branch already exists" early return.
  - one real run through main() per mode confirming the summary IS built,
    and with the right data, when an import genuinely happens.

Unlike the other test modules, these import the real FleetImporter so the
actual implementation is exercised; AutoPkg is stubbed so it can run without
AutoPkg installed.
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
    "gitops_mode",
]
# Appended only in direct mode (API response IDs + the Fleet instance URL).
DIRECT_ONLY_FIELDS = ["title_id", "installer_id", "fleet_instance"]
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
            "fleet_title_id": 42,
            "fleet_installer_id": 100,
            "fleet_api_base": "https://fleet.example.com",
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
                "pkg_name": "Island-1.2.3.pkg",
                "pkg_sha256": "abc123",
                "categories": "Productivity,Developer Tools",
                "gitops_mode": "False",
                "title_id": "42",
                "installer_id": "100",
                "fleet_instance": "https://fleet.example.com",
            },
        )

    def test_pkg_name_uses_basename_not_full_path(self):
        """pkg_name must not leak the local cache path into the report."""
        self.fi.env["pkg_path"] = (
            "/Users/example/Library/AutoPkg/Cache/foo/Island-1.2.3.pkg"
        )
        self.fi._build_run_summary()
        self.assertEqual(self._summary()["data"]["pkg_name"], "Island-1.2.3.pkg")

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
        self.fi._build_run_summary()
        data = self._summary()["data"]
        self.assertEqual(data["name"], "")

    def test_missing_hash_sha256_does_not_raise(self):
        """hash_sha256 absent must not KeyError.

        This is the env state left behind by every direct-mode early return
        where nothing was actually imported (package already exists, could
        not resolve the existing title, failed to replace the installer):
        none of them set hash_sha256. _build_run_summary() itself must
        tolerate that even though, with the main() gating in place, it is
        no longer called on those paths.
        """
        self.fi.env.pop("hash_sha256")
        self.fi._build_run_summary()
        self.assertEqual(self._summary()["data"]["pkg_sha256"], "")

    def test_gitops_mode_absent_equals_false(self):
        """Omitting gitops_mode behaves the same as setting it false."""
        self.fi.env["gitops_mode"] = False
        self.fi._build_run_summary()
        summary_with_false = self._summary()

        self.fi.env.pop("gitops_mode", None)
        self.fi._build_run_summary()
        self.assertEqual(self._summary(), summary_with_false)

    def test_fleet_instance_defaults_to_empty_string(self):
        """Missing fleet_api_base reports an empty fleet_instance."""
        self.fi.env.pop("fleet_api_base")
        self.fi._build_run_summary()
        self.assertEqual(self._summary()["data"]["fleet_instance"], "")

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
            summary["data"]["cloudfront_url"],
            "https://cdn.example.com/Island-1.2.3.pkg",
        )
        self.assertEqual(summary["data"]["gitops_mode"], "True")

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


class TestMainSummaryGating(unittest.TestCase):
    """Integration tests through FleetImporter.main().

    Unlike test_variable_insertion.py, _build_run_summary is NOT stubbed
    here: these tests exercise the real main() -> _build_run_summary
    integration, for both the "nothing imported" early-return states and a
    genuine import in each mode. The workflow methods themselves are
    stubbed (as in test_variable_insertion.py) purely to avoid touching the
    network/filesystem/Fleet API; each stub reproduces exactly the env
    mutations the real workflow leaves behind on that path.
    """

    def setUp(self):
        self.fi = FleetImporter.FleetImporter()
        self.fi.env = {
            "display_name": "Island",
            "version": "1.2.3",
            "pkg_path": "/path/to/Island-1.2.3.pkg",
            "categories": ["Productivity"],
            "fleet_api_base": "https://fleet.example.com",
        }

    def _summary(self):
        return self.fi.env.get("fleet_importer_summary_result")

    # --- Direct mode: nothing imported, no summary -------------------------

    def test_existing_package_in_fleet_skips_summary(self):
        """'Package already exists in Fleet' return never sets hash_sha256."""

        def fake_direct():
            self.fi.env["fleet_title_id"] = 42
            self.fi.env["fleet_installer_id"] = None

        self.fi.env["gitops_mode"] = False
        self.fi._run_direct_upload_workflow = fake_direct
        self.fi.main()
        self.assertIsNone(self._summary())

    def test_could_not_resolve_existing_title_skips_summary(self):
        """'Could not resolve the existing software title' return."""

        def fake_direct():
            self.fi.env["fleet_title_id"] = None
            self.fi.env["fleet_installer_id"] = None

        self.fi.env["gitops_mode"] = False
        self.fi._run_direct_upload_workflow = fake_direct
        self.fi.main()
        self.assertIsNone(self._summary())

    def test_installer_replace_failure_skips_summary(self):
        """'Failed to replace the existing installer' return."""

        def fake_direct():
            self.fi.env["fleet_title_id"] = 42
            self.fi.env["fleet_installer_id"] = None

        self.fi.env["gitops_mode"] = False
        self.fi._run_direct_upload_workflow = fake_direct
        self.fi.main()
        self.assertIsNone(self._summary())

    # --- Direct mode: genuine import builds the summary ---------------------

    def test_successful_direct_upload_builds_summary(self):
        def fake_direct():
            self.fi.env["fleet_title_id"] = 42
            self.fi.env["fleet_installer_id"] = 100
            self.fi.env["hash_sha256"] = "abc123"
            self.fi._import_occurred = True

        self.fi.env["gitops_mode"] = False
        self.fi._run_direct_upload_workflow = fake_direct
        self.fi.main()
        summary = self._summary()
        self.assertIsNotNone(summary)
        self.assertEqual(summary["data"]["pkg_sha256"], "abc123")
        self.assertEqual(summary["data"]["title_id"], "42")
        self.assertEqual(summary["data"]["installer_id"], "100")

    # --- GitOps mode: nothing imported, no summary --------------------------

    def test_gitops_idempotent_branch_skips_summary(self):
        """Branch/PR already exists for this version: hash_sha256 never set."""

        def fake_gitops():
            self.fi.env["git_branch"] = "autopkg/island-1-2-3"
            self.fi.env["pull_request_url"] = "https://github.com/org/repo/pull/7"

        self.fi.env["gitops_mode"] = True
        self.fi._run_gitops_workflow = fake_gitops
        self.fi.main()
        self.assertIsNone(self._summary())

    # --- GitOps mode: genuine import builds the summary ----------------------

    def test_successful_gitops_pr_builds_summary(self):
        def fake_gitops():
            self.fi.env["git_branch"] = "autopkg/island-1-2-3"
            self.fi.env["pull_request_url"] = "https://github.com/org/repo/pull/8"
            self.fi.env["cloudfront_url"] = "https://cdn.example.com/Island-1.2.3.pkg"
            self.fi.env["hash_sha256"] = "def456"
            self.fi._import_occurred = True

        self.fi.env["gitops_mode"] = True
        self.fi._run_gitops_workflow = fake_gitops
        self.fi.main()
        summary = self._summary()
        self.assertIsNotNone(summary)
        self.assertEqual(summary["data"]["pkg_sha256"], "def456")
        self.assertEqual(
            summary["data"]["pull_request_url"], "https://github.com/org/repo/pull/8"
        )
        self.assertEqual(
            summary["data"]["cloudfront_url"],
            "https://cdn.example.com/Island-1.2.3.pkg",
        )


if __name__ == "__main__":
    unittest.main()
