#!/usr/bin/env python3
"""
Unit tests for the auto-update policy automation functionality in FleetImporter.

Tests cover:
1. Policy name formatting with various inputs
2. osquery version detection query building
3. SQL injection prevention through quote escaping
4. Policy payload structure validation

Note: These tests extract and test the core logic from FleetImporter without
requiring AutoPkg dependencies. The functions are replicated here to enable
testing in environments where AutoPkg is not installed.
"""

import re
import sys
import unittest


# Replicate the core functions from FleetImporter for testing
def slugify(text):
    """
    Convert text to a slug suitable for URLs and identifiers.
    Replicated from FleetImporter._slugify()
    """
    text = str(text).lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    text = re.sub(r"^-+|-+$", "", text)
    return text


def format_policy_name(template, software_title):
    """
    Format policy name from template, replacing %NAME% with slugified software title.
    Replicated from FleetImporter._format_policy_name()
    """
    slug = slugify(software_title)
    return template.replace("%NAME%", slug)


def build_version_query(version, query_template=None, bundle_id=None):
    """
    Build osquery SQL query to detect outdated software versions.
    Replicated from FleetImporter._build_version_query()

    Supports two modes:
    1. Template mode: Use provided query_template with %VERSION% placeholder
    2. Default mode: Generate query using bundle_identifier and version_compare()
    """
    # Escape single quotes to prevent SQL injection
    safe_version = version.replace("'", "''")

    if query_template:
        # Template mode: Replace %VERSION% placeholder
        return query_template.replace("%VERSION%", safe_version)
    elif bundle_id:
        # Default mode: Generate bundle_identifier query
        safe_bundle_id = bundle_id.replace("'", "''")
        query = (
            f"SELECT 1 WHERE EXISTS (\n"
            f"  SELECT 1 FROM apps WHERE bundle_identifier = '{safe_bundle_id}' "
            f"AND version_compare(bundle_short_version, '{safe_version}') < 0\n"
            f");"
        )
        return query
    else:
        raise ValueError(
            "Either query_template or bundle_id must be provided to build version query"
        )


class TestAutoUpdatePolicyFormatting(unittest.TestCase):
    """Test policy name formatting functionality."""

    def test_format_policy_name_basic(self):
        """Test basic policy name formatting."""
        result = format_policy_name("autopkg-auto-update-%NAME%", "GitHub Desktop")
        self.assertEqual(result, "autopkg-auto-update-github-desktop")

    def test_format_policy_name_spaces(self):
        """Test policy name formatting with spaces."""
        result = format_policy_name("autopkg-auto-update-%NAME%", "Visual Studio Code")
        self.assertEqual(result, "autopkg-auto-update-visual-studio-code")

    def test_format_policy_name_special_chars(self):
        """Test policy name formatting with special characters."""
        result = format_policy_name("autopkg-auto-update-%NAME%", "1Password 8")
        self.assertEqual(result, "autopkg-auto-update-1password-8")

    def test_format_policy_name_multiple_placeholders(self):
        """Test policy name with multiple %NAME% placeholders."""
        result = format_policy_name("auto-update-%NAME%-policy-%NAME%", "Claude")
        self.assertEqual(result, "auto-update-claude-policy-claude")

    def test_format_policy_name_no_placeholder(self):
        """Test policy name without placeholder."""
        result = format_policy_name("static-policy-name", "GitHub Desktop")
        self.assertEqual(result, "static-policy-name")

    def test_format_policy_name_uppercase(self):
        """Test policy name formatting with uppercase template."""
        result = format_policy_name("AUTOPKG-AUTO-UPDATE-%NAME%", "Slack")
        # Only %NAME% is slugified (lowercase), template stays as-is
        self.assertEqual(result, "AUTOPKG-AUTO-UPDATE-slack")

    def test_format_policy_name_dots_and_dashes(self):
        """Test policy name with dots and dashes in software name."""
        result = format_policy_name("autopkg-auto-update-%NAME%", "GPG Suite")
        self.assertEqual(result, "autopkg-auto-update-gpg-suite")


