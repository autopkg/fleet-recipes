#!/usr/bin/env python3
"""
Regression tests for script/query resolution in FleetImporter.

These guard two related bugs that broke custom install/post-install/uninstall
scripts (and pre-install queries) in GitOps mode:

1. The path-vs-inline heuristic used to treat any input containing "/" as a
   file path. Real shell scripts are full of slashes ("/usr/sbin/chown", the
   "#!/bin/sh" shebang), so inline scripts were misread as paths, the "file"
   wasn't found, and the script was silently dropped.

2. GitOps mode wrote the resolved script *contents* into a YAML "path:" field.
   Fleet's GitOps spec expects install_script.path / post_install_script.path /
   etc. to point to a file in the repo whose contents it reads. Dumping the body
   into "path:" made `fleetctl gitops` try to open the script body as a filename
   (e.g. "platforms/macos/software/#!/bin/sh ... exit 0: no such file or directory").

Unlike the other test modules, these import the real FleetImporter so the actual
implementation is exercised; AutoPkg is stubbed so it can run without AutoPkg
installed.
"""

import os
import re
import sys
import tempfile
import types
import unittest
from pathlib import Path

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

import yaml  # noqa: E402

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

# The exact post-install script from the bug report: multi-line, full of slashes.
ISLAND_POST_INSTALL = (
    "#!/bin/sh\n\n"
    '/usr/sbin/chown -R "$(stat -f%Su /dev/console)" "/Applications/Island.app"\n\n'
    "exit 0\n"
)


class TestResolveScriptContent(unittest.TestCase):
    """Tests for FleetImporter._resolve_script_content path-vs-inline logic."""

    def setUp(self):
        self.fi = FleetImporter.FleetImporter()
        self.fi.env = {}

    def test_multiline_script_with_slashes_is_inline(self):
        # The original failing case must be treated as an inline body, verbatim.
        self.assertEqual(
            self.fi._resolve_script_content(ISLAND_POST_INSTALL),
            ISLAND_POST_INSTALL,
        )

    def test_single_line_command_with_slashes_is_inline(self):
        cmd = "installer -pkg /tmp/x.pkg -target /"
        self.assertEqual(self.fi._resolve_script_content(cmd), cmd)

    def test_single_line_sql_query_is_inline(self):
        query = "SELECT 1 FROM apps WHERE bundle_identifier = 'com.example'"
        self.assertEqual(self.fi._resolve_script_content(query), query)

    def test_empty_input_returns_empty(self):
        self.assertEqual(self.fi._resolve_script_content(""), "")

    def test_existing_file_path_is_read(self):
        with tempfile.TemporaryDirectory() as d:
            script = Path(d) / "postinstall.sh"
            script.write_text("#!/bin/sh\necho hi\n")
            self.assertEqual(
                self.fi._resolve_script_content(str(script)),
                "#!/bin/sh\necho hi\n",
            )

    def test_missing_script_path_returns_empty(self):
        # Single-line, script-like extension, no such file -> empty (not the
        # literal string), preserving the prior "file not found" behavior.
        self.assertEqual(
            self.fi._resolve_script_content("scripts/does-not-exist.sh"), ""
        )


