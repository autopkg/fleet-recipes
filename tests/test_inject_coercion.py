#!/usr/bin/env python3
"""
Unit tests for FleetImporter.inject() numeric coercion.

Background:
    AutoPkg's do_variable_substitution uses re.sub against env values. If a
    referenced %KEY% resolves to an int (e.g. FLEET_TEAM_ID stored via
    `defaults write … -int 1`), substitution fails with
    "TypeError: sequence item 0: expected str instance, int found" before the
    processor's main() runs.

    FleetImporter.inject() works around this by coercing numeric env entries
    that are referenced via %KEY% in the step's Arguments. Booleans are left
    alone (bool is an int subclass in Python and stringifying it would change
    semantics for keys like gitops_mode).

These tests replicate the coercion logic from FleetImporter without importing
AutoPkg, matching the pattern used in test_auto_update.py.
"""

import re
import unittest

ENV_REF_RE = re.compile(r"%([^%]+)%")


def collect_referenced_keys(value):
    keys = set()
    if isinstance(value, str):
        keys.update(ENV_REF_RE.findall(value))
    elif isinstance(value, dict):
        for v in value.values():
            keys.update(collect_referenced_keys(v))
    elif isinstance(value, (list, tuple)):
        for v in value:
            keys.update(collect_referenced_keys(v))
    return keys


def coerce_referenced_numerics(env, arguments):
    for key in collect_referenced_keys(arguments):
        value = env.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            env[key] = str(value)
    return env


class TestCollectReferencedKeys(unittest.TestCase):
    def test_extracts_keys_from_string(self):
        self.assertEqual(collect_referenced_keys("%FOO%/%BAR%"), {"FOO", "BAR"})

    def test_walks_into_dicts_and_lists(self):
        args = {
            "a": "%ONE%",
            "b": ["%TWO%", {"c": "%THREE%"}],
            "d": "literal",
        }
        self.assertEqual(collect_referenced_keys(args), {"ONE", "TWO", "THREE"})

    def test_no_keys_returns_empty(self):
        self.assertEqual(collect_referenced_keys("no refs here"), set())


class TestCoerceReferencedNumerics(unittest.TestCase):
    def test_coerces_int_team_id(self):
        env = {"FLEET_TEAM_ID": 1}
        coerce_referenced_numerics(env, {"team_id": "%FLEET_TEAM_ID%"})
        self.assertEqual(env["FLEET_TEAM_ID"], "1")

    def test_coerces_float(self):
        env = {"PORT": 8080.0}
        coerce_referenced_numerics(env, {"port": "%PORT%"})
        self.assertEqual(env["PORT"], "8080.0")

    def test_leaves_strings_alone(self):
        env = {"FLEET_TEAM_ID": "1"}
        coerce_referenced_numerics(env, {"team_id": "%FLEET_TEAM_ID%"})
        self.assertEqual(env["FLEET_TEAM_ID"], "1")

    def test_does_not_coerce_booleans(self):
        # bool is a subclass of int; coercing would change semantics for
        # keys like gitops_mode where downstream code does `if env[key]`.
        env = {"gitops_mode": False}
        coerce_referenced_numerics(env, {"flag": "%gitops_mode%"})
        self.assertIs(env["gitops_mode"], False)

    def test_skips_unreferenced_keys(self):
        env = {"FLEET_TEAM_ID": 1, "OTHER_INT": 99}
        coerce_referenced_numerics(env, {"team_id": "%FLEET_TEAM_ID%"})
        self.assertEqual(env["FLEET_TEAM_ID"], "1")
        self.assertEqual(env["OTHER_INT"], 99)

    def test_handles_nested_arguments(self):
        env = {"A": 1, "B": 2}
        args = {"x": ["%A%"], "y": {"z": "%B%"}}
        coerce_referenced_numerics(env, args)
        self.assertEqual(env["A"], "1")
        self.assertEqual(env["B"], "2")

    def test_missing_env_key_is_ignored(self):
        env = {}
        # Should not raise — substitution will fail later with a clearer error.
        coerce_referenced_numerics(env, {"team_id": "%FLEET_TEAM_ID%"})
        self.assertEqual(env, {})


if __name__ == "__main__":
    unittest.main()