class TestAutoUpdateQueryBuilder(unittest.TestCase):
    """Test osquery version detection query building."""

    def test_build_version_query_basic(self):
        """Test basic version query building."""
        query = build_version_query("3.3.12", bundle_id="com.github.GitHubClient")
        expected = (
            "SELECT 1 WHERE EXISTS (\n"
            "  SELECT 1 FROM apps WHERE bundle_identifier = 'com.github.GitHubClient' "
            "AND version_compare(bundle_short_version, '3.3.12') < 0\n"
            ");"
        )
        self.assertEqual(query, expected)

    def test_build_version_query_single_quotes(self):
        """Test query building with single quotes in bundle ID (SQL injection prevention)."""
        query = build_version_query("1.0.0", bundle_id="com.oreilly'.malicious")
        expected = (
            "SELECT 1 WHERE EXISTS (\n"
            "  SELECT 1 FROM apps WHERE bundle_identifier = 'com.oreilly''.malicious' "
            "AND version_compare(bundle_short_version, '1.0.0') < 0\n"
            ");"
        )
        self.assertEqual(query, expected)

    def test_build_version_query_multiple_quotes(self):
        """Test query building with multiple single quotes."""
        query = build_version_query("2.0.0", bundle_id="com.test'app'id")
        expected = (
            "SELECT 1 WHERE EXISTS (\n"
            "  SELECT 1 FROM apps WHERE bundle_identifier = 'com.test''app''id' "
            "AND version_compare(bundle_short_version, '2.0.0') < 0\n"
            ");"
        )
        self.assertEqual(query, expected)

    def test_build_version_query_version_with_build(self):
        """Test query with version containing build numbers."""
        query = build_version_query("1.85.2.123", bundle_id="com.microsoft.VSCode")
        expected = (
            "SELECT 1 WHERE EXISTS (\n"
            "  SELECT 1 FROM apps WHERE bundle_identifier = 'com.microsoft.VSCode' "
            "AND version_compare(bundle_short_version, '1.85.2.123') < 0\n"
            ");"
        )
        self.assertEqual(query, expected)

    def test_build_version_query_special_chars_in_version(self):
        """Test query with special characters in version."""
        query = build_version_query("1.0.0-beta+123", bundle_id="com.test.app")
        expected = (
            "SELECT 1 WHERE EXISTS (\n"
            "  SELECT 1 FROM apps WHERE bundle_identifier = 'com.test.app' "
            "AND version_compare(bundle_short_version, '1.0.0-beta+123') < 0\n"
            ");"
        )
        self.assertEqual(query, expected)

    def test_build_version_query_empty_values(self):
        """Test query building with empty values."""
        # Empty bundle_id should raise an error
        with self.assertRaises(ValueError):
            build_version_query("", bundle_id="")

    def test_build_version_query_unicode(self):
        """Test query building with unicode characters."""
        query = build_version_query("1.0.0", bundle_id="com.café.app™")
        expected = (
            "SELECT 1 WHERE EXISTS (\n"
            "  SELECT 1 FROM apps WHERE bundle_identifier = 'com.café.app™' "
            "AND version_compare(bundle_short_version, '1.0.0') < 0\n"
            ");"
        )
        self.assertEqual(query, expected)


class TestAutoUpdatePolicyPayload(unittest.TestCase):
    """Test policy payload structure for Fleet API."""

    def test_policy_payload_structure(self):
        """Test that policy payload has all required fields."""
        # Simulate what would be created in _create_or_update_policy_direct
        policy_name = format_policy_name("autopkg-auto-update-%NAME%", "GitHub Desktop")
        query = build_version_query("3.3.12", bundle_id="com.github.GitHubClient")

        # Expected payload structure
        payload = {
            "name": policy_name,
            "query": query,
            "description": "Auto-update policy for GitHub Desktop (version 3.3.12). Created by AutoPkg FleetImporter.",
            "resolution": "Install GitHub Desktop 3.3.12 via Fleet self-service.",
            "platform": "darwin",
            "critical": False,
        }

        # Verify all required fields are present
        self.assertIn("name", payload)
        self.assertIn("query", payload)
        self.assertIn("description", payload)
        self.assertIn("resolution", payload)
        self.assertIn("platform", payload)
        self.assertIn("critical", payload)

        # Verify field types
        self.assertIsInstance(payload["name"], str)
        self.assertIsInstance(payload["query"], str)
        self.assertIsInstance(payload["description"], str)
        self.assertIsInstance(payload["resolution"], str)
        self.assertEqual(payload["platform"], "darwin")
        self.assertIsInstance(payload["critical"], bool)
        self.assertFalse(payload["critical"])

        # Verify content
        self.assertEqual(payload["name"], "autopkg-auto-update-github-desktop")
        self.assertIn("com.github.GitHubClient", payload["query"])
        self.assertIn("3.3.12", payload["query"])
        self.assertIn("version_compare", payload["query"])