class TestCreateSoftwarePackageYaml(unittest.TestCase):
    """Tests that GitOps mode writes script files and references them by path."""

    # Fleet's current repo layout (matches the processor defaults).
    SOFTWARE_DIR = "platforms/macos/software"
    SCRIPTS_DIR = "platforms/macos/scripts"

    def setUp(self):
        self.fi = FleetImporter.FleetImporter()
        self.fi.env = {}
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _create(self, software_title, **scripts):
        """Helper: invoke _create_software_package_yaml with sensible defaults."""
        return self.fi._create_software_package_yaml(
            str(self.repo),
            scripts.get("software_dir", self.SOFTWARE_DIR),
            scripts.get("scripts_dir", self.SCRIPTS_DIR),
            software_title,
            "https://cdn.example.com/pkg.pkg",
            "a" * 64,
            scripts.get("install_script", ""),
            scripts.get("uninstall_script", ""),
            scripts.get("pre_install_query", ""),
            scripts.get("post_install_script", ""),
            scripts.get("icon_path", None),
            scripts.get("display_name", ""),
        )

    def _entry(self, software_dir, slug):
        pkg_yaml = self.repo / software_dir / f"{slug}.yml"
        return pkg_yaml, yaml.safe_load(pkg_yaml.read_text())[0]

    def test_post_install_script_written_as_file_and_referenced_by_path(self):
        _, script_paths = self._create(
            "Island.app", post_install_script=ISLAND_POST_INSTALL
        )

        pkg_yaml, entry = self._entry(self.SOFTWARE_DIR, "island-app")

        # The YAML must reference a *path*, and that path must not be the body.
        self.assertIn("post_install_script", entry)
        ref_path = entry["post_install_script"]["path"]
        self.assertFalse(ref_path.startswith("#!"))
        self.assertTrue(ref_path.endswith(".sh"))

        # The path resolves (relative to the package YAML) to a real file whose
        # contents are the script body.
        resolved = (pkg_yaml.parent / ref_path).resolve()
        self.assertTrue(resolved.is_file())
        self.assertEqual(resolved.read_text(), ISLAND_POST_INSTALL)

        # The returned repo-relative path is reported for git staging.
        self.assertEqual(
            script_paths, ["platforms/macos/scripts/island-app-postinstall.sh"]
        )

    def test_pre_install_query_written_as_file(self):
        query = "SELECT 1 FROM apps WHERE bundle_identifier = 'com.example'"
        _, script_paths = self._create("Example.app", pre_install_query=query)

        pkg_yaml, entry = self._entry(self.SOFTWARE_DIR, "example-app")
        ref_path = entry["pre_install_query"]["path"]
        resolved = (pkg_yaml.parent / ref_path).resolve()
        self.assertTrue(resolved.is_file())
        self.assertEqual(resolved.read_text(), query + "\n")
        self.assertEqual(
            script_paths,
            ["platforms/macos/scripts/example-app-preinstall-query.sql"],
        )

    def test_no_scripts_means_no_script_files(self):
        _, script_paths = self._create("Bare.app")
        self.assertEqual(script_paths, [])
        _, entry = self._entry(self.SOFTWARE_DIR, "bare-app")
        self.assertNotIn("post_install_script", entry)
        self.assertNotIn("install_script", entry)

    def test_custom_dirs_are_honored_with_correct_relative_path(self):
        # Configurable dirs: the script lands in the custom scripts dir and the
        # package YAML references it via a path relative to the package YAML.
        _, script_paths = self._create(
            "Island.app",
            software_dir="custom/sw",
            scripts_dir="custom/sh",
            post_install_script=ISLAND_POST_INSTALL,
        )
        self.assertEqual(script_paths, ["custom/sh/island-app-postinstall.sh"])
        pkg_yaml, entry = self._entry("custom/sw", "island-app")
        # custom/sw -> custom/sh  ==  ../sh/island-app-postinstall.sh
        self.assertEqual(
            entry["post_install_script"]["path"],
            "../sh/island-app-postinstall.sh",
        )
        self.assertTrue(
            (pkg_yaml.parent / entry["post_install_script"]["path"]).is_file()
        )


class TestCopyIconToGitopsRepo(unittest.TestCase):
    """Tests icon placement + relative referencing across configurable dirs."""

    def setUp(self):
        self.fi = FleetImporter.FleetImporter()
        self.fi.env = {}
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_icon_repo_and_yaml_paths(self):
        src = Path(self._tmp.name) / "src.png"
        src.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)  # tiny fake PNG
        yaml_rel, repo_rel = self.fi._copy_icon_to_gitops_repo(
            str(self.repo),
            str(src),
            "Island.app",
            "platforms/all/icons",
            "platforms/macos/software",
        )
        # repo-relative path for git staging
        self.assertEqual(repo_rel, "platforms/all/icons/island-app.png")
        self.assertTrue((self.repo / repo_rel).is_file())
        # yaml-relative: platforms/macos/software -> platforms/all/icons
        self.assertEqual(yaml_rel, "../../all/icons/island-app.png")


