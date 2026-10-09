#!/usr/bin/env python3
"""
Regression tests for direct-mode variable insertion in FleetImporter.main.

Covers the fallback introduced in 28221b8 plus the uncommitted
`%PLACEHOLDER%` handling:

  fleet_api_token <- FLEET_API_TOKEN
  fleet_api_base  <- FLEET_API_BASE
  team_id         <- FLEET_TEAM_ID (str when set, e.g. "42")

Unset means: key absent, None, empty/whitespace-only, or an unsubstituted
AutoPkg reference like "%FLEET_API_TOKEN%". Explicit values (including an
int team_id) must be honored and must never crash re.match.

Like test_script_resolution.py, the real FleetImporter is imported with
AutoPkg stubbed, and the workflows are stubbed so no network is touched.
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


class TestDirectModeVariableInsertion(unittest.TestCase):
    """main() must resolve lowercase inputs from UPPER prefs when unset."""

    def setUp(self):
        self.fi = FleetImporter.FleetImporter()
        self.fi.env = {}
        self.called = {}
        self.fi._run_direct_upload_workflow = lambda: self.called.update(direct=True)
        self.fi._run_gitops_workflow = lambda: self.called.update(gitops=True)

    def _run_main(self, env):
        self.fi.env = dict(env)
        self.called = {}
        self.fi.main()
        return self.fi.env

    def test_missing_lowercase_falls_back_to_upper(self):
        env = self._run_main(
            {
                "FLEET_API_TOKEN": "tok-abc",
                "FLEET_API_BASE": "https://fleet.example.com",
                "FLEET_TEAM_ID": "42",
            }
        )
        self.assertEqual(env["fleet_api_token"], "tok-abc")
        self.assertEqual(env["fleet_api_base"], "https://fleet.example.com")
        self.assertEqual(env["team_id"], "42")
        self.assertTrue(self.called.get("direct"))
        self.assertIsInstance(env["team_id"], str)

    def test_unsubstituted_placeholder_falls_back_to_upper(self):
        env = self._run_main(
            {
                "fleet_api_token": "%FLEET_API_TOKEN%",
                "fleet_api_base": "%FLEET_API_BASE%",
                "team_id": "%FLEET_TEAM_ID%",
                "FLEET_API_TOKEN": "tok-abc",
                "FLEET_API_BASE": "https://fleet.example.com",
                "FLEET_TEAM_ID": "42",
            }
        )
        self.assertEqual(env["fleet_api_token"], "tok-abc")
        self.assertEqual(env["fleet_api_base"], "https://fleet.example.com")
        self.assertEqual(env["team_id"], "42")

    def test_empty_and_whitespace_fall_back_to_upper(self):
        for blank in ("", "   "):
            env = self._run_main(
                {
                    "fleet_api_token": blank,
                    "fleet_api_base": blank,
                    "team_id": blank,
                    "FLEET_API_TOKEN": "tok-abc",
                    "FLEET_API_BASE": "https://fleet.example.com",
                    "FLEET_TEAM_ID": "42",
                }
            )
            self.assertEqual(env["fleet_api_token"], "tok-abc")
            self.assertEqual(env["fleet_api_base"], "https://fleet.example.com")
            self.assertEqual(env["team_id"], "42")

    def test_explicit_values_are_honored(self):
        env = self._run_main(
            {
                "fleet_api_token": "explicit-tok",
                "fleet_api_base": "https://explicit.example.com",
                "team_id": "7",
                "FLEET_API_TOKEN": "tok-abc",
                "FLEET_API_BASE": "https://fleet.example.com",
                "FLEET_TEAM_ID": "42",
            }
        )
        self.assertEqual(env["fleet_api_token"], "explicit-tok")
        self.assertEqual(env["fleet_api_base"], "https://explicit.example.com")
        self.assertEqual(env["team_id"], "7")

    def test_int_team_id_does_not_crash_and_is_honored(self):
        # team_id should be a str when set, but an int must not crash
        # re.match nor be clobbered.
        env = self._run_main(
            {
                "fleet_api_token": "explicit-tok",
                "fleet_api_base": "https://explicit.example.com",
                "team_id": 7,
                "FLEET_TEAM_ID": "42",
            }
        )
        self.assertEqual(env["team_id"], 7)

    def test_missing_upper_leaves_none_without_crash(self):
        env = self._run_main({})
        self.assertIsNone(env["fleet_api_token"])
        self.assertIsNone(env["fleet_api_base"])
        self.assertIsNone(env["team_id"])
        self.assertTrue(self.called.get("direct"))

    def test_placeholder_with_missing_upper_results_in_none(self):
        env = self._run_main(
            {
                "fleet_api_token": "%FLEET_API_TOKEN%",
                "fleet_api_base": "%FLEET_API_BASE%",
                "team_id": "%FLEET_TEAM_ID%",
            }
        )
        self.assertIsNone(env["fleet_api_token"])
        self.assertIsNone(env["fleet_api_base"])
        self.assertIsNone(env["team_id"])

    def test_real_value_containing_percent_is_kept(self):
        env = self._run_main(
            {
                "fleet_api_token": "tok%backup",
                "fleet_api_base": "https://fleet.example.com",
                "team_id": "7",
                "FLEET_API_TOKEN": "tok-abc",
                "FLEET_TEAM_ID": "42",
            }
        )
        self.assertEqual(env["fleet_api_token"], "tok%backup")

    def test_gitops_mode_skips_insertion(self):
        env = self._run_main(
            {
                "gitops_mode": True,
                "FLEET_API_TOKEN": "tok-abc",
                "FLEET_API_BASE": "https://fleet.example.com",
                "FLEET_TEAM_ID": "42",
            }
        )
        self.assertTrue(self.called.get("gitops"))
        self.assertFalse(self.called.get("direct"))
        self.assertNotIn("fleet_api_token", env)
        self.assertNotIn("fleet_api_base", env)
        self.assertNotIn("team_id", env)


if __name__ == "__main__":
    unittest.main(verbosity=2)