class TestAutoUpdateSQLInjectionPrevention(unittest.TestCase):
    """Test SQL injection prevention in query building."""

    def test_prevent_sql_injection_or_clause(self):
        """Test that SQL OR injection attempts are properly escaped."""
        malicious_bundle_id = "com.app' OR '1'='1"
        query = build_version_query("1.0.0", bundle_id=malicious_bundle_id)

        # Should escape the single quote, making it safe
        self.assertIn("com.app'' OR ''1''=''1", query)
        # Should NOT contain unescaped OR that would execute
        self.assertNotIn("' OR '1'='1", query)

    def test_prevent_sql_injection_comment(self):
        """Test that SQL comment injection attempts are properly escaped."""
        malicious_bundle_id = "com.app' -- comment"
        query = build_version_query("1.0.0", bundle_id=malicious_bundle_id)

        # Should escape the single quote
        self.assertIn("com.app'' -- comment", query)
        # Query should remain valid
        self.assertTrue(query.startswith("SELECT 1 WHERE EXISTS"))

    def test_prevent_sql_injection_union(self):
        """Test that SQL UNION injection attempts are properly escaped."""
        malicious_bundle_id = "com.app' UNION SELECT * FROM users --"
        query = build_version_query("1.0.0", bundle_id=malicious_bundle_id)

        # Should escape the single quote, neutralizing the injection
        self.assertIn("com.app'' UNION SELECT * FROM users --", query)

    def test_prevent_sql_injection_drop_table(self):
        """Test that DROP TABLE injection attempts are properly escaped."""
        malicious_version = "1.0.0'; DROP TABLE apps; --"
        query = build_version_query(malicious_version, bundle_id="com.test.app")

        # Should escape the single quote
        self.assertIn("1.0.0''; DROP TABLE apps; --", query)

    def test_multiple_injection_attempts(self):
        """Test multiple injection attempts in same query."""
        malicious_bundle_id = "com.app' OR '1'='1' --"
        malicious_version = "1.0'; DROP TABLE apps; --"
        query = build_version_query(malicious_version, bundle_id=malicious_bundle_id)

        # All single quotes should be escaped
        count_single_quotes = query.count("''")
        # Should have escaped quotes for both bundle_id and version
        self.assertGreater(count_single_quotes, 0)


class TestAutoUpdateEdgeCases(unittest.TestCase):
    """Test edge cases and error handling."""

    def test_format_policy_name_empty_template(self):
        """Test policy name formatting with empty template."""
        result = format_policy_name("", "GitHub Desktop")
        self.assertEqual(result, "")

    def test_format_policy_name_empty_software_name(self):
        """Test policy name formatting with empty software name."""
        result = format_policy_name("autopkg-auto-update-%NAME%", "")
        self.assertEqual(result, "autopkg-auto-update-")

    def test_build_query_long_bundle_id(self):
        """Test query building with very long bundle ID."""
        long_bundle_id = "com." + "a" * 500
        query = build_version_query("1.0.0", bundle_id=long_bundle_id)
        self.assertIn(long_bundle_id, query)
        self.assertTrue(query.startswith("SELECT 1 WHERE EXISTS"))

    def test_build_query_long_version(self):
        """Test query building with very long version string."""
        long_version = "1." + "0" * 500
        query = build_version_query(long_version, bundle_id="com.test.app")
        self.assertIn(long_version, query)

    def test_format_policy_name_only_special_chars(self):
        """Test policy name formatting with only special characters."""
        result = format_policy_name("autopkg-auto-update-%NAME%", "!@#$%^&*()")
        # Slugify should handle this gracefully
        self.assertIsInstance(result, str)
        # Should have at least the prefix
        self.assertIn("autopkg-auto-update", result)


