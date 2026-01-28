# -*- coding: utf-8 -*-
#
# FleetImporter AutoPkg Processor
#
# Uploads a package to Fleet for software deployment.
#
# Requires: Python 3.9+
#

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import ssl
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import certifi
import yaml
from autopkglib import Processor, ProcessorError

__all__ = ["FleetImporter"]

# boto3 is only required for GitOps mode (S3 uploads)
# It will be imported lazily when needed to avoid requiring it for direct mode
boto3 = None
ClientError = None
NoCredentialsError = None

# Constants for improved readability
DEFAULT_PLATFORM = "darwin"

# Fleet version constants
FLEET_MINIMUM_VERSION = "4.74.0"

# HTTP timeout constants (in seconds)
FLEET_VERSION_TIMEOUT = 30
FLEET_UPLOAD_TIMEOUT = 900  # 15 minutes for large packages


class FleetImporter(Processor):
    """
    Upload AutoPkg-built installer packages to Fleet for software deployment.

    This processor uploads software packages (.pkg files) to Fleet and configures
    deployment settings including self-service availability, automatic installation,
    host targeting via labels, and custom install/uninstall scripts.

    Dependencies:
        - boto3>=1.18.0: Required for GitOps mode S3 operations. Will be automatically
          installed if not present when GitOps mode is used.
        - Native Python libraries only for direct mode (no external dependencies)
    """

    description = __doc__
    input_variables = {
        # --- Required basics ---
        "pkg_path": {
            "required": True,
            "description": "Path to the built .pkg from AutoPkg.",
        },
        "software_title": {
            "required": True,
            "description": "Human-readable software title, e.g., 'Firefox.app'.",
        },
        "version": {
            "required": True,
            "description": "Software version string.",
        },
        "platform": {
            "required": False,
            "default": DEFAULT_PLATFORM,
            "description": "Platform (darwin|windows|linux|ios|ipados). Default: darwin",
        },
        # --- Fleet API (required for direct mode, optional for GitOps mode) ---
        "fleet_api_base": {
            "required": False,
            "description": "Fleet base URL, e.g., https://fleet.example.com (required for direct mode)",
        },
        "fleet_api_token": {
            "required": False,
            "description": "Fleet API token (Bearer) (required for direct mode).",
        },
        "team_id": {
            "required": False,
            "description": "Fleet team ID to attach the uploaded package to (required for direct mode).",
        },
        # --- GitOps mode ---
        "gitops_mode": {
            "required": False,
            "default": False,
            "description": "Enable GitOps mode: upload to S3 and create PR instead of direct Fleet upload.",
        },
        "aws_s3_bucket": {
            "required": False,
            "description": "S3 bucket name for package storage (required for GitOps mode).",
        },
        "aws_cloudfront_domain": {
            "required": False,
            "description": "CloudFront distribution domain (required for GitOps mode), e.g., cdn.example.com",
        },
        "gitops_repo_url": {
            "required": False,
            "description": "GitOps repository URL (required for GitOps mode), e.g., https://github.com/org/fleet-gitops.git. Use FLEET_GITOPS_REPO_URL environment variable.",
        },
        "gitops_software_dir": {
            "required": False,
            "default": "lib/macos/software",
            "description": "Directory for software package YAMLs within GitOps repo (default: lib/macos/software). Use FLEET_GITOPS_SOFTWARE_DIR environment variable.",
        },
        "gitops_team_yaml_path": {
            "required": False,
            "description": "Path to team YAML file within GitOps repo (required for GitOps mode), e.g., teams/team-name.yml. Use FLEET_GITOPS_TEAM_YAML_PATH environment variable.",
        },
        "github_token": {
            "required": False,
            "description": "GitHub personal access token for cloning and creating PRs (required for GitOps mode). Use FLEET_GITOPS_GITHUB_TOKEN environment variable.",
        },
        "s3_retention_versions": {
            "required": False,
            "default": 0,
            "description": "Number of old versions to retain per software title in S3. Set to 0 to disable pruning (default: 0).",
        },
        # --- AWS Configuration (required for GitOps mode) ---
        "aws_access_key_id": {
            "required": False,
            "description": "AWS access key ID for S3 operations (required for GitOps mode).",
        },
        "aws_secret_access_key": {
            "required": False,
            "description": "AWS secret access key for S3 operations (required for GitOps mode).",
        },
        "aws_default_region": {
            "required": False,
            "default": "us-east-1",
            "description": "AWS region for S3 operations (default: us-east-1).",
        },
        # --- Fleet deployment options ---
        "self_service": {
            "required": False,
            "default": True,
            "description": "Whether the package is available for self-service installation.",
        },
        "automatic_install": {
            "required": False,
            "default": False,
            "description": "macOS-only: automatically install on hosts that don't have this software.",
        },
        "labels_include_any": {
            "required": False,
            "default": [],
            "description": "List of label names - software is available on hosts with ANY of these labels.",
        },
        "labels_exclude_any": {
            "required": False,
            "default": [],
            "description": "List of label names - software is excluded from hosts with ANY of these labels.",
        },
        "install_script": {
            "required": False,
            "default": "",
            "description": "Custom install script - either inline script body (string) or path to .sh file (relative to recipe dir or absolute).",
        },
        "uninstall_script": {
            "required": False,
            "default": "",
            "description": "Custom uninstall script - either inline script body (string) or path to .sh file (relative to recipe dir or absolute).",
        },
        "icon": {
            "required": False,
            "default": "",
            "description": "Path to PNG icon file (square, 120x120 to 1024x1024 px) to upload to Fleet. If not provided, will attempt to extract icon from app bundle automatically.",
        },
        "pre_install_query": {
            "required": False,
            "default": "",
            "description": "Pre-install osquery SQL condition.",
        },
        "post_install_script": {
            "required": False,
            "default": "",
            "description": "Post-install script - either inline script body (string) or path to .sh file (relative to recipe dir or absolute).",
        },
        "categories": {
            "required": False,
            "default": [],
            "description": "List of category names to group self-service software in Fleet Desktop (e.g., ['Productivity', 'Browser']).",
        },
        "display_name": {
            "required": False,
            "default": "",
            "description": "Custom display name for the software in Fleet (e.g., 'CrowdStrike Falcon' instead of 'Falcon.app'). If not provided, Fleet will use the software_title.",
        },
        # --- Auto-update policy options ---
        "automatic_update": {
            "required": False,
            "default": False,
            "description": "Enable auto-update policy creation. Creates a Fleet policy that automatically installs software on devices with outdated versions.",
        },
        "auto_update_policy_name": {
            "required": False,
            "default": "autopkg-auto-update-%NAME%",
            "description": "Template for auto-update policy name. Use %NAME% as placeholder for software title (default: autopkg-auto-update-%NAME%).",
        },
        "auto_update_policy_query": {
            "required": False,
            "default": "",
            "description": "Query template for auto-update policy. Use %VERSION% as placeholder for version number. If not specified, a default query using bundle_identifier will be generated (macOS apps only).",
        },
    }

    output_variables = {
        "fleet_title_id": {"description": "Created/updated Fleet software title ID."},
        "fleet_installer_id": {"description": "Installer ID in Fleet."},
        "hash_sha256": {
            "description": "SHA-256 hash of the uploaded package, as returned by Fleet."
        },
        "cloudfront_url": {
            "description": "CloudFront URL for the uploaded package (GitOps mode only)."
        },
        "pull_request_url": {
            "description": "URL of the created pull request (GitOps mode only)."
        },
        "git_branch": {
            "description": "Name of the Git branch created for the PR (GitOps mode only)."
        },
    }

    def _get_ssl_context(self):
        """Create an SSL context using certifi's CA bundle."""
        return ssl.create_default_context(cafile=certifi.where())

    def _build_version_query(
        self, version: str, query_template: str = None, bundle_id: str = None
    ) -> str:
        """Build osquery query to detect outdated software versions.

        Supports two modes:
        1. Template mode: Use provided query_template with %VERSION% placeholder
        2. Default mode: Generate query using bundle_identifier and version_compare()

        Args:
            version: Current version to check against
            query_template: Optional query template with %VERSION% placeholder
            bundle_id: App bundle identifier (required for default mode)

        Returns:
            osquery SQL query string with version substituted

        Raises:
            ProcessorError: If template mode is used without query_template,
                          or default mode is used without bundle_id
        """
        # Sanitize version for SQL (escape single quotes)
        safe_version = version.replace("'", "''")

        if query_template:
            # Template mode: Replace %VERSION% placeholder with actual version
            query = query_template.replace("%VERSION%", safe_version)
            return query
        elif bundle_id:
            # Default mode: Generate query using apps table and version_compare
            # This is the legacy behavior for macOS apps
            safe_bundle_id = bundle_id.replace("'", "''")

            # Build query using apps table for version checking
            # Policy passes when no instances exist with incorrect version
            # This means: app not installed OR all instances have correct version
            # Policy fails when any instance has wrong version (needs update)
            safe_bundle_id = bundle_id.replace("'", "''")

            query = (
                f"SELECT 1 WHERE NOT EXISTS ("
                f"SELECT 1 FROM apps WHERE bundle_identifier = '{safe_bundle_id}' "
                f"AND bundle_short_version != '{safe_version}'"
                f");"
            )
            return query
        else:
            raise ProcessorError(
                "Either query_template or bundle_id must be provided to build version query"
            )

    def _format_policy_name(self, software_title: str, template: str = None) -> str:
        """Format policy name from template.

        Args:
            software_title: Software title to use in policy name
            template: Optional template string with %NAME% placeholder

        Returns:
            Formatted policy name
        """
        if template is None:
            template = self.env.get(
                "auto_update_policy_name", "autopkg-auto-update-%NAME%"
            )

        # Create slug from software title (lowercase, hyphens only)
        slug = self._slugify(software_title)

        # Replace %NAME% placeholder with slug
        policy_name = template.replace("%NAME%", slug)

        return policy_name

    def _find_existing_policy(
        self, fleet_api_base: str, fleet_token: str, team_id: int, policy_name: str
    ) -> dict | None:
        """Find existing policy by name.

        Args:
            fleet_api_base: Fleet base URL
            fleet_token: Fleet API token
            team_id: Team ID (0 for global)
            policy_name: Policy name to search for

        Returns:
            Policy dict if found, None otherwise
        """
        try:
            # Determine endpoint based on team_id
            if team_id == 0:
                endpoint = f"{fleet_api_base}/api/v1/fleet/global/policies"
            else:
                endpoint = f"{fleet_api_base}/api/v1/fleet/teams/{team_id}/policies"

            headers = {
                "Authorization": f"Bearer {fleet_token}",
                "Accept": "application/json",
            }
            req = urllib.request.Request(endpoint, headers=headers)

            with urllib.request.urlopen(
                req, timeout=FLEET_VERSION_TIMEOUT, context=self._get_ssl_context()
            ) as resp:
                if resp.getcode() == 200:
                    data = json.loads(resp.read().decode())
                    policies = data.get("policies", [])

                    # Search for policy by name
                    for policy in policies:
                        if policy.get("name") == policy_name:
                            return policy
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            json.JSONDecodeError,
        ) as e:
            self.output(f"Warning: Could not query policies: {e}")

        return None

    def _create_or_update_policy_direct(
        self,
        fleet_api_base: str,
        fleet_token: str,
        team_id: int,
        software_title: str,
        version: str,
        title_id: int,
        pkg_path: str,
    ):
        """Create or update auto-update policy via Fleet API.

        Args:
            fleet_api_base: Fleet base URL
            fleet_token: Fleet API token
            team_id: Team ID (0 for global)
            software_title: Software title
            version: Software version
            title_id: Software title ID for linking policy to package
            pkg_path: Path to package file for bundle ID extraction
        """
        # Build policy name
        policy_name = self._format_policy_name(software_title)
        self.output(f"Auto-update policy name: {policy_name}")

        # Build version detection query
        query_template = self.env.get("auto_update_policy_query", "").strip()

        if query_template:
            # Use custom query template from recipe
            self.output("Using custom query template from recipe")
            query = self._build_version_query(version, query_template=query_template)
        else:
            # Fall back to default bundle_identifier-based query
            self.output(
                "No query template specified, using default bundle_identifier detection"
            )
            bundle_id = self._extract_bundle_id_from_pkg(Path(pkg_path))
            if not bundle_id:
                self.output(
                    f"Warning: Could not extract bundle ID from package and no query template provided. "
                    "Skipping auto-update policy creation."
                )
                return
            query = self._build_version_query(version, bundle_id=bundle_id)

        self.output(f"Auto-update policy query: {query}")

        # Check if policy already exists
        existing_policy = self._find_existing_policy(
            fleet_api_base, fleet_token, team_id, policy_name
        )

        # Prepare policy payload
        payload = {
            "name": policy_name,
            "query": query,
            "description": f"Auto-update policy for {software_title}. Managed by AutoPkg.",
            "resolution": f"This device will automatically install {software_title} {version}",
            "platform": "darwin",
            "critical": False,
            "software_title_id": title_id,
        }

        # Determine endpoint based on team_id
        if team_id == 0:
            base_endpoint = f"{fleet_api_base}/api/v1/fleet/global/policies"
        else:
            base_endpoint = f"{fleet_api_base}/api/v1/fleet/teams/{team_id}/policies"

        headers = {
            "Authorization": f"Bearer {fleet_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        try:
            if existing_policy:
                # Update existing policy
                policy_id = existing_policy["id"]
                endpoint = f"{base_endpoint}/{policy_id}"
                self.output(f"Updating existing auto-update policy (ID: {policy_id})")

                req = urllib.request.Request(
                    endpoint,
                    data=json.dumps(payload).encode(),
                    headers=headers,
                    method="PATCH",
                )
            else:
                # Create new policy
                endpoint = base_endpoint
                self.output("Creating new auto-update policy")

                req = urllib.request.Request(
                    endpoint,
                    data=json.dumps(payload).encode(),
                    headers=headers,
                    method="POST",
                )

            with urllib.request.urlopen(
                req, timeout=FLEET_VERSION_TIMEOUT, context=self._get_ssl_context()
            ) as resp:
                if resp.getcode() in (200, 201):
                    response_data = json.loads(resp.read().decode())
                    policy_id = response_data.get("policy", {}).get("id")
                    self.output(
                        f"Auto-update policy {'updated' if existing_policy else 'created'} successfully (ID: {policy_id})"
                    )
                else:
                    raise ProcessorError(
                        f"Failed to create/update policy: {resp.getcode()}"
                    )
        except urllib.error.HTTPError as e:
            error_body = e.read().decode()
            raise ProcessorError(
                f"Failed to create/update auto-update policy: {e.code} {error_body}"
            )
        except urllib.error.URLError as e:
            raise ProcessorError(
                f"Failed to connect to Fleet API for policy creation: {e}"
            )

    def _create_or_update_policy_gitops(
        self,
        repo_dir: str,
        software_title: str,
        version: str,
        pkg_path: str,
    ):
        """Create or update auto-update policy in GitOps repository.

        Args:
            repo_dir: Path to Git repository
            software_title: Software title (used to reference the software package)
            version: Software version
            pkg_path: Path to package file for bundle ID extraction

        Note:
            In GitOps mode, the policy references software by name rather than ID.
            Fleet will resolve the software_title to the appropriate software_title_id
            when it processes the GitOps configuration.
        """
        # Build policy name
        policy_name = self._format_policy_name(software_title)
        self.output(f"Auto-update policy name: {policy_name}")

        # Build version detection query
        query_template = self.env.get("auto_update_policy_query", "").strip()

        if query_template:
            # Use custom query template from recipe
            self.output("Using custom query template from recipe")
            query = self._build_version_query(version, query_template=query_template)
        else:
            # Fall back to default bundle_identifier-based query
            self.output(
                "No query template specified, using default bundle_identifier detection"
            )
            bundle_id = self._extract_bundle_id_from_pkg(Path(pkg_path))
            if not bundle_id:
                self.output(
                    f"Warning: Could not extract bundle ID from package and no query template provided. "
                    "Skipping auto-update policy creation."
                )
                return None
            query = self._build_version_query(version, bundle_id=bundle_id)

        self.output(f"Auto-update policy query: {query}")

        # Create policy YAML structure
        # In GitOps mode, reference software by name - Fleet will resolve to software_title_id
        policy_yaml = {
            "name": policy_name,
            "query": query,
            "description": f"Auto-update policy for {software_title}. Managed by AutoPkg.",
            "resolution": f"This device will automatically install {software_title} {version}",
            "platform": "darwin",
            "critical": False,
            "install_software": {
                "name": software_title,
            },
        }

        # Create lib/policies directory if it doesn't exist
        policies_dir = Path(repo_dir) / "lib" / "policies"
        policies_dir.mkdir(parents=True, exist_ok=True)

        # Write policy file
        slug = self._slugify(software_title)
        policy_filename = f"{slug}.yml"
        policy_path = policies_dir / policy_filename

        self.output(f"Writing auto-update policy to: lib/policies/{policy_filename}")
        self._write_yaml(policy_path, policy_yaml)

        # Return relative path for Git operations
        return f"lib/policies/{policy_filename}"

    def main(self):
        # Check if GitOps mode is enabled
        gitops_mode = bool(self.env.get("gitops_mode", False))

        if gitops_mode:
            self._run_gitops_workflow()
        else:
            self._run_direct_upload_workflow()

    def _run_direct_upload_workflow(self):
        """Run the original direct upload workflow to Fleet API."""
        # Validate inputs
        pkg_path = Path(self.env["pkg_path"]).expanduser().resolve()
        if not pkg_path.is_file():
            raise ProcessorError(f"pkg_path not found: {pkg_path}")

        software_title = self.env["software_title"].strip()
        version = self.env["version"].strip()
        # Platform parameter accepted for future use but not currently utilized
        _ = self.env.get("platform", DEFAULT_PLATFORM)  # noqa: F841

        # Validate required direct mode parameters
        fleet_api_base = self.env.get("fleet_api_base")
        fleet_token = self.env.get("fleet_api_token")
        team_id = self.env.get("team_id")

        if not all([fleet_api_base, fleet_token, team_id]):
            raise ProcessorError(
                "Direct mode requires: fleet_api_base, fleet_api_token, and team_id. "
                "These can be set via recipe Input variables or AutoPkg preferences:\n"
                "  defaults write com.github.autopkg FLEET_API_BASE 'https://fleet.example.com'\n"
                "  defaults write com.github.autopkg FLEET_API_TOKEN 'your-token'\n"
                "  defaults write com.github.autopkg FLEET_TEAM_ID '1'"
            )

        # Now safe to use - strip/convert values
        fleet_api_base = fleet_api_base.rstrip("/")
        team_id = int(team_id)

        # Fleet deployment options
        self_service = bool(self.env.get("self_service", False))
        automatic_install = bool(self.env.get("automatic_install", False))
        labels_include_any = list(self.env.get("labels_include_any", []))
        labels_exclude_any = list(self.env.get("labels_exclude_any", []))
        categories = list(self.env.get("categories", []))

        # Display name: optional custom display name for Fleet UI
        # If not provided, use software_title as default
        display_name = self.env.get("display_name", "").strip()
        if not display_name:
            display_name = software_title

        # Read script files if paths are provided, otherwise use inline content
        install_script_input = self.env.get("install_script", "")
        uninstall_script_input = self.env.get("uninstall_script", "")
        pre_install_query = self.env.get("pre_install_query", "")
        post_install_script_input = self.env.get("post_install_script", "")

        # Check if inputs look like file paths (end with .sh or contain /) or inline scripts
        # If they look like paths, read the file content
        install_script = (
            self._read_script_file(install_script_input)
            if (
                install_script_input
                and (
                    install_script_input.endswith(".sh") or "/" in install_script_input
                )
            )
            else install_script_input
        )

        uninstall_script = (
            self._read_script_file(uninstall_script_input)
            if (
                uninstall_script_input
                and (
                    uninstall_script_input.endswith(".sh")
                    or "/" in uninstall_script_input
                )
            )
            else uninstall_script_input
        )

        post_install_script = (
            self._read_script_file(post_install_script_input)
            if (
                post_install_script_input
                and (
                    post_install_script_input.endswith(".sh")
                    or "/" in post_install_script_input
                )
            )
            else post_install_script_input
        )

        # Validate label targeting - only one of include/exclude allowed
        if labels_include_any and labels_exclude_any:
            raise ProcessorError(
                "Only one of labels_include_any or labels_exclude_any may be specified, not both."
            )

        # Validate categories - required when self_service is enabled
        if self_service and not categories:
            raise ProcessorError(
                "CATEGORIES is required when SELF_SERVICE is true. Please specify at least one category."
            )

        # Query Fleet API to get server version
        self.output("Querying Fleet server version...")
        fleet_version = self._get_fleet_version(fleet_api_base, fleet_token)
        self.output(f"Detected Fleet version: {fleet_version}")

        # Check minimum version requirements
        if not self._is_fleet_minimum_supported(fleet_version):
            raise ProcessorError(
                f"Fleet version {fleet_version} is not supported. "
                f"This processor requires Fleet v{FLEET_MINIMUM_VERSION} or higher. "
                f"Please upgrade your Fleet server to a supported version."
            )

        # Check if package already exists in Fleet
        self.output(
            f"Checking if {software_title} {version} already exists in Fleet..."
        )
        existing_package = self._check_existing_package(
            fleet_api_base, fleet_token, team_id, software_title, version
        )

        if existing_package:
            self.output(
                f"Package {software_title} {version} already exists in Fleet. Skipping upload."
            )
            # Calculate hash from local package file
            hash_sha256 = self._calculate_file_sha256(pkg_path)
            self.output(
                f"Calculated SHA-256 hash from local file: {hash_sha256[:16]}..."
            )
            # Set output variables for existing package
            title_id = existing_package.get("title_id")
            self.env["fleet_title_id"] = title_id
            self.env["fleet_installer_id"] = None
            self.env["hash_sha256"] = hash_sha256

            # Still create/update auto-update policy if enabled
            automatic_update = bool(self.env.get("automatic_update", False))
            if automatic_update and title_id:
                self.output("Auto-update policy enabled - creating/updating policy...")
                try:
                    self._create_or_update_policy_direct(
                        fleet_api_base,
                        fleet_token,
                        team_id,
                        software_title,
                        version,
                        title_id,
                        pkg_path,
                    )
                except Exception as e:
                    # Log warning but don't fail the entire workflow
                    self.output(
                        f"Warning: Failed to create auto-update policy: {e}. "
                        "Package already exists, but policy creation failed."
                    )
            return

        # Upload to Fleet
        self.output("Uploading package to Fleet...")
        upload_info = self._fleet_upload_package(
            fleet_api_base,
            fleet_token,
            pkg_path,
            software_title,
            version,
            team_id,
            self_service,
            automatic_install,
            labels_include_any,
            labels_exclude_any,
            install_script,
            uninstall_script,
            pre_install_query,
            post_install_script,
            categories,
            display_name,
        )

        if not upload_info:
            raise ProcessorError("Fleet package upload failed; no data returned")

        # Check for graceful exit case (409 Conflict)
        if upload_info.get("package_exists"):
            self.output(
                "Package already exists in Fleet (409 Conflict). Exiting gracefully."
            )
            self.env["fleet_title_id"] = None
            self.env["fleet_installer_id"] = None
            return

        # Extract upload results
        software_package = upload_info.get("software_package", {})
        title_id = software_package.get("title_id")
        installer_id = software_package.get("installer_id")
        hash_sha256 = software_package.get("hash_sha256")

        # Set output variables
        self.output(
            f"Package uploaded successfully. Title ID: {title_id}, Installer ID: {installer_id}"
        )
        self.env["fleet_title_id"] = title_id
        self.env["fleet_installer_id"] = installer_id
        if hash_sha256:
            self.env["hash_sha256"] = hash_sha256

        # Upload icon if provided
        icon_path_str = self.env.get("icon", "").strip()

        extracted_icon_path = None  # Track if we need to clean up

        if icon_path_str and title_id:
            # Manual icon path provided - use it
            # Try to resolve icon path relative to recipe directory first
            icon_path = Path(icon_path_str)
            if not icon_path.is_absolute():
                # Get recipe directory from AutoPkg environment
                recipe_dir = self.env.get("RECIPE_DIR")
                if recipe_dir:
                    icon_path = (Path(recipe_dir) / icon_path_str).resolve()
                else:
                    icon_path = icon_path.expanduser().resolve()
            else:
                icon_path = icon_path.expanduser().resolve()

            if icon_path.exists():
                self.output(f"Using manual icon file: {icon_path}")
                self._fleet_upload_icon(
                    fleet_api_base,
                    fleet_token,
                    title_id,
                    team_id,
                    icon_path,
                )
            else:
                self.output(
                    f"Warning: Icon file not found: {icon_path}. Skipping icon upload."
                )
        elif title_id:
            # No manual icon - try to extract from package automatically
            self.output("Attempting to extract icon from package automatically...")
            extracted_icon_path = self._extract_icon_from_pkg(pkg_path)

            if extracted_icon_path and extracted_icon_path.exists():
                self.output(f"Successfully extracted icon: {extracted_icon_path.name}")
                try:
                    self._fleet_upload_icon(
                        fleet_api_base,
                        fleet_token,
                        title_id,
                        team_id,
                        extracted_icon_path,
                    )
                finally:
                    # Clean up extracted icon temp directory
                    if extracted_icon_path.parent.exists():
                        try:
                            shutil.rmtree(extracted_icon_path.parent)
                        except Exception as e:
                            self.output(
                                f"Warning: Failed to cleanup icon temp dir: {e}"
                            )
            else:
                self.output(
                    "Could not extract icon from package. Skipping icon upload."
                )

        # Create auto-update policy if enabled
        automatic_update = bool(self.env.get("automatic_update", False))
        if automatic_update and title_id:
            self.output("Auto-update policy enabled - creating/updating policy...")
            try:
                self._create_or_update_policy_direct(
                    fleet_api_base,
                    fleet_token,
                    team_id,
                    software_title,
                    version,
                    title_id,
                    pkg_path,
                )
            except Exception as e:
                # Log warning but don't fail the entire workflow
                self.output(
                    f"Warning: Failed to create auto-update policy: {e}. "
                    "Package upload succeeded, but policy creation failed."
                )
        elif automatic_update and not title_id:
            self.output(
                "Warning: Auto-update policy enabled but no software title ID available. "
                "Skipping policy creation."
            )

    def _run_gitops_workflow(self):
        """Run the GitOps workflow: upload to S3, update YAML, create PR."""
        # Import boto3 for GitOps mode (required for S3 operations)
        global boto3, ClientError, NoCredentialsError
        try:
            import boto3
            from botocore.exceptions import ClientError, NoCredentialsError
        except ImportError:
            raise ProcessorError(
                "boto3 is required for GitOps mode.\n\n"
                "Install it into AutoPkg's Python environment with:\n"
                "  /Library/AutoPkg/Python3/Python.framework/Versions/Current/bin/python3 -m pip install boto3>=1.18.0\n\n"
                "Or use direct mode to upload directly to Fleet API without S3/GitOps:\n"
                "  Set gitops_mode to false in your recipe or AutoPkg preferences."
            )

        # Validate inputs
        pkg_path = Path(self.env["pkg_path"]).expanduser().resolve()
        if not pkg_path.is_file():
            raise ProcessorError(f"pkg_path not found: {pkg_path}")

        software_title = self.env["software_title"].strip()
        version = self.env["version"].strip()

        # GitOps mode required parameters
        aws_s3_bucket = self.env.get("aws_s3_bucket")
        aws_cloudfront_domain = self.env.get("aws_cloudfront_domain")
        gitops_repo_url = self.env.get("gitops_repo_url")
        gitops_software_dir = self.env.get("gitops_software_dir", "lib/macos/software")
        gitops_team_yaml_path = self.env.get("gitops_team_yaml_path")
        github_token = self.env.get("github_token")
        s3_retention_versions = int(self.env.get("s3_retention_versions", 0))

        # Validate required GitOps parameters
        if not all(
            [
                aws_s3_bucket,
                aws_cloudfront_domain,
                gitops_repo_url,
                gitops_team_yaml_path,
                github_token,
            ]
        ):
            raise ProcessorError(
                "GitOps mode requires: aws_s3_bucket, aws_cloudfront_domain, "
                "gitops_repo_url, gitops_team_yaml_path, and github_token"
            )

        # Fleet deployment options
        self_service = bool(self.env.get("self_service", True))
        automatic_install = bool(self.env.get("automatic_install", False))
        labels_include_any = list(self.env.get("labels_include_any", []))
        labels_exclude_any = list(self.env.get("labels_exclude_any", []))
        categories = list(self.env.get("categories", []))

        # Display name: optional custom display name for Fleet UI
        # If not provided, use software_title as default
        display_name = self.env.get("display_name", "").strip()
        if not display_name:
            display_name = software_title

        # Read script files if paths are provided, otherwise use inline content
        install_script_input = self.env.get("install_script", "")
        uninstall_script_input = self.env.get("uninstall_script", "")
        pre_install_query = self.env.get("pre_install_query", "")
        post_install_script_input = self.env.get("post_install_script", "")

        # Check if inputs look like file paths (end with .sh or contain /) or inline scripts
        # If they look like paths, read the file content
        install_script = (
            self._read_script_file(install_script_input)
            if (
                install_script_input
                and (
                    install_script_input.endswith(".sh") or "/" in install_script_input
                )
            )
            else install_script_input
        )

        uninstall_script = (
            self._read_script_file(uninstall_script_input)
            if (
                uninstall_script_input
                and (
                    uninstall_script_input.endswith(".sh")
                    or "/" in uninstall_script_input
                )
            )
            else uninstall_script_input
        )

        post_install_script = (
            self._read_script_file(post_install_script_input)
            if (
                post_install_script_input
                and (
                    post_install_script_input.endswith(".sh")
                    or "/" in post_install_script_input
                )
            )
            else post_install_script_input
        )

        icon_path_str = self.env.get("icon", "").strip()

        # Validate label targeting - only one of include/exclude allowed
        if labels_include_any and labels_exclude_any:
            raise ProcessorError(
                "Only one of labels_include_any or labels_exclude_any may be specified, not both."
            )

        # Validate categories - required when self_service is enabled
        if self_service and not categories:
            raise ProcessorError(
                "CATEGORIES is required when SELF_SERVICE is true. Please specify at least one category."
            )

        # Clone GitOps repository first (fail early if this doesn't work)
        self.output(f"Cloning GitOps repository: {gitops_repo_url}")
        temp_dir = None
        extracted_icon_path = None  # Track extracted icon for cleanup
        try:
            temp_dir = self._clone_gitops_repo(gitops_repo_url, github_token)
            self.output(f"Repository cloned to: {temp_dir}")

            # Handle icon - either from manual path or auto-extraction
            icon_relative_path = None

            if icon_path_str:
                # Manual icon path provided
                icon_relative_path = self._copy_icon_to_gitops_repo(
                    temp_dir, icon_path_str, software_title
                )
            else:
                # Try to extract icon from package automatically
                self.output("Attempting to extract icon from package automatically...")
                extracted_icon_path = self._extract_icon_from_pkg(pkg_path)

                if extracted_icon_path and extracted_icon_path.exists():
                    self.output(
                        f"Successfully extracted icon: {extracted_icon_path.name}"
                    )
                    # Copy extracted icon to GitOps repo
                    icon_relative_path = self._copy_icon_to_gitops_repo(
                        temp_dir, str(extracted_icon_path), software_title
                    )
                else:
                    self.output(
                        "Could not extract icon from package. Skipping icon in GitOps."
                    )

            # Upload package to S3
            self.output(f"Uploading package to S3 bucket: {aws_s3_bucket}")
            s3_key, package_was_uploaded = self._upload_to_s3(
                aws_s3_bucket, software_title, version, pkg_path
            )
            self.output(f"Package in S3: {s3_key}")

            # Calculate SHA-256 hash
            # If package was uploaded, hash the local file
            # If package already existed in S3, download and hash it to ensure accuracy
            if package_was_uploaded:
                self.output(
                    f"Calculating SHA-256 hash from local file: {pkg_path.name}"
                )
                hash_sha256 = self._calculate_file_sha256(pkg_path)
            else:
                self.output(
                    "Package already exists in S3. Downloading to calculate accurate SHA-256 hash..."
                )
                hash_sha256 = self._calculate_s3_file_sha256(aws_s3_bucket, s3_key)

            self.output(f"SHA-256: {hash_sha256}")

            # Construct CloudFront URL
            cloudfront_url = self._construct_cloudfront_url(
                aws_cloudfront_domain, s3_key
            )
            self.output(f"CloudFront URL: {cloudfront_url}")
            self.env["cloudfront_url"] = cloudfront_url
            self.env["hash_sha256"] = hash_sha256

            # Clean up old versions in S3
            if s3_retention_versions > 0:
                self.output(
                    f"Cleaning up old S3 versions (retaining {s3_retention_versions} most recent)..."
                )
                self._cleanup_old_s3_versions(
                    aws_s3_bucket, software_title, version, s3_retention_versions
                )
            else:
                self.output("S3 pruning disabled (s3_retention_versions = 0)")

            # Create software package YAML file
            self.output(f"Creating software package YAML in {gitops_software_dir}")
            package_yaml_path = self._create_software_package_yaml(
                temp_dir,
                gitops_software_dir,
                software_title,
                cloudfront_url,
                hash_sha256,
                install_script,
                uninstall_script,
                pre_install_query,
                post_install_script,
                icon_relative_path,
                display_name,
            )

            # Update team YAML file to reference the package
            self.output(f"Updating team YAML: {gitops_team_yaml_path}")
            team_yaml_path = Path(temp_dir) / gitops_team_yaml_path
            self._update_team_yaml(
                team_yaml_path,
                package_yaml_path,
                software_title,
                self_service,
                automatic_install,
                labels_include_any,
                labels_exclude_any,
                categories,
            )

            # Create auto-update policy if enabled
            policy_yaml_path = None
            automatic_update = bool(self.env.get("automatic_update", False))
            if automatic_update:
                self.output("Auto-update policy enabled - creating policy YAML...")
                try:
                    policy_yaml_path = self._create_or_update_policy_gitops(
                        temp_dir,
                        software_title,
                        version,
                        pkg_path,
                    )
                except Exception as e:
                    # Log warning but don't fail the entire workflow
                    self.output(
                        f"Warning: Failed to create auto-update policy YAML: {e}. "
                        "Package upload succeeded, but policy creation failed."
                    )

            # Create Git branch, commit, and push
            branch_name = f"autopkg/{self._slugify(software_title)}-{version}"
            self.output(f"Creating Git branch: {branch_name}")
            self._commit_and_push(
                temp_dir,
                branch_name,
                software_title,
                version,
                package_yaml_path,
                team_yaml_path,
                icon_relative_path,
                policy_yaml_path,
            )
            self.env["git_branch"] = branch_name

            # Create pull request
            self.output("Creating pull request...")
            pr_url = self._create_pull_request(
                gitops_repo_url, github_token, branch_name, software_title, version
            )
            self.output(f"Pull request created: {pr_url}")
            self.env["pull_request_url"] = pr_url

        except Exception as e:
            # If we have a CloudFront URL, log it so it can be manually added
            if "cloudfront_url" in self.env:
                self.output(
                    f"ERROR: GitOps workflow failed, but package was uploaded to: {self.env['cloudfront_url']}"
                )
            raise ProcessorError(f"GitOps workflow failed: {e}")
        finally:
            # Clean up extracted icon temp directory
            if extracted_icon_path and extracted_icon_path.parent.exists():
                try:
                    shutil.rmtree(extracted_icon_path.parent)
                except Exception as e:
                    self.output(f"Warning: Failed to cleanup icon temp dir: {e}")
            # Always clean up temporary directory
            if temp_dir and Path(temp_dir).exists():
                self.output(f"Cleaning up temporary directory: {temp_dir}")
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    self.output(f"Warning: Failed to cleanup temp dir: {e}")

    # ------------------- helpers -------------------

    def _slugify(self, text: str) -> str:
        """Convert text to a URL-safe slug.

        Args:
            text: Text to slugify

        Returns:
            Lowercase slug with hyphens instead of spaces/special chars
        """
        # Convert to lowercase and replace non-alphanumeric with hyphens
        slug = re.sub(r"[^a-z0-9]+", "-", text.lower())
        # Remove leading/trailing hyphens
        return slug.strip("-")

    def _read_script_file(self, script_path_str: str) -> str:
        """Read script content from a file path.

        Args:
            script_path_str: Path to script file (relative or absolute)

        Returns:
            Script content as string, or empty string if file not found

        Notes:
            - If path is relative, resolves relative to recipe directory
            - Returns empty string if file doesn't exist (with warning)
        """
        if not script_path_str:
            return ""

        script_path = Path(script_path_str)

        # Resolve relative paths relative to recipe directory
        if not script_path.is_absolute():
            recipe_dir = self.env.get("RECIPE_DIR")
            if recipe_dir:
                script_path = (Path(recipe_dir) / script_path_str).resolve()
            else:
                script_path = script_path.expanduser().resolve()
        else:
            script_path = script_path.expanduser().resolve()

        if script_path.exists():
            try:
                with open(script_path, "r", encoding="utf-8") as f:
                    content = f.read()
                self.output(f"Read script file: {script_path}")
                return content
            except Exception as e:
                self.output(
                    f"Warning: Could not read script file {script_path}: {e}. Using empty script."
                )
                return ""
        else:
            self.output(
                f"Warning: Script file not found: {script_path}. Using empty script."
            )
            return ""

    def _extract_icon_from_pkg(self, pkg_path: Path) -> Path | None:
        """Extract and convert app icon from a package to PNG format.

        Args:
            pkg_path: Path to .pkg file

        Returns:
            Path to extracted PNG icon file in temp directory, or None if extraction fails

        Raises:
            ProcessorError: If icon extraction fails critically
        """
        try:
            # Create temporary directory for extraction
            temp_dir = Path(tempfile.mkdtemp(prefix="fleetimporter-icon-"))

            # First, expand the pkg to find the app bundle
            # Note: pkgutil --expand will create the target directory, so don't create it beforehand
            pkg_expand_dir = temp_dir / "pkg_contents"

            self.output(f"Expanding package to find app bundle: {pkg_path.name}")
            result = subprocess.run(
                ["pkgutil", "--expand", str(pkg_path), str(pkg_expand_dir)],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                self.output(
                    f"Warning: Could not expand package: {result.stderr}. Skipping icon extraction."
                )
                shutil.rmtree(temp_dir, ignore_errors=True)
                return None

            # Find .app bundles within the expanded package
            app_bundles = list(pkg_expand_dir.rglob("*.app"))

            # If no .app bundles found directly, check for Payload archives
            if not app_bundles:
                self.output(
                    "No .app bundle found directly in package. Checking Payload archives..."
                )
                payload_files = list(pkg_expand_dir.rglob("Payload"))

                for payload_file in payload_files:
                    if payload_file.is_file():
                        self.output(f"Found Payload archive: {payload_file}")
                        # Extract Payload archive to find .app bundles
                        payload_extract_dir = temp_dir / "payload_extracted"
                        payload_extract_dir.mkdir(exist_ok=True)

                        try:
                            # Try to extract as gzip compressed tar (most common)
                            result = subprocess.run(
                                [
                                    "tar",
                                    "-xzf",
                                    str(payload_file),
                                    "-C",
                                    str(payload_extract_dir),
                                ],
                                capture_output=True,
                                text=True,
                            )

                            if result.returncode != 0:
                                # Try as bzip2 compressed tar
                                result = subprocess.run(
                                    [
                                        "tar",
                                        "-xjf",
                                        str(payload_file),
                                        "-C",
                                        str(payload_extract_dir),
                                    ],
                                    capture_output=True,
                                    text=True,
                                )

                            if result.returncode != 0:
                                # Try as uncompressed tar
                                result = subprocess.run(
                                    [
                                        "tar",
                                        "-xf",
                                        str(payload_file),
                                        "-C",
                                        str(payload_extract_dir),
                                    ],
                                    capture_output=True,
                                    text=True,
                                )

                            if result.returncode == 0:
                                # Search for .app bundles in extracted payload
                                app_bundles = list(payload_extract_dir.rglob("*.app"))
                                if app_bundles:
                                    self.output(
                                        f"Found {len(app_bundles)} .app bundle(s) in Payload archive"
                                    )
                                    break
                                else:
                                    # Some packages have app bundle contents without the .app wrapper
                                    # Look for directories containing Contents/Info.plist OR
                                    # a Contents directory with Info.plist directly inside it
                                    self.output(
                                        "No .app bundles found. Checking for unwrapped app bundle contents..."
                                    )
                                    for candidate_dir in payload_extract_dir.iterdir():
                                        if candidate_dir.is_dir():
                                            # Case 1: Directory contains Contents/Info.plist
                                            info_plist = (
                                                candidate_dir
                                                / "Contents"
                                                / "Info.plist"
                                            )
                                            if info_plist.exists():
                                                self.output(
                                                    f"Found unwrapped app bundle contents at: {candidate_dir}"
                                                )
                                                # Treat this as an app bundle (the directory containing Contents/)
                                                app_bundles.append(candidate_dir)
                                                break

                                            # Case 2: Directory IS the Contents directory with Info.plist inside
                                            if candidate_dir.name == "Contents":
                                                info_plist = (
                                                    candidate_dir / "Info.plist"
                                                )
                                                if info_plist.exists():
                                                    self.output(
                                                        f"Found Contents directory directly at: {candidate_dir}"
                                                    )
                                                    # Treat the parent directory as the app bundle
                                                    app_bundles.append(
                                                        payload_extract_dir
                                                    )
                                                    break
                                    if app_bundles:
                                        break
                        except Exception as e:
                            self.output(f"Warning: Could not extract Payload: {e}")
                            continue

            if not app_bundles:
                self.output(
                    "Warning: No .app bundle found in package or Payload archives. Skipping icon extraction."
                )
                shutil.rmtree(temp_dir, ignore_errors=True)
                return None

            # Use the first app bundle found
            app_bundle = app_bundles[0]
            self.output(f"Found app bundle: {app_bundle.name}")

            # Extract icon using the _extract_icon_from_app helper
            icon_path = self._extract_icon_from_app(app_bundle, temp_dir)

            if icon_path and icon_path.exists():
                # Verify the icon meets size requirements
                icon_size_bytes = icon_path.stat().st_size
                icon_size_kb = icon_size_bytes / 1024

                if icon_size_bytes > 100 * 1024:  # 100KB limit
                    self.output(
                        f"Warning: Extracted icon is {icon_size_kb:.1f} KB, which exceeds Fleet's 100 KB limit. "
                        f"Attempting to compress..."
                    )
                    # Try to compress the icon
                    compressed_icon = self._compress_icon(icon_path, temp_dir)
                    if compressed_icon:
                        icon_path = compressed_icon
                        icon_size_kb = icon_path.stat().st_size / 1024
                        self.output(
                            f"Compressed icon to {icon_size_kb:.1f} KB successfully"
                        )
                    else:
                        self.output(
                            "Warning: Could not compress icon below 100 KB. Skipping icon upload."
                        )
                        shutil.rmtree(temp_dir, ignore_errors=True)
                        return None

                self.output(
                    f"Successfully extracted icon: {icon_path.name} ({icon_size_kb:.1f} KB)"
                )
                return icon_path
            else:
                shutil.rmtree(temp_dir, ignore_errors=True)
                return None

        except Exception as e:
            self.output(
                f"Warning: Icon extraction failed with error: {e}. Skipping icon extraction."
            )
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
            return None

    def _extract_icon_from_app(self, app_bundle: Path, temp_dir: Path) -> Path | None:
        """Extract icon from an .app bundle and convert to PNG.

        Args:
            app_bundle: Path to .app bundle or directory containing Contents/
            temp_dir: Temporary directory for output

        Returns:
            Path to PNG icon file, or None if extraction fails
        """
        try:
            # Handle both .app bundles and unwrapped app bundle contents
            # Check if we have Contents/Info.plist directly (unwrapped bundle)
            info_plist = app_bundle / "Contents" / "Info.plist"
            if not info_plist.exists():
                # Maybe we were passed the Contents directory itself?
                # This shouldn't happen with current code, but handle it for robustness
                if (
                    app_bundle.name == "Contents"
                    and (app_bundle / "Info.plist").exists()
                ):
                    # Adjust app_bundle to be the parent directory
                    app_bundle = app_bundle.parent
                    info_plist = app_bundle / "Contents" / "Info.plist"

            if not info_plist.exists():
                self.output(f"Warning: Info.plist not found in {app_bundle.name}")
                return None

            icon_file = None

            # Try CFBundleIconFile first (legacy .icns approach)
            result = subprocess.run(
                ["plutil", "-extract", "CFBundleIconFile", "raw", str(info_plist)],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0 and result.stdout.strip():
                icon_name = result.stdout.strip()
                # Add .icns extension if not present
                if not icon_name.endswith(".icns"):
                    icon_name += ".icns"

                # Find the icon file in the app bundle
                icon_file = app_bundle / "Contents" / "Resources" / icon_name
                if not icon_file.exists():
                    # Try without extension
                    icon_name_no_ext = icon_name.replace(".icns", "")
                    icon_file = (
                        app_bundle
                        / "Contents"
                        / "Resources"
                        / f"{icon_name_no_ext}.icns"
                    )

                if icon_file.exists():
                    self.output(f"Found icon file: {icon_file.name}")
                else:
                    icon_file = None

            # If CFBundleIconFile not found, try CFBundleIconName (modern asset catalog approach)
            if not icon_file:
                result = subprocess.run(
                    ["plutil", "-extract", "CFBundleIconName", "raw", str(info_plist)],
                    capture_output=True,
                    text=True,
                )

                if result.returncode == 0 and result.stdout.strip():
                    icon_name = result.stdout.strip()
                    self.output(
                        f"App uses asset catalog (CFBundleIconName: {icon_name}). Searching for icon..."
                    )
                    resources_dir = app_bundle / "Contents" / "Resources"

                    # First try: Look for .icns files in Resources
                    icns_files = list(resources_dir.glob("*.icns"))
                    if icns_files:
                        icon_file = icns_files[0]
                        self.output(f"Found icon file: {icon_file.name}")

                    # Second try: Use macOS icon services via Python/Cocoa to extract icon
                    if not icon_file:
                        self.output(
                            "No .icns file found. Attempting to extract icon using macOS icon services..."
                        )
                        temp_png = (
                            Path(tempfile.gettempdir()) / f"{app_bundle.stem}_icon.png"
                        )
                        try:
                            # Use Python with Cocoa (PyObjC) to get the app's icon
                            # This is available in macOS's system Python
                            import Cocoa

                            workspace = Cocoa.NSWorkspace.sharedWorkspace()
                            app_icon = workspace.iconForFile_(str(app_bundle))

                            if app_icon:
                                # Get the largest representation (usually 512x512 or 1024x1024)
                                tiff_data = app_icon.TIFFRepresentation()
                                bitmap_rep = Cocoa.NSBitmapImageRep.imageRepWithData_(
                                    tiff_data
                                )

                                # Convert to PNG
                                png_data = (
                                    bitmap_rep.representationUsingType_properties_(
                                        Cocoa.NSBitmapImageFileTypePNG, None
                                    )
                                )

                                # Write PNG file
                                png_data.writeToFile_atomically_(str(temp_png), True)

                                if temp_png.exists() and temp_png.stat().st_size > 0:
                                    icon_file = temp_png
                                    self.output(
                                        f"Successfully extracted icon using macOS icon services ({temp_png.stat().st_size} bytes)"
                                    )
                                else:
                                    self.output("Warning: Icon file created but empty")
                            else:
                                self.output(
                                    "Warning: Could not get app icon from macOS"
                                )

                        except ImportError:
                            self.output(
                                "Warning: PyObjC (Cocoa module) not available. Cannot extract icon from asset catalog."
                            )
                        except Exception as e:
                            self.output(f"Warning: Error extracting icon: {str(e)}")
                            if temp_png.exists():
                                temp_png.unlink()

                    if not icon_file:
                        self.output(
                            f"Warning: Could not find or extract icon for {app_bundle.name}"
                        )
                        return None
                else:
                    self.output(
                        f"Warning: Neither CFBundleIconFile nor CFBundleIconName found in Info.plist for {app_bundle.name}"
                    )
                    return None

            if not icon_file or not icon_file.exists():
                self.output(f"Warning: Icon file not found in {app_bundle.name}")
                return None

            # Convert .icns to PNG using sips (macOS built-in tool)
            output_png = temp_dir / "icon.png"
            result = subprocess.run(
                [
                    "sips",
                    "-s",
                    "format",
                    "png",
                    str(icon_file),
                    "--out",
                    str(output_png),
                ],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                self.output(f"Warning: Could not convert icon to PNG: {result.stderr}")
                return None

            if not output_png.exists():
                self.output("Warning: PNG conversion produced no output file")
                return None

            return output_png

        except Exception as e:
            self.output(f"Warning: Icon extraction from app bundle failed: {e}")
            return None

    def _compress_icon(self, icon_path: Path, temp_dir: Path) -> Path | None:
        """Compress a PNG icon to meet Fleet's 100 KB size limit.

        Uses sips to resize the icon progressively until it's under 100 KB.

        Args:
            icon_path: Path to original PNG icon
            temp_dir: Temporary directory for output

        Returns:
            Path to compressed PNG icon, or None if compression fails
        """
        try:
            # Try progressively smaller sizes: 512, 256, 128
            for size in [512, 256, 128]:
                compressed_path = temp_dir / f"icon_compressed_{size}.png"

                result = subprocess.run(
                    [
                        "sips",
                        "-Z",
                        str(size),
                        str(icon_path),
                        "--out",
                        str(compressed_path),
                    ],
                    capture_output=True,
                    text=True,
                )

                if result.returncode != 0:
                    continue

                if compressed_path.exists():
                    compressed_size = compressed_path.stat().st_size
                    if compressed_size <= 100 * 1024:  # Under 100 KB
                        self.output(
                            f"Compressed icon to {size}x{size}px ({compressed_size / 1024:.1f} KB)"
                        )
                        return compressed_path

            # If we get here, even 128px was too large - this is unusual
            self.output("Warning: Could not compress icon below 100 KB even at 128px")
            return None

        except Exception as e:
            self.output(f"Warning: Icon compression failed: {e}")
            return None

    def _extract_bundle_id_from_pkg(self, pkg_path: Path) -> str | None:
        """Extract bundle identifier from a package file.

        Args:
            pkg_path: Path to .pkg file

        Returns:
            Bundle identifier string, or None if extraction fails
        """
        temp_dir = None
        try:
            # Create temporary directory for extraction
            temp_dir = Path(tempfile.mkdtemp(prefix="fleetimporter-bundleid-"))

            # Expand the pkg to find the app bundle
            pkg_expand_dir = temp_dir / "pkg_contents"

            self.output(f"Extracting bundle ID from package: {pkg_path.name}")
            result = subprocess.run(
                ["pkgutil", "--expand-full", str(pkg_path), str(pkg_expand_dir)],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                self.output(
                    f"Warning: Could not expand package for bundle ID extraction: {result.stderr}"
                )
                shutil.rmtree(temp_dir, ignore_errors=True)
                return None

            # Find .app bundles within the expanded package
            app_bundles = list(pkg_expand_dir.rglob("*.app"))
            if not app_bundles:
                self.output(
                    "Warning: No .app bundle found in package for bundle ID extraction."
                )
                shutil.rmtree(temp_dir, ignore_errors=True)
                return None

            # Use the first app bundle found
            app_bundle = app_bundles[0]
            info_plist = app_bundle / "Contents" / "Info.plist"

            if not info_plist.exists():
                self.output(f"Warning: Info.plist not found in {app_bundle.name}")
                shutil.rmtree(temp_dir, ignore_errors=True)
                return None

            # Extract CFBundleIdentifier using PlistBuddy
            result = subprocess.run(
                [
                    "/usr/libexec/PlistBuddy",
                    "-c",
                    "Print :CFBundleIdentifier",
                    str(info_plist),
                ],
                capture_output=True,
                text=True,
            )

            # Clean up temp directory
            shutil.rmtree(temp_dir, ignore_errors=True)

            if result.returncode != 0:
                self.output(
                    f"Warning: Could not read CFBundleIdentifier from Info.plist: {result.stderr}"
                )
                return None

            bundle_id = result.stdout.strip()
            if not bundle_id:
                self.output("Warning: CFBundleIdentifier is empty in Info.plist")
                return None

            self.output(f"Extracted bundle identifier: {bundle_id}")
            return bundle_id

        except Exception as e:
            self.output(f"Warning: Bundle ID extraction failed with error: {e}")
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
            return None

    def _get_aws_credentials(self) -> tuple[str, str, str]:
        """Get AWS credentials from processor environment.

        Uses standard AutoPkg variable precedence: recipe arguments override
        AutoPkg preferences, which override defaults.

        Returns:
            Tuple of (access_key_id, secret_access_key, region)

        Raises:
            ProcessorError: If required credentials are missing
        """
        access_key = self.env.get("aws_access_key_id")
        secret_key = self.env.get("aws_secret_access_key")
        region = self.env.get("aws_default_region", "us-east-1")

        if not access_key or not secret_key:
            raise ProcessorError(
                "AWS credentials not found. Please provide aws_access_key_id and "
                "aws_secret_access_key as recipe arguments or set in AutoPkg preferences:\n"
                "  defaults write com.github.autopkg AWS_ACCESS_KEY_ID 'your-key'\n"
                "  defaults write com.github.autopkg AWS_SECRET_ACCESS_KEY 'your-secret'"
            )

        return access_key, secret_key, region

    def _get_s3_client(self):
        """Get configured boto3 S3 client.

        Returns:
            boto3 S3 client

        Raises:
            ProcessorError: If boto3 is not available or credentials are missing
        """
        if boto3 is None:
            raise ProcessorError(
                "boto3 is required for S3 operations but could not be imported or installed. "
                "Please install it manually: pip install boto3"
            )

        access_key, secret_key, region = self._get_aws_credentials()

        try:
            s3_client = boto3.client(
                "s3",
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name=region,
            )
            return s3_client
        except Exception as e:
            raise ProcessorError(f"Failed to create S3 client: {e}")

    def _upload_to_s3(
        self, bucket: str, software_title: str, version: str, pkg_path: Path
    ) -> tuple[str, bool]:
        """Upload package to S3 and return the S3 key.

        Args:
            bucket: S3 bucket name
            software_title: Software title for path construction
            version: Software version for path construction
            pkg_path: Path to the package file

        Returns:
            Tuple of (S3 key, was_uploaded: bool)
            - S3 key: path within bucket
            - was_uploaded: True if file was uploaded, False if it already existed

        Raises:
            ProcessorError: If upload fails
        """
        try:
            # Get S3 client
            s3_client = self._get_s3_client()

            # Use AutoPkg standard naming: software/Title/Title-Version.pkg
            extension = pkg_path.suffix
            s3_key = f"software/{software_title}/{software_title}-{version}{extension}"

            # Check if package already exists in S3
            try:
                head_response = s3_client.head_object(Bucket=bucket, Key=s3_key)
                # Package exists - verify it matches local file
                s3_etag = head_response.get("ETag", "").strip('"')
                s3_size = head_response.get("ContentLength", 0)
                local_size = pkg_path.stat().st_size

                if s3_size != local_size:
                    self.output(
                        f"Warning: S3 package size ({s3_size} bytes) differs from local file ({local_size} bytes). "
                        f"Re-uploading package."
                    )
                    # Continue to upload
                else:
                    self.output(
                        f"Package {software_title} {version} already exists in S3 at {s3_key}. "
                        f"Skipping upload (size: {s3_size} bytes, ETag: {s3_etag})."
                    )
                    return s3_key, False
            except ClientError as e:
                if e.response["Error"]["Code"] == "404":
                    self.output("Package not found in S3, proceeding with upload")
                else:
                    raise ProcessorError(f"S3 HEAD request failed: {e}")

            # Upload file to S3
            self.output(f"Uploading to s3://{bucket}/{s3_key}")
            s3_client.upload_file(
                str(pkg_path),
                bucket,
                s3_key,
                ExtraArgs={"ContentType": "application/octet-stream"},
            )
            self.output(f"Upload complete: s3://{bucket}/{s3_key}")
            return s3_key, True

        except NoCredentialsError:
            raise ProcessorError(
                "AWS credentials not found. Please configure AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY."
            )
        except ClientError as e:
            raise ProcessorError(f"S3 upload failed: {e}")
        except Exception as e:
            raise ProcessorError(f"S3 upload failed: {e}")

    def _construct_cloudfront_url(self, cloudfront_domain: str, s3_key: str) -> str:
        """Construct CloudFront URL from S3 key.

        Args:
            cloudfront_domain: CloudFront distribution domain
            s3_key: S3 key (path within bucket)

        Returns:
            Full CloudFront HTTPS URL
        """
        # Remove any leading/trailing slashes from domain
        domain = cloudfront_domain.strip("/")
        # Ensure s3_key doesn't start with /
        key = s3_key.lstrip("/")
        return f"https://{domain}/{key}"

    def _cleanup_old_s3_versions(
        self,
        bucket: str,
        software_title: str,
        current_version: str,
        retention_count: int,
    ):
        """Clean up old package versions in S3, keeping the N most recent.

        Args:
            bucket: S3 bucket name
            software_title: Software title
            current_version: Current version (just uploaded)
            retention_count: Number of versions to keep (0 means no pruning)

        Safety rules:
        - Never delete the only remaining version
        - Keep the N most recent versions based on version sort
        - If retention_count is 0, skip pruning entirely
        """
        # Skip pruning if retention_count is 0
        if retention_count <= 0:
            self.output("S3 version pruning disabled (retention_count <= 0)")
            return

        try:
            # Get S3 client
            s3_client = self._get_s3_client()
            prefix = f"software/{software_title}/"

            # List all objects for this software title
            response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)

            if "Contents" not in response:
                self.output(f"No existing versions found in S3 for {software_title}")
                return

            # Extract version information from S3 keys
            # Key format: software/Title/Title-Version.pkg
            versions = {}
            for obj in response["Contents"]:
                key = obj["Key"]
                # Extract version from filename pattern: Title-Version.pkg
                # Match: software/Title/Title-Version.ext
                match = re.search(rf"{re.escape(software_title)}-([^/]+)\.", key)
                if match:
                    ver = match.group(1)
                    if ver not in versions:
                        versions[ver] = []
                    versions[ver].append(key)

            self.output(
                f"Found {len(versions)} version(s) in S3: {list(versions.keys())}"
            )

            # Safety check: never delete if only one version exists
            if len(versions) <= 1:
                self.output("Only one version exists, skipping cleanup")
                return

            # Sort versions (semantic versioning)
            try:
                from packaging import version as pkg_version

                sorted_versions = sorted(
                    versions.keys(),
                    key=lambda v: pkg_version.parse(v),
                    reverse=True,
                )
            except Exception:
                # Fallback to string sort if packaging not available
                sorted_versions = sorted(versions.keys(), reverse=True)

            # Determine which versions to delete
            versions_to_keep = sorted_versions[:retention_count]
            versions_to_delete = [
                v for v in sorted_versions if v not in versions_to_keep
            ]

            if not versions_to_delete:
                self.output(
                    f"All versions within retention limit ({retention_count}), skipping cleanup"
                )
                return

            # Delete old versions
            for ver in versions_to_delete:
                for key in versions[ver]:
                    self.output(f"Deleting old version from S3: {key}")
                    try:
                        s3_client.delete_object(Bucket=bucket, Key=key)
                    except ClientError as e:
                        self.output(f"Warning: Failed to delete {key}: {e}")

            self.output(
                f"Cleanup complete. Kept versions: {versions_to_keep}, "
                f"Deleted versions: {versions_to_delete}"
            )

        except ClientError as e:
            # Log error but don't fail the entire workflow
            self.output(f"Warning: S3 cleanup failed: {e}")
        except Exception as e:
            # Log error but don't fail the entire workflow
            self.output(f"Warning: S3 cleanup failed: {e}")

    def _copy_icon_to_gitops_repo(
        self, repo_dir: str, icon_path_str: str, software_title: str
    ) -> str:
        """Copy icon file to GitOps repository under lib/icons.

        Args:
            repo_dir: Path to Git repository
            icon_path_str: Path to icon file (relative to recipe or absolute)
            software_title: Software title for naming

        Returns:
            Relative path from software YAML to icon (e.g., ../icons/claude.png)

        Raises:
            ProcessorError: If icon file not found or invalid
        """
        # Resolve icon path relative to recipe directory first
        icon_path = Path(icon_path_str)
        if not icon_path.is_absolute():
            # Get recipe directory from AutoPkg environment
            recipe_dir = self.env.get("RECIPE_DIR")
            if recipe_dir:
                icon_path = (Path(recipe_dir) / icon_path_str).resolve()
            else:
                icon_path = icon_path.expanduser().resolve()
        else:
            icon_path = icon_path.expanduser().resolve()

        if not icon_path.exists():
            raise ProcessorError(f"Icon file not found: {icon_path}")

        # Validate icon is PNG
        if icon_path.suffix.lower() != ".png":
            self.output(
                f"Warning: Icon file {icon_path.name} is not a PNG file. Fleet requires PNG format."
            )

        # Check file size (must be <= 100KB)
        icon_size_bytes = icon_path.stat().st_size
        icon_size_kb = icon_size_bytes / 1024
        if icon_size_bytes > 100 * 1024:  # 100KB in bytes
            raise ProcessorError(
                f"Icon file {icon_path.name} is too large ({icon_size_kb:.1f} KB). "
                f"Maximum allowed size is 100 KB. Please use a smaller icon file."
            )

        # Create icons directory in GitOps repo
        icons_dir = Path(repo_dir) / "lib" / "icons"
        icons_dir.mkdir(parents=True, exist_ok=True)

        # Use slugified software title for icon filename
        slug = self._slugify(software_title)
        icon_filename = f"{slug}.png"
        dest_icon_path = icons_dir / icon_filename

        # Copy icon to GitOps repo
        self.output(f"Copying icon to GitOps repo: lib/icons/{icon_filename}")
        shutil.copy2(icon_path, dest_icon_path)

        # Return relative path from lib/macos/software to lib/icons
        # From lib/macos/software/package.yml to lib/icons/icon.png = ../../icons/icon.png
        return f"../../icons/{icon_filename}"

    def _clone_gitops_repo(self, repo_url: str, github_token: str) -> str:
        """Clone GitOps repository to a temporary directory.

        Args:
            repo_url: Git repository URL
            github_token: GitHub personal access token

        Returns:
            Path to temporary directory containing cloned repo

        Raises:
            ProcessorError: If clone fails
        """
        temp_dir = tempfile.mkdtemp(prefix="fleetimporter-gitops-")
        askpass_script = None

        try:
            # Create a temporary GIT_ASKPASS script to provide credentials securely
            # This avoids embedding tokens in URLs where they could be logged
            askpass_fd, askpass_script = tempfile.mkstemp(
                prefix="git-askpass-", suffix=".sh", text=True
            )
            os.write(askpass_fd, f'#!/bin/sh\necho "{github_token}"\n'.encode())
            os.close(askpass_fd)
            os.chmod(askpass_script, 0o700)

            # Set up minimal environment for git clone
            git_env = {
                "GIT_ASKPASS": askpass_script,
                "GIT_TERMINAL_PROMPT": "0",
                "PATH": os.environ.get("PATH", ""),
                "HOME": os.environ.get("HOME", ""),
            }

            # Clone repository using GIT_ASKPASS for authentication
            subprocess.run(
                ["git", "clone", repo_url, temp_dir],
                check=True,
                capture_output=True,
                text=True,
                env=git_env,
            )
            return temp_dir
        except subprocess.CalledProcessError as e:
            # Clean up temp dir on failure
            if Path(temp_dir).exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
            raise ProcessorError(
                f"Failed to clone GitOps repository: {e.stderr or e.stdout}"
            )
        finally:
            # Clean up the askpass script
            if askpass_script and os.path.exists(askpass_script):
                try:
                    os.unlink(askpass_script)
                except Exception:
                    pass  # Best effort cleanup

    def _read_yaml(self, yaml_path: Path) -> dict:
        """Read and parse YAML file.

        Args:
            yaml_path: Path to YAML file

        Returns:
            Parsed YAML data as dict

        Raises:
            ProcessorError: If file cannot be read or parsed
        """
        try:
            if not yaml_path.exists():
                # Return empty structure if file doesn't exist
                return {"software": []}
            with open(yaml_path, "r") as f:
                data = yaml.safe_load(f) or {}
                # Ensure software array exists
                if "software" not in data:
                    data["software"] = []
                return data
        except (yaml.YAMLError, IOError) as e:
            raise ProcessorError(f"Failed to read YAML file {yaml_path}: {e}")

    def _write_yaml(self, yaml_path: Path, data: dict):
        """Write data to YAML file.

        Args:
            yaml_path: Path to YAML file
            data: Data to write

        Raises:
            ProcessorError: If file cannot be written
        """
        try:
            # Ensure parent directory exists
            yaml_path.parent.mkdir(parents=True, exist_ok=True)
            with open(yaml_path, "w") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False, indent=2)
        except (yaml.YAMLError, IOError) as e:
            raise ProcessorError(f"Failed to write YAML file {yaml_path}: {e}")

    def _create_software_package_yaml(
        self,
        repo_dir: str,
        software_dir: str,
        software_title: str,
        cloudfront_url: str,
        hash_sha256: str,
        install_script: str,
        uninstall_script: str,
        pre_install_query: str,
        post_install_script: str,
        icon_path: str = None,
        display_name: str = "",
    ) -> str:
        """Create software package YAML file in lib/ directory.

        Args:
            repo_dir: Path to Git repository
            software_dir: Directory for software YAMLs (e.g., lib/macos/software)
            software_title: Software title
            cloudfront_url: CloudFront URL for package
            hash_sha256: SHA-256 hash of package
            install_script: Custom install script
            uninstall_script: Custom uninstall script
            pre_install_query: Pre-install query
            post_install_script: Post-install script
            icon_path: Relative path to icon file in GitOps repo (e.g., ../icons/claude.png)
            display_name: Custom display name for the software in Fleet UI

        Returns:
            Relative path to created package YAML file (for use in team YAML)

        Raises:
            ProcessorError: If YAML creation fails
        """
        # Create slugified filename
        slug = self._slugify(software_title)
        package_filename = f"{slug}.yml"
        package_path = Path(repo_dir) / software_dir / package_filename

        # Build package entry (Fleet expects a list with single item)
        package_entry = {
            "url": cloudfront_url,
            "hash_sha256": hash_sha256,
        }

        # Add optional display name if provided
        if display_name:
            package_entry["display_name"] = display_name

        # Add optional icon path if provided
        if icon_path:
            package_entry["icon"] = {"path": icon_path}

        # Add optional script paths if provided
        if install_script:
            package_entry["install_script"] = {"path": install_script}
        if uninstall_script:
            package_entry["uninstall_script"] = {"path": uninstall_script}
        if pre_install_query:
            package_entry["pre_install_query"] = {"path": pre_install_query}
        if post_install_script:
            package_entry["post_install_script"] = {"path": post_install_script}

        # Package YAML is a list with single entry
        self._write_yaml(package_path, [package_entry])

        # Return relative path from team YAML to package YAML
        # E.g., if team YAML is teams/team-name.yml and package is lib/macos/software/chrome.yml
        # then relative path is ../lib/macos/software/chrome.yml
        return f"../{software_dir}/{package_filename}"

    def _update_team_yaml(
        self,
        team_yaml_path: Path,
        package_yaml_relative_path: str,
        software_title: str,
        self_service: bool,
        automatic_install: bool,
        labels_include_any: list,
        labels_exclude_any: list,
        categories: list,
    ):
        """Update team YAML file to include software package reference.

        Args:
            team_yaml_path: Path to team YAML file
            package_yaml_relative_path: Relative path to package YAML
            software_title: Software title (for logging)
            self_service: Self-service flag
            automatic_install: Automatic install flag (setup_experience in Fleet)
            labels_include_any: Include labels
            labels_exclude_any: Exclude labels
            categories: List of category names for grouping software

        Raises:
            ProcessorError: If YAML update fails
        """
        data = self._read_yaml(team_yaml_path)

        # Ensure software section exists
        if "software" not in data:
            data["software"] = {}
        if "packages" not in data["software"]:
            data["software"]["packages"] = []

        packages_list = data["software"]["packages"]

        # Find existing entry for this package path
        existing_entry = None
        for entry in packages_list:
            if entry.get("path") == package_yaml_relative_path:
                existing_entry = entry
                break

        # Build package reference entry
        new_entry = {
            "path": package_yaml_relative_path,
            "self_service": self_service,
        }

        # Add optional fields according to Fleet docs
        if categories:
            new_entry["categories"] = categories
        if automatic_install:
            new_entry["setup_experience"] = True
        if labels_include_any:
            new_entry["labels_include_any"] = labels_include_any
        if labels_exclude_any:
            new_entry["labels_exclude_any"] = labels_exclude_any

        if existing_entry:
            # Update existing entry
            self.output(f"Updating existing team entry for {software_title}")
            existing_entry.update(new_entry)
        else:
            # Add new entry
            self.output(f"Adding new team entry for {software_title}")
            packages_list.append(new_entry)

        data["software"]["packages"] = packages_list
        self._write_yaml(team_yaml_path, data)

    def _commit_and_push(
        self,
        repo_dir: str,
        branch_name: str,
        software_title: str,
        version: str,
        package_yaml_path: str,
        team_yaml_path: str,
        icon_path: str = None,
        policy_yaml_path: str = None,
    ):
        """Create Git branch, commit changes, and push to remote.

        Args:
            repo_dir: Path to Git repository
            branch_name: Name of branch to create
            software_title: Software title for commit message
            version: Software version for commit message
            package_yaml_path: Relative path to package YAML file
            team_yaml_path: Relative path to team YAML file
            icon_path: Optional relative path to icon file (e.g., ../../icons/claude.png)
            policy_yaml_path: Optional relative path to policy YAML file (e.g., lib/policies/chrome.yml)

        Raises:
            ProcessorError: If Git operations fail
        """
        try:
            # Use explicit allowlist of environment variables for Git operations
            # Only pass what Git actually needs, avoiding leakage of secrets
            git_env = {
                "GIT_TERMINAL_PROMPT": "0",
                "PATH": os.environ.get("PATH", ""),
                "HOME": os.environ.get("HOME", ""),
            }

            # Create and checkout new branch
            subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=repo_dir,
                check=True,
                capture_output=True,
                text=True,
                env=git_env,
            )

            # Stage YAML files and icon
            # Convert relative paths (with ../) to paths relative to repo root
            # package_yaml_path is like ../lib/macos/software/chrome.yml
            # team_yaml_path is like Path object to teams/team-name.yml
            pkg_file = package_yaml_path.replace("../", "")
            team_file = str(team_yaml_path.relative_to(repo_dir))

            files_to_add = [pkg_file, team_file]

            # Add icon file if provided
            if icon_path:
                # icon_path is like ../../icons/claude.png, need to convert to lib/icons/claude.png
                icon_file = icon_path.replace("../../", "lib/")
                files_to_add.append(icon_file)

            # Add policy file if provided
            if policy_yaml_path:
                # policy_yaml_path is already relative to repo root (e.g., lib/policies/chrome.yml)
                files_to_add.append(policy_yaml_path)

            subprocess.run(
                ["git", "add"] + files_to_add,
                cwd=repo_dir,
                check=True,
                capture_output=True,
                text=True,
                env=git_env,
            )

            # Commit
            commit_msg = f"Add {software_title} {version}"
            subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=repo_dir,
                check=True,
                capture_output=True,
                text=True,
                env=git_env,
            )

            # Push to remote
            subprocess.run(
                ["git", "push", "origin", branch_name],
                cwd=repo_dir,
                check=True,
                capture_output=True,
                text=True,
                env=git_env,
            )
        except subprocess.CalledProcessError as e:
            raise ProcessorError(f"Git operation failed: {e.stderr or e.stdout}")

    def _create_pull_request(
        self,
        repo_url: str,
        github_token: str,
        branch_name: str,
        software_title: str,
        version: str,
    ) -> str:
        """Create a pull request using GitHub API.

        Args:
            repo_url: Git repository URL
            github_token: GitHub personal access token
            branch_name: Name of branch to create PR from
            software_title: Software title for PR title
            version: Software version for PR title

        Returns:
            URL of created pull request

        Raises:
            ProcessorError: If PR creation fails
        """
        # Parse repository owner and name from URL
        # Expected format: https://github.com/owner/repo.git
        match = re.search(r"github\.com[:/]([^/]+)/([^/\.]+)", repo_url)
        if not match:
            raise ProcessorError(
                f"Could not parse GitHub repository from URL: {repo_url}"
            )

        owner = match.group(1)
        repo = match.group(2)

        # Construct PR details
        pr_title = f"Add {software_title} {version}"
        pr_body = f"""
## AutoPkg Package Upload

This PR adds a new version of {software_title}.

- **Version**: {version}
- **Source**: AutoPkg FleetImporter
- **Branch**: `{branch_name}`

### Changes
- Updated software definition in GitOps YAML
- Package uploaded to S3 and available via CloudFront

This PR was automatically generated by the FleetImporter AutoPkg processor.
""".strip()

        # Create PR using GitHub API
        api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
        headers = {
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        }
        data = {
            "title": pr_title,
            "body": pr_body,
            "head": branch_name,
            "base": "main",  # TODO: Make this configurable
        }

        try:
            req = urllib.request.Request(
                api_url,
                data=json.dumps(data).encode(),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(
                req, timeout=30, context=self._get_ssl_context()
            ) as resp:
                if resp.getcode() in (200, 201):
                    response_data = json.loads(resp.read().decode())
                    pr_url = response_data.get("html_url")
                    return pr_url
                else:
                    raise ProcessorError(
                        f"GitHub API returned unexpected status: {resp.getcode()}"
                    )
        except urllib.error.HTTPError as e:
            error_body = e.read().decode()
            raise ProcessorError(
                f"Failed to create pull request: {e.code} {error_body}"
            )
        except urllib.error.URLError as e:
            raise ProcessorError(f"Failed to connect to GitHub API: {e}")

    def _calculate_file_sha256(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of a file.

        Args:
            file_path: Path to the file to hash

        Returns:
            Lowercase hexadecimal SHA-256 hash string
        """
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            # Read in chunks to handle large files efficiently
            for chunk in iter(lambda: f.read(8192), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()

    def _calculate_s3_file_sha256(self, bucket: str, s3_key: str) -> str:
        """Calculate SHA-256 hash of a file in S3 by downloading it.

        Args:
            bucket: S3 bucket name
            s3_key: S3 key (path within bucket)

        Returns:
            Lowercase hexadecimal SHA-256 hash string

        Raises:
            ProcessorError: If download fails
        """
        try:
            s3_client = self._get_s3_client()

            # Download file in chunks and calculate hash
            sha256_hash = hashlib.sha256()
            response = s3_client.get_object(Bucket=bucket, Key=s3_key)

            # Read body in chunks
            for chunk in iter(lambda: response["Body"].read(8192), b""):
                sha256_hash.update(chunk)

            return sha256_hash.hexdigest()
        except ClientError as e:
            raise ProcessorError(
                f"Failed to download S3 file for hash calculation: {e}"
            )
        except Exception as e:
            raise ProcessorError(f"Failed to calculate S3 file hash: {e}")

    def _is_fleet_minimum_supported(self, fleet_version: str) -> bool:
        """Check if Fleet version meets minimum requirements."""
        try:
            # Parse version string like "4.70.0" or "4.70.0-dev"
            version_parts = fleet_version.split("-")[0].split(".")
            major = int(version_parts[0])
            minor = int(version_parts[1])
            patch = int(version_parts[2]) if len(version_parts) > 2 else 0

            # Parse minimum version from constant
            min_parts = FLEET_MINIMUM_VERSION.split(".")
            min_major = int(min_parts[0])
            min_minor = int(min_parts[1])
            min_patch = int(min_parts[2]) if len(min_parts) > 2 else 0

            # Check if >= minimum version
            if major > min_major:
                return True
            elif major == min_major and minor > min_minor:
                return True
            elif major == min_major and minor == min_minor and patch >= min_patch:
                return True
            return False
        except (ValueError, IndexError):
            # If we can't parse the version, assume it's supported to avoid blocking
            return True

    def _check_existing_package(
        self,
        fleet_api_base: str,
        fleet_token: str,
        team_id: int,
        software_title: str,
        version: str,
    ) -> dict | None:
        """Query Fleet API to check if a package version already exists.

        Returns a dict with package info if it exists, None otherwise.
        The dict includes: version, hash_sha256 if the version matches.

        The API response includes a versions array with all uploaded versions.
        We check if our version exists in that array.
        """
        try:
            # Search for the software title
            query_param = urllib.parse.quote(software_title)
            search_url = f"{fleet_api_base}/api/v1/fleet/software/titles?available_for_install=true&team_id={team_id}&query={query_param}"
            headers = {
                "Authorization": f"Bearer {fleet_token}",
                "Accept": "application/json",
            }
            req = urllib.request.Request(search_url, headers=headers)

            with urllib.request.urlopen(
                req, timeout=FLEET_VERSION_TIMEOUT, context=self._get_ssl_context()
            ) as resp:
                if resp.getcode() == 200:
                    data = json.loads(resp.read().decode())
                    software_titles = data.get("software_titles", [])

                    self.output(
                        f"Found {len(software_titles)} software title(s) matching '{software_title}'"
                    )

                    # Look for title match - try exact match first, then case-insensitive, then fuzzy
                    matching_title = None
                    for title in software_titles:
                        title_name = title.get("name", "")
                        # Exact match (preferred)
                        if title_name == software_title:
                            matching_title = title
                            self.output(
                                f"Found exact match for '{software_title}' (title_id: {title.get('id')})"
                            )
                            break
                        # Case-insensitive match as fallback
                        elif title_name.lower() == software_title.lower():
                            matching_title = title
                            self.output(
                                f"Found case-insensitive match: '{title_name}' for '{software_title}' (title_id: {title.get('id')})"
                            )
                            break

                    # If no exact match, try fuzzy matching (e.g., "Zoom" matches "zoom.us", "Caffeine" matches "Caffeine.app")
                    if not matching_title and software_titles:
                        for title in software_titles:
                            title_name = title.get("name", "")
                            # Check if search term is contained in title name or vice versa (case-insensitive)
                            search_lower = software_title.lower()
                            title_lower = title_name.lower()
                            if (
                                search_lower in title_lower
                                or title_lower in search_lower
                            ):
                                matching_title = title
                                self.output(
                                    f"Found fuzzy match: '{title_name}' for '{software_title}' (title_id: {title.get('id')})"
                                )
                                break

                    if not matching_title:
                        # No exact or case-insensitive match - log what we found for debugging
                        if software_titles:
                            for title in software_titles:
                                self.output(
                                    f"No match found - searched for '{software_title}', found '{title.get('name', '')}'"
                                )
                        return None

                    # Check if our version exists in the versions array
                    versions = matching_title.get("versions", [])
                    if versions:
                        self.output(
                            f"Checking {len(versions)} version(s) for '{matching_title.get('name')}'"
                        )
                        for idx, ver in enumerate(versions):
                            # Debug: show what fields are in the version object
                            if isinstance(ver, dict):
                                ver_string = ver.get("version", "")
                                self.output(
                                    f"  Version {idx + 1}: '{ver_string}' (fields: {list(ver.keys())})"
                                )
                            elif isinstance(ver, str):
                                # Sometimes versions might be returned as strings directly
                                ver_string = ver
                                self.output(
                                    f"  Version {idx + 1}: '{ver_string}' (string)"
                                )
                            else:
                                self.output(
                                    f"  Version {idx + 1}: unexpected type {type(ver)}"
                                )
                                continue

                            if ver_string == version:
                                # Hash is at the title level, not version level
                                hash_sha256 = matching_title.get("hash_sha256")
                                title_id = matching_title.get("id")
                                self.output(
                                    f"Package {software_title} {version} already exists in Fleet (hash: {hash_sha256[:16] + '...' if hash_sha256 else 'none'})"
                                )
                                return {
                                    "version": ver_string,
                                    "hash_sha256": hash_sha256,
                                    "package_name": software_title,
                                    "title_id": title_id,
                                }

                    # Check the currently available software_package as well
                    sw_package = matching_title.get("software_package")
                    if sw_package:
                        pkg_version = sw_package.get("version", "")
                        if pkg_version == version:
                            hash_sha256 = matching_title.get("hash_sha256")
                            title_id = matching_title.get("id")
                            self.output(
                                f"Package {software_title} {version} already exists in Fleet as current package (hash: {hash_sha256[:16] + '...' if hash_sha256 else 'none'})"
                            )
                            return {
                                "version": pkg_version,
                                "hash_sha256": hash_sha256,
                                "package_name": sw_package.get("name", software_title),
                                "title_id": title_id,
                            }

                    # Version not found in this title
                    self.output(
                        f"Version {version} not found for '{matching_title.get('name')}'"
                    )

        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            json.JSONDecodeError,
            KeyError,
        ) as e:
            # If query fails, log and continue with upload
            self.output(f"Warning: Could not check for existing package: {e}")

        return None

    def _get_fleet_version(self, fleet_api_base: str, fleet_token: str) -> str:
        """Query Fleet API to get the server version.

        Returns the semantic version string (e.g., "4.74.0").
        If the query fails, defaults to "4.74.0" (minimum supported) assuming a modern deployment.
        """
        try:
            url = f"{fleet_api_base}/api/v1/fleet/version"
            headers = {
                "Authorization": f"Bearer {fleet_token}",
                "Accept": "application/json",
            }
            req = urllib.request.Request(url, headers=headers)

            with urllib.request.urlopen(
                req, timeout=FLEET_VERSION_TIMEOUT, context=self._get_ssl_context()
            ) as resp:
                if resp.getcode() == 200:
                    data = json.loads(resp.read().decode())
                    version = data.get("version", "")
                    if version:
                        # Parse version string like "4.74.0-dev", "4.74.0", or "0.0.0-SNAPSHOT"
                        # Extract just the semantic version part
                        base_version = version.split("-")[0]
                        # If version is 0.0.0, it's a snapshot/development build
                        # Treat it as meeting minimum version requirements
                        if base_version == "0.0.0":
                            self.output(
                                f"Detected Fleet snapshot build: {version}. "
                                "Assuming compatibility with minimum version requirements."
                            )
                            return FLEET_MINIMUM_VERSION
                        return base_version

        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            json.JSONDecodeError,
            KeyError,
        ):
            # If we can't get the version, assume minimum supported version for modern deployments
            pass

        # Default to minimum supported version if query fails (assume modern Fleet deployment)
        return FLEET_MINIMUM_VERSION

    def _fleet_upload_package(
        self,
        base_url,
        token,
        pkg_path: Path,
        software_title: str,
        version: str,
        team_id: int,
        self_service: bool,
        automatic_install: bool,
        labels_include_any: list[str],
        labels_exclude_any: list[str],
        install_script: str,
        uninstall_script: str,
        pre_install_query: str,
        post_install_script: str,
        categories: list[str],
        display_name: str = "",
    ) -> dict:
        url = f"{base_url}/api/v1/fleet/software/package"
        self.output(f"Uploading file to Fleet: {pkg_path}")
        # API rules: only one of include/exclude
        if labels_include_any and labels_exclude_any:
            raise ProcessorError(
                "Only one of labels_include_any or labels_exclude_any may be specified."
            )

        boundary = "----FleetUploadBoundary" + hashlib.sha1(os.urandom(16)).hexdigest()
        body = io.BytesIO()

        def write_field(name: str, value: str):
            body.write(f"--{boundary}\r\n".encode())
            body.write(
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
            )
            body.write(str(value).encode())
            body.write(b"\r\n")

        def write_file(name: str, filename: str, path: Path):
            body.write(f"--{boundary}\r\n".encode())
            body.write(
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode()
            )
            body.write(b"Content-Type: application/octet-stream\r\n\r\n")
            with open(path, "rb") as f:
                shutil.copyfileobj(f, body)
            body.write(b"\r\n")

        write_field("team_id", str(team_id))
        write_field("self_service", json.dumps(bool(self_service)).lower())
        write_field("display_name", display_name)
        if install_script:
            write_field("install_script", install_script)
        if uninstall_script:
            write_field("uninstall_script", uninstall_script)
        if pre_install_query:
            write_field("pre_install_query", pre_install_query)
        if post_install_script:
            write_field("post_install_script", post_install_script)
        if automatic_install:
            write_field("automatic_install", "true")

        for label in labels_include_any:
            write_field("labels_include_any", label)
        for label in labels_exclude_any:
            write_field("labels_exclude_any", label)
        for category in categories:
            write_field("categories", category)

        write_file("software", pkg_path.name, pkg_path)
        body.write(f"--{boundary}--\r\n".encode())

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        }
        req = urllib.request.Request(url, data=body.getvalue(), headers=headers)
        try:
            with urllib.request.urlopen(
                req, timeout=FLEET_UPLOAD_TIMEOUT, context=self._get_ssl_context()
            ) as resp:
                resp_body = resp.read()
                status = resp.getcode()
        except urllib.error.HTTPError as e:
            if e.code == 409:
                # Package already exists in Fleet - return special marker for graceful exit
                self.output(
                    "Package already exists in Fleet (409 Conflict). Exiting gracefully."
                )
                return {"package_exists": True}
            raise ProcessorError(f"Fleet upload failed: {e.code} {e.read().decode()}")
        if status != 200:
            raise ProcessorError(f"Fleet upload failed: {status} {resp_body.decode()}")
        return json.loads(resp_body or b"{}")

    def _fleet_upload_icon(
        self, base_url: str, token: str, title_id: int, team_id: int, icon_path: Path
    ) -> None:
        """
        Upload a software icon to Fleet with retry logic for race condition errors.

        Fleet has a known issue (#33917, #34281, #36090) where icon uploads can fail
        with "500 sql: no rows in result set" due to a race condition in activity
        logging. The icon usually uploads successfully despite the error, but the
        activity feed entry fails. Retrying after a brief delay typically succeeds.

        Args:
            base_url: Fleet base URL
            token: Fleet API token
            title_id: Software title ID from package upload
            team_id: Team ID for the icon
            icon_path: Path to PNG icon file (square, 120x120 to 1024x1024 px)
        """
        url = (
            f"{base_url}/api/v1/fleet/software/titles/{title_id}/icon?team_id={team_id}"
        )
        self.output(f"Uploading icon to Fleet: {icon_path}")

        # Validate icon file exists and is PNG
        if not icon_path.exists():
            raise ProcessorError(f"Icon file not found: {icon_path}")

        # Check file extension
        if icon_path.suffix.lower() != ".png":
            self.output(
                f"Warning: Icon file {icon_path.name} is not a PNG file. Fleet requires PNG format."
            )

        # Check file size (must be <= 100KB)
        icon_size_bytes = icon_path.stat().st_size
        icon_size_kb = icon_size_bytes / 1024
        if icon_size_bytes > 100 * 1024:  # 100KB in bytes
            raise ProcessorError(
                f"Icon file {icon_path.name} is too large ({icon_size_kb:.1f} KB). "
                f"Maximum allowed size is 100 KB. Please use a smaller icon file."
            )

        boundary = (
            "----FleetIconUploadBoundary" + hashlib.sha1(os.urandom(16)).hexdigest()
        )
        body = io.BytesIO()

        # Write the icon file
        body.write(f"--{boundary}\r\n".encode())
        body.write(
            f'Content-Disposition: form-data; name="icon"; filename="{icon_path.name}"\r\n'.encode()
        )
        body.write(b"Content-Type: image/png\r\n\r\n")
        with open(icon_path, "rb") as f:
            shutil.copyfileobj(f, body)
        body.write(b"\r\n")
        body.write(f"--{boundary}--\r\n".encode())

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        }

        # Retry logic to work around Fleet race condition bug
        max_retries = 3
        retry_delays = [2, 4, 8]  # Exponential backoff: 2s, 4s, 8s

        last_error = None
        for attempt in range(max_retries):
            if attempt > 0:
                delay = retry_delays[attempt - 1]
                self.output(
                    f"Retrying icon upload after {delay}s delay (attempt {attempt + 1}/{max_retries})..."
                )
                time.sleep(delay)

            req = urllib.request.Request(
                url, data=body.getvalue(), headers=headers, method="PUT"
            )

            try:
                with urllib.request.urlopen(
                    req, timeout=FLEET_VERSION_TIMEOUT, context=self._get_ssl_context()
                ) as resp:
                    status = resp.getcode()

                if status != 200:
                    last_error = f"Fleet icon upload failed with status: {status}"
                    continue

                self.output(
                    f"Icon uploaded successfully for software title ID: {title_id}"
                )
                return  # Success!

            except urllib.error.HTTPError as e:
                error_body = e.read().decode()
                # Check if this is the known race condition error
                if e.code == 500 and "sql: no rows in result set" in error_body:
                    last_error = f"Fleet race condition error (known bug): {error_body}"
                    self.output(
                        f"Encountered Fleet race condition bug on attempt {attempt + 1}/{max_retries}"
                    )
                    continue  # Retry
                else:
                    # Different error - don't retry
                    raise ProcessorError(
                        f"Fleet icon upload failed: {e.code} {error_body}"
                    )

        # All retries exhausted
        raise ProcessorError(
            f"Fleet icon upload failed after {max_retries} attempts. Last error: {last_error}"
        )


if __name__ == "__main__":
    PROCESSOR = FleetImporter()
    PROCESSOR.execute_shell()