class TestDirectUploadScriptDelivery(unittest.TestCase):
    """Direct mode must send script *content* inline as multipart form fields.

    This guards the other half of the delivery contract: GitOps writes files and
    references them by path, while direct mode posts the resolved content inline
    to POST /api/v1/fleet/software/package. It also catches positional-argument
    mismatches between the call site and _fleet_upload_package's signature.
    """

    def setUp(self):
        self.fi = FleetImporter.FleetImporter()
        self.fi.env = {}
        self._orig_urlopen = FleetImporter.urllib.request.urlopen

    def tearDown(self):
        FleetImporter.urllib.request.urlopen = self._orig_urlopen

    @staticmethod
    def _field(body, name):
        match = re.search(r'name="%s"\r\n\r\n(.*?)\r\n--' % re.escape(name), body, re.S)
        return match.group(1) if match else None

    def _capture_upload_body(self, **kwargs):
        captured = {}

        class _FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return (
                    b'{"software_package":{"title_id":1,'
                    b'"installer_id":2,"hash_sha256":"x"}}'
                )

            def getcode(self):
                return 200

        def _fake_urlopen(req, timeout=None, context=None):
            captured["body"] = req.data
            return _FakeResp()

        FleetImporter.urllib.request.urlopen = _fake_urlopen

        with tempfile.TemporaryDirectory() as d:
            pkg = Path(d) / "app.pkg"
            pkg.write_bytes(b"PKGDATA")
            self.fi._fleet_upload_package(
                "https://fleet.example.com",
                "tok",
                pkg,
                "Island.app",
                "1.0",
                2,
                True,  # self_service
                False,  # automatic_install
                [],  # labels_include_any
                [],  # labels_exclude_any
                kwargs.get("install_script", ""),
                kwargs.get("uninstall_script", ""),
                kwargs.get("pre_install_query", ""),
                kwargs.get("post_install_script", ""),
                ["Browsers"],  # categories
                "Island",  # display_name
            )
        return captured["body"].decode("utf-8", "replace")

    def test_post_install_script_sent_inline(self):
        # Resolve exactly as the direct workflow does, then upload.
        resolved = self.fi._resolve_script_content(ISLAND_POST_INSTALL)
        body = self._capture_upload_body(post_install_script=resolved)
        # The full script body is present as a form field value...
        self.assertEqual(self._field(body, "post_install_script"), ISLAND_POST_INSTALL)
        # ...and it is NOT turned into a file path reference.
        self.assertNotIn("platforms/macos/scripts", body)

    def test_all_script_fields_sent_inline(self):
        body = self._capture_upload_body(
            install_script="echo install",
            uninstall_script="echo uninstall",
            pre_install_query="SELECT 1;",
            post_install_script="echo post",
        )
        self.assertEqual(self._field(body, "install_script"), "echo install")
        self.assertEqual(self._field(body, "uninstall_script"), "echo uninstall")
        self.assertEqual(self._field(body, "pre_install_query"), "SELECT 1;")
        self.assertEqual(self._field(body, "post_install_script"), "echo post")

    def test_empty_scripts_omit_fields(self):
        body = self._capture_upload_body()
        self.assertIsNone(self._field(body, "install_script"))
        self.assertIsNone(self._field(body, "post_install_script"))


class TestGitopsPathFallback(unittest.TestCase):
    """_gitops_path must fall back to the default for unset/empty values and
    for AutoPkg %PLACEHOLDER% references that were left unsubstituted because
    the recipe variable was undefined."""

    # Mirrors the processor's GitOps path defaults.
    DEFAULTS = {
        "gitops_software_dir": "platforms/macos/software",
        "gitops_scripts_dir": "platforms/macos/scripts",
        "gitops_icons_dir": "platforms/all/icons",
        "gitops_policies_dir": "platforms/macos/policies",
        "gitops_team_yaml_path": "fleets/workstations.yml",
    }

    def setUp(self):
        self.fi = FleetImporter.FleetImporter()
        self.fi.env = {}

    def test_uses_default_when_key_absent(self):
        for key, default in self.DEFAULTS.items():
            self.fi.env = {}
            self.assertEqual(self.fi._gitops_path(key, default), default)

    def test_uses_default_when_empty_or_whitespace(self):
        for key, default in self.DEFAULTS.items():
            for blank in ("", "   "):
                self.fi.env = {key: blank}
                self.assertEqual(self.fi._gitops_path(key, default), default)

    def test_uses_default_when_placeholder_unsubstituted(self):
        # AutoPkg leaves "%VAR%" intact when VAR is undefined; treat as unset.
        placeholders = {
            "gitops_software_dir": "%FLEET_GITOPS_SOFTWARE_DIR%",
            "gitops_scripts_dir": "%FLEET_GITOPS_SCRIPTS_DIR%",
            "gitops_icons_dir": "%FLEET_GITOPS_ICONS_DIR%",
            "gitops_policies_dir": "%FLEET_GITOPS_POLICIES_DIR%",
            "gitops_team_yaml_path": "%FLEET_GITOPS_TEAM_YAML_PATH%",
        }
        for key, placeholder in placeholders.items():
            self.fi.env = {key: placeholder}
            self.assertEqual(
                self.fi._gitops_path(key, self.DEFAULTS[key]), self.DEFAULTS[key]
            )

    def test_honors_explicit_override(self):
        self.fi.env = {"gitops_scripts_dir": "custom/scripts"}
        self.assertEqual(
            self.fi._gitops_path(
                "gitops_scripts_dir", self.DEFAULTS["gitops_scripts_dir"]
            ),
            "custom/scripts",
        )

    def test_does_not_treat_real_path_with_percent_as_placeholder(self):
        # A real value that merely contains '%' (not a full %VAR% token) is kept.
        self.fi.env = {"gitops_scripts_dir": "platforms/macos/scripts%backup"}
        self.assertEqual(
            self.fi._gitops_path(
                "gitops_scripts_dir", self.DEFAULTS["gitops_scripts_dir"]
            ),
            "platforms/macos/scripts%backup",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