class TestAutoUpdateTemplateMode(unittest.TestCase):
    """Test template-based query building with %VERSION% placeholder."""

    def test_template_basic_replacement(self):
        """Test basic %VERSION% placeholder replacement."""
        template = "SELECT 1 WHERE program_name = 'MyApp' AND version >= '%VERSION%'"
        query = build_version_query("3.2.1", query_template=template)

        # Should replace %VERSION% with actual version
        self.assertIn("version >= '3.2.1'", query)
        # Should NOT contain the placeholder
        self.assertNotIn("%VERSION%", query)

    def test_template_multiple_placeholders(self):
        """Test template with multiple %VERSION% placeholders."""
        template = (
            "SELECT 1 WHERE version >= '%VERSION%' OR build_version = '%VERSION%'"
        )
        query = build_version_query("1.5.0", query_template=template)

        # Both placeholders should be replaced
        self.assertIn("version >= '1.5.0'", query)
        self.assertIn("build_version = '1.5.0'", query)
        self.assertNotIn("%VERSION%", query)

    def test_template_sql_injection_in_version(self):
        """Test that SQL injection in version is escaped even with templates."""
        template = "SELECT 1 WHERE version = '%VERSION%'"
        malicious_version = "1.0'; DROP TABLE programs; --"
        query = build_version_query(malicious_version, query_template=template)

        # Should escape single quotes in version
        self.assertIn("1.0''; DROP TABLE programs; --", query)
        # Should NOT contain unescaped injection
        self.assertNotIn("1.0'; DROP", query)

    def test_template_complex_query(self):
        """Test template with complex multi-table query."""
        template = """SELECT 1 WHERE EXISTS (
            SELECT 1 FROM programs p
            LEFT JOIN rpm_packages r ON p.name = r.name
            WHERE p.name = 'MyProgram'
            AND version_compare(r.version, '%VERSION%') >= 0
        )"""
        query = build_version_query("2.4.6", query_template=template)

        # Should replace placeholder
        self.assertIn("version_compare(r.version, '2.4.6')", query)
        self.assertNotIn("%VERSION%", query)

    def test_template_windows_registry_query(self):
        """Test template for Windows registry-based detection."""
        template = """SELECT 1 WHERE EXISTS (
            SELECT 1 FROM registry
            WHERE path = 'HKEY_LOCAL_MACHINE\\Software\\MyApp'
            AND name = 'Version'
            AND data >= '%VERSION%'
        )"""
        query = build_version_query("5.1.2", query_template=template)

        # Should work with Windows-style queries
        self.assertIn("data >= '5.1.2'", query)
        self.assertNotIn("%VERSION%", query)

    def test_template_takes_precedence_over_bundle_id(self):
        """Test that template is used even when bundle_id is provided."""
        template = "SELECT 1 WHERE custom_field = '%VERSION%'"
        # Even though we pass bundle_id, template should be used
        query = build_version_query(
            "1.0.0", query_template=template, bundle_id="com.ignored.app"
        )

        # Should use template, not bundle_id
        self.assertIn("custom_field = '1.0.0'", query)
        self.assertNotIn("com.ignored.app", query)
        self.assertNotIn("bundle_identifier", query)

    def test_template_empty_string(self):
        """Test that empty template string falls back to bundle_id mode."""
        # Empty template should be treated as None
        query = build_version_query(
            "1.0.0", query_template="", bundle_id="com.test.app"
        )

        # Should fall back to bundle_id mode
        self.assertIn("com.test.app", query)
        self.assertIn("bundle_identifier", query)

    def test_fallback_when_no_template_or_bundle_id(self):
        """Test behavior when neither template nor bundle_id provided."""
        # Should raise ValueError when neither template nor bundle_id is provided
        with self.assertRaises(ValueError) as context:
            build_version_query("1.0.0")

        # Verify error message
        self.assertIn(
            "query_template or bundle_id must be provided", str(context.exception)
        )


def run_tests():
    """Run all tests and print results."""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestAutoUpdatePolicyFormatting))
    suite.addTests(loader.loadTestsFromTestCase(TestAutoUpdateQueryBuilder))
    suite.addTests(loader.loadTestsFromTestCase(TestAutoUpdatePolicyPayload))
    suite.addTests(loader.loadTestsFromTestCase(TestAutoUpdateSQLInjectionPrevention))
    suite.addTests(loader.loadTestsFromTestCase(TestAutoUpdateEdgeCases))
    suite.addTests(loader.loadTestsFromTestCase(TestAutoUpdateTemplateMode))

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Return exit code
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
