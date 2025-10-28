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
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml
from autopkglib import Processor, ProcessorError

# Try to import boto3 for S3 operations (optional dependency)
try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False
    boto3 = None
    BotoCoreError = Exception
    ClientError = Exception

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
            "default": 3,
            "description": "Number of old versions to retain per software title in S3 (default: 3).",
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
            "description": "Custom install script body (string).",
        },
        "uninstall_script": {
            "required": False,
            "default": "",
            "description": "Custom uninstall script body (string).",
        },
        "pre_install_query": {
            "required": False,
            "default": "",
            "description": "Pre-install osquery SQL condition.",
        },
        "post_install_script": {
            "required": False,
            "default": "",
            "description": "Post-install script body (string).",
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

        fleet_api_base = self.env["fleet_api_base"].rstrip("/")
        fleet_token = self.env["fleet_api_token"]
        team_id = int(self.env["team_id"])

        # Fleet deployment options
        self_service = bool(self.env.get("self_service", False))
        automatic_install = bool(self.env.get("automatic_install", False))
        labels_include_any = list(self.env.get("labels_include_any", []))
        labels_exclude_any = list(self.env.get("labels_exclude_any", []))
        install_script = self.env.get("install_script", "")
        uninstall_script = self.env.get("uninstall_script", "")
        pre_install_query = self.env.get("pre_install_query", "")
        post_install_script = self.env.get("post_install_script", "")

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
            self.env["fleet_title_id"] = None
            self.env["fleet_installer_id"] = None
            self.env["hash_sha256"] = hash_sha256
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

    def _run_gitops_workflow(self):
        """Run the GitOps workflow: upload to S3, update YAML, create PR."""
        # Check for boto3
        if not HAS_BOTO3:
            raise ProcessorError(
                "GitOps mode requires boto3. Install with: pip install boto3"
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
        s3_retention_versions = int(self.env.get("s3_retention_versions", 3))

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
        install_script = self.env.get("install_script", "")
        uninstall_script = self.env.get("uninstall_script", "")
        pre_install_query = self.env.get("pre_install_query", "")
        post_install_script = self.env.get("post_install_script", "")

        # Calculate SHA-256 hash before uploading
        self.output(f"Calculating SHA-256 hash for {pkg_path.name}...")
        hash_sha256 = self._calculate_file_sha256(pkg_path)
        self.output(f"SHA-256: {hash_sha256}")

        # Clone GitOps repository first (fail early if this doesn't work)
        self.output(f"Cloning GitOps repository: {gitops_repo_url}")
        temp_dir = None
        try:
            temp_dir = self._clone_gitops_repo(gitops_repo_url, github_token)
            self.output(f"Repository cloned to: {temp_dir}")

            # Upload package to S3
            self.output(f"Uploading package to S3 bucket: {aws_s3_bucket}")
            s3_key = self._upload_to_s3(
                aws_s3_bucket, software_title, version, pkg_path
            )
            self.output(f"Package uploaded to S3: {s3_key}")

            # Construct CloudFront URL
            cloudfront_url = self._construct_cloudfront_url(
                aws_cloudfront_domain, s3_key
            )
            self.output(f"CloudFront URL: {cloudfront_url}")
            self.env["cloudfront_url"] = cloudfront_url
            self.env["hash_sha256"] = hash_sha256

            # Clean up old versions in S3
            self.output(
                f"Cleaning up old S3 versions (retaining {s3_retention_versions} most recent)..."
            )
            self._cleanup_old_s3_versions(
                aws_s3_bucket, software_title, version, s3_retention_versions
            )

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
            # Always clean up temporary directory
            if temp_dir and Path(temp_dir).exists():
                self.output(f"Cleaning up temporary directory: {temp_dir}")
                shutil.rmtree(temp_dir, ignore_errors=True)

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

    def _upload_to_s3(
        self, bucket: str, software_title: str, version: str, pkg_path: Path
    ) -> str:
        """Upload package to S3 and return the S3 key.

        Args:
            bucket: S3 bucket name
            software_title: Software title for path construction
            version: Software version for path construction
            pkg_path: Path to the package file

        Returns:
            S3 key (path within bucket)

        Raises:
            ProcessorError: If upload fails
        """
        try:
            s3_client = boto3.client("s3")
            # Use AutoPkg standard naming: software/Title/Title-Version.pkg
            extension = pkg_path.suffix
            s3_key = f"software/{software_title}/{software_title}-{version}{extension}"

            # Check if package already exists in S3
            try:
                s3_client.head_object(Bucket=bucket, Key=s3_key)
                self.output(
                    f"Package {software_title} {version} already exists in S3 at {s3_key}. Skipping upload."
                )
                return s3_key
            except ClientError as e:
                # 404 means object doesn't exist, which is expected for new packages
                if e.response["Error"]["Code"] == "404":
                    self.output("Package not found in S3, proceeding with upload")
                else:
                    # Some other error occurred
                    raise

            self.output(f"Uploading to s3://{bucket}/{s3_key}")
            s3_client.upload_file(str(pkg_path), bucket, s3_key)
            self.output(f"Upload complete: s3://{bucket}/{s3_key}")
            return s3_key
        except (ClientError, BotoCoreError) as e:
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
            retention_count: Number of versions to keep

        Safety rules:
        - Never delete the only remaining version
        - Keep the N most recent versions based on version sort
        """
        try:
            s3_client = boto3.client("s3")
            prefix = f"software/{software_title}/"

            # List all objects for this software title
            response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
            if "Contents" not in response:
                self.output(f"No existing versions found in S3 for {software_title}")
                return

            # Extract version information from S3 keys
            # Key format: software/Title/Title-Version.pkg
            # Parse version from filename
            import re

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
                    s3_client.delete_object(Bucket=bucket, Key=key)

            self.output(
                f"Cleanup complete. Kept versions: {versions_to_keep}, "
                f"Deleted versions: {versions_to_delete}"
            )

        except (ClientError, BotoCoreError) as e:
            # Log error but don't fail the entire workflow
            self.output(f"Warning: S3 cleanup failed: {e}")

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

        # Inject token into HTTPS URL for authentication
        if repo_url.startswith("https://github.com/"):
            auth_url = repo_url.replace(
                "https://github.com/", f"https://{github_token}@github.com/"
            )
        else:
            # Assume token can be used as-is
            auth_url = repo_url

        try:
            # Clone repository
            subprocess.run(
                ["git", "clone", auth_url, temp_dir],
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
            return temp_dir
        except subprocess.CalledProcessError as e:
            # Clean up temp dir on failure
            if Path(temp_dir).exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
            raise ProcessorError(
                f"Failed to clone GitOps repository: {e.stderr or e.stdout}"
            )

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
    ):
        """Create Git branch, commit changes, and push to remote.

        Args:
            repo_dir: Path to Git repository
            branch_name: Name of branch to create
            software_title: Software title for commit message
            version: Software version for commit message
            package_yaml_path: Relative path to package YAML file
            team_yaml_path: Relative path to team YAML file

        Raises:
            ProcessorError: If Git operations fail
        """
        try:
            git_env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}

            # Create and checkout new branch
            subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=repo_dir,
                check=True,
                capture_output=True,
                text=True,
                env=git_env,
            )

            # Stage both YAML files
            # Convert relative paths (with ../) to paths relative to repo root
            # package_yaml_path is like ../lib/macos/software/chrome.yml
            # team_yaml_path is like Path object to teams/team-name.yml
            pkg_file = package_yaml_path.replace("../", "")
            team_file = str(team_yaml_path.relative_to(repo_dir))

            subprocess.run(
                ["git", "add", pkg_file, team_file],
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
            with urllib.request.urlopen(req, timeout=30) as resp:
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

            with urllib.request.urlopen(req, timeout=FLEET_VERSION_TIMEOUT) as resp:
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
                                self.output(
                                    f"Package {software_title} {version} already exists in Fleet (hash: {hash_sha256[:16] + '...' if hash_sha256 else 'none'})"
                                )
                                return {
                                    "version": ver_string,
                                    "hash_sha256": hash_sha256,
                                    "package_name": software_title,
                                }

                    # Check the currently available software_package as well
                    sw_package = matching_title.get("software_package")
                    if sw_package:
                        pkg_version = sw_package.get("version", "")
                        if pkg_version == version:
                            hash_sha256 = matching_title.get("hash_sha256")
                            self.output(
                                f"Package {software_title} {version} already exists in Fleet as current package (hash: {hash_sha256[:16] + '...' if hash_sha256 else 'none'})"
                            )
                            return {
                                "version": pkg_version,
                                "hash_sha256": hash_sha256,
                                "package_name": sw_package.get("name", software_title),
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

            with urllib.request.urlopen(req, timeout=FLEET_VERSION_TIMEOUT) as resp:
                if resp.getcode() == 200:
                    data = json.loads(resp.read().decode())
                    version = data.get("version", "")
                    if version:
                        # Parse version string like "4.74.0-dev" or "4.74.0"
                        # Extract just the semantic version part
                        return version.split("-")[0]

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

        write_file("software", pkg_path.name, pkg_path)
        body.write(f"--{boundary}--\r\n".encode())

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        }
        req = urllib.request.Request(url, data=body.getvalue(), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=FLEET_UPLOAD_TIMEOUT) as resp:
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
