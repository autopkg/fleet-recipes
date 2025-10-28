# FleetImporter AutoPkg Processor

Upload freshly built installers to Fleet using the Software API. This processor is designed for CI use in GitHub Actions and can also be run locally.

> **⚠️ Experimental:** This processor uses Fleet's [experimental software management API](https://fleetdm.com/docs/rest-api/rest-api#list-software), which is subject to breaking changes. Fleet may introduce API changes that require corresponding updates to this processor. **Production use is not recommended** due to the experimental nature of the underlying Fleet API.

---

## Features

- Uploads `.pkg` files to Fleet for specific teams
- Configures software deployment settings via Fleet API:
  - Self-service availability
  - Automatic installation policies
  - Host targeting via labels (include/exclude)
  - Custom install/uninstall/pre-install/post-install scripts
- Detects and skips duplicate package uploads
- Idempotent where practical and fails loudly on API errors
- Compatible with AutoPkg's YAML recipe format

---

## Requirements

- **macOS**: Required for AutoPkg execution
- **Python 3.9+**: For the FleetImporter processor
- **AutoPkg 2.7+**: For recipe processing
- **Fleet API Access**: Fleet server v4.74.0+ with software management permissions

---

## Why YAML?

AutoPkg [supports both XML (plist) and YAML recipe formats](https://github.com/autopkg/autopkg/wiki/Recipe-Format#overview). I personally find YAML more readable and maintainable than XML, especially for recipes that may be edited by hand or reviewed in code. YAML's indentation and lack of angle brackets make it easier to scan and less error-prone for most users.

---

## Installation

### 1. Install AutoPkg

```bash
# Using Homebrew (recommended)
brew install autopkg

# Verify installation
autopkg version
```

### 2. Add Recipe Repositories

```bash
# Add common AutoPkg recipe repos
autopkg repo-add https://github.com/autopkg/recipes.git
autopkg repo-add https://github.com/autopkg/homebysix-recipes.git

# Add this repo for FleetImporter processor
autopkg repo-add https://github.com/kitzy/fleetimporter.git
```

### 3. Configure Environment Variables

You can configure Fleet API credentials in two ways:

**Option A: Environment Variables (for CI/CD)**

```bash
export FLEET_API_BASE="https://fleet.example.com"
export FLEET_API_TOKEN="your-fleet-api-token"
export FLEET_TEAM_ID="1"
```

**Option B: AutoPkg Preferences (for local use)**

Set preferences in AutoPkg's plist file:

```bash
# Set Fleet API credentials
defaults write com.github.autopkg FLEET_API_BASE "https://fleet.example.com"
defaults write com.github.autopkg FLEET_API_TOKEN "your-fleet-api-token"
defaults write com.github.autopkg FLEET_TEAM_ID "1"

# Verify settings
defaults read com.github.autopkg FLEET_API_BASE
defaults read com.github.autopkg FLEET_API_TOKEN
defaults read com.github.autopkg FLEET_TEAM_ID
```

This stores the values in `~/Library/Preferences/com.github.autopkg.plist` so you don't need to export environment variables for each terminal session.

---

## Usage

### Basic Recipe Example

Here's a minimal recipe that downloads and uploads Google Chrome to Fleet:

```yaml
Description: 'Builds GoogleChrome.pkg and uploads to Fleet'
Identifier: com.github.kitzy.fleet.GoogleChrome
Input:
  NAME: Google Chrome
MinimumVersion: '2.0'
ParentRecipe: com.github.autopkg.pkg.googlechrome
Process:
- Arguments:
    pkg_path: '%pkg_path%'
    software_title: '%NAME%'
    version: '%version%'
    fleet_api_base: '%FLEET_API_BASE%'
    fleet_api_token: '%FLEET_API_TOKEN%'
    team_id: '%FLEET_TEAM_ID%'
    self_service: true
  Processor: FleetImporter
```

### Running a Recipe

```bash
# Run a single recipe
autopkg run GoogleChrome.fleet.recipe.yaml

# Run with verbose output
autopkg run -v GoogleChrome.fleet.recipe.yaml

# Override variables
autopkg run GoogleChrome.fleet.recipe.yaml \
  -k FLEET_API_BASE="https://fleet.example.com" \
  -k FLEET_API_TOKEN="your-token" \
  -k FLEET_TEAM_ID="1"
```

---

## GitOps Mode

FleetImporter supports GitOps mode as an alternative to direct Fleet API uploads. In GitOps mode, packages are uploaded to S3 and made available via CloudFront, and a pull request is automatically created in your GitOps repository with the software definition.

### Why GitOps Mode?

GitOps mode provides a workaround for [Fleet issue #34137](https://github.com/fleetdm/fleet/issues/34137), where Fleet's GitOps synchronization deletes newly uploaded packages before their corresponding PRs are merged. By uploading to S3 and defining the software in YAML from the start, the package is never deleted by Fleet's GitOps sync.

### Requirements for GitOps Mode

**Additional Dependencies:**
```bash
# Install PyYAML for YAML file manipulation (if not already installed)
pip install PyYAML

# Verify AWS credentials are configured
aws configure list

# Or set AWS credentials via environment variables
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_DEFAULT_REGION="us-east-1"
```

> **Note:** GitOps mode uses the AWS S3 REST API with Signature Version 4 authentication, which only requires the `requests` library (already included with AutoPkg). No additional AWS SDK dependencies like boto3 are needed.

**AWS Permissions Required:**
- `s3:PutObject` - Upload new packages
- `s3:ListBucket` - List existing versions for cleanup
- `s3:DeleteObject` - Remove old versions based on retention policy

**Example IAM Policy:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "FleetPackageManagement",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::my-fleet-packages/software/*"
    },
    {
      "Sid": "FleetPackageList",
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket"
      ],
      "Resource": "arn:aws:s3:::my-fleet-packages",
      "Condition": {
        "StringLike": {
          "s3:prefix": "software/*"
        }
      }
    }
  ]
}
```

Replace `my-fleet-packages` with your actual bucket name. This policy grants access only to objects within the `software/` prefix - the processor will automatically create this path structure when uploading packages (S3 doesn't require pre-existing directories).

**GitHub Permissions Required:**
- GitHub personal access token with `repo` scope
- Write access to the GitOps repository

### GitOps Mode Environment Variables

```bash
# AWS S3 and CloudFront
export AWS_S3_BUCKET="my-fleet-packages"
export AWS_CLOUDFRONT_DOMAIN="cdn.example.com"

# GitOps repository
export FLEET_GITOPS_REPO_URL="https://github.com/org/fleet-gitops.git"
export FLEET_GITOPS_SOFTWARE_DIR="lib/macos/software"  # Default, can be omitted
export FLEET_GITOPS_TEAM_YAML_PATH="teams/team-name.yml"

# GitHub authentication
export FLEET_GITOPS_GITHUB_TOKEN="your-github-token"
```

### GitOps Recipe Example

```yaml
Description: 'Builds GoogleChrome.pkg, uploads to S3, and creates GitOps PR'
Identifier: com.github.kitzy.fleet.gitops.GoogleChrome
Input:
  NAME: Google Chrome
  FLEET_GITOPS_SOFTWARE_DIR: lib/macos/software
  FLEET_GITOPS_TEAM_YAML_PATH: teams/workstations.yml
MinimumVersion: '2.0'
ParentRecipe: com.github.autopkg.pkg.googlechrome
Process:
- Arguments:
    pkg_path: '%pkg_path%'
    software_title: '%NAME%'
    version: '%version%'
    gitops_mode: true
    aws_s3_bucket: '%AWS_S3_BUCKET%'
    aws_cloudfront_domain: '%AWS_CLOUDFRONT_DOMAIN%'
    gitops_repo_url: '%FLEET_GITOPS_REPO_URL%'
    gitops_software_dir: '%FLEET_GITOPS_SOFTWARE_DIR%'
    gitops_team_yaml_path: '%FLEET_GITOPS_TEAM_YAML_PATH%'
    github_token: '%FLEET_GITOPS_GITHUB_TOKEN%'
    s3_retention_versions: 3
    self_service: true
    labels_include_any:
      - workstations
  Processor: FleetImporter
```

This makes it easy to override the paths when running recipes:
```bash
autopkg run GoogleChrome.fleet.gitops.recipe.yaml \
  -k FLEET_GITOPS_TEAM_YAML_PATH="teams/engineering.yml"
```

### GitOps Mode Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `gitops_mode` | No | `false` | Enable GitOps mode (S3 upload + PR creation) |
| `aws_s3_bucket` | Yes* | - | S3 bucket name for package storage |
| `aws_cloudfront_domain` | Yes* | - | CloudFront distribution domain (e.g., cdn.example.com) |
| `gitops_repo_url` | Yes* | - | GitOps repository URL |
| `gitops_software_dir` | No | `lib/macos/software` | Directory for package YAMLs within GitOps repo |
| `gitops_team_yaml_path` | Yes* | - | Path to team YAML file (e.g., teams/team-name.yml) |
| `github_token` | Yes* | - | GitHub personal access token |
| `s3_retention_versions` | No | `3` | Number of old versions to retain per software title |

*Required when `gitops_mode` is `true`

### GitOps Mode Output Variables

| Variable | Description |
|----------|-------------|
| `cloudfront_url` | CloudFront URL for the uploaded package |
| `pull_request_url` | URL of the created pull request |
| `git_branch` | Name of the Git branch created for the PR |
| `hash_sha256` | SHA-256 hash of uploaded package |

### GitOps Workflow

1. **Calculate package hash**: SHA-256 hash is calculated for the package
2. **Clone GitOps repository**: Repository is cloned to a temporary directory
3. **Check S3 for existing package**: Checks if package with same title and version already exists
4. **Upload to S3**: Package is uploaded to `s3://bucket/software/<Title>/<Title>-<Version>.pkg` (skipped if already exists)
5. **Construct CloudFront URL**: URL is generated from S3 path and CloudFront domain
6. **Create package YAML**: Software package YAML file is created in `lib/macos/software/<slug>.yml` with URL and hash
7. **Update team YAML**: Team YAML file (e.g., `teams/team-name.yml`) is updated to reference the package
8. **Create Git branch**: Branch is created with format `autopkg/<software-slug>-<version>`
9. **Commit and push**: Both YAML files are committed and pushed to the remote repository
10. **Create pull request**: PR is created via GitHub API
11. **Clean up S3**: Old package versions are deleted based on retention policy
12. **Clean up temp directory**: Temporary clone is removed

**Note**: The processor detects duplicate packages in S3 by filename (title + version) and skips re-uploading if the package already exists. This makes the workflow idempotent and avoids unnecessary S3 uploads. The YAML update and PR creation still proceed even if the package exists, allowing recipe configuration changes to be deployed.

### GitOps Repository Structure

The processor creates/updates files following Fleet's [GitOps YAML structure](https://fleetdm.com/docs/configuration/yaml-files#software):

```
fleet-gitops/
├── lib/
│   └── macos/
│       └── software/
│           ├── google-chrome.yml      # Package definition (URL, hash, scripts)
│           └── firefox.yml
└── teams/
    ├── workstations.yml               # Team config (references packages)
    └── no-team.yml
```

**Package YAML** (`lib/macos/software/google-chrome.yml`):
```yaml
- url: https://cdn.example.com/software/Google Chrome/Google Chrome-131.0.0.0.pkg
  hash_sha256: abc123...
  install_script:
    path: ../scripts/chrome-install.sh  # Optional
  uninstall_script:
    path: ../scripts/chrome-uninstall.sh  # Optional
```

**Team YAML** (`teams/workstations.yml`):
```yaml
software:
  packages:
    - path: ../lib/macos/software/google-chrome.yml
      self_service: true
      labels_include_any:
        - workstations
```

### S3 Package Structure

Packages are organized in S3 following AutoPkg's standard naming convention:

```
s3://my-fleet-packages/
  software/
    Google Chrome/
      Google Chrome-131.0.0.0.pkg
      Google Chrome-130.0.0.0.pkg
    Firefox/
      Firefox-120.0.0.pkg
      Firefox-119.0.1.pkg
```

The naming pattern is: `software/<Title>/<Title>-<Version>.<ext>`

### S3 Retention Policy

The `s3_retention_versions` parameter controls how many old versions are kept:

- **Default**: Keep the 3 most recent versions
- **Safety rule**: Never delete the only remaining version
- **Cleanup timing**: After successfully uploading a new version
- **Version sorting**: Uses semantic versioning when available, falls back to string sort

### Error Handling in GitOps Mode

- **Clone fails**: Workflow aborts before S3 upload (fail early)
- **S3 upload succeeds but PR fails**: CloudFront URL is logged for manual YAML update
- **Cleanup always runs**: Temporary directory is removed even on error

---

## Configuration

### Required Arguments (Direct Mode)

| Argument | Description |
|----------|-------------|
| `pkg_path` | Path to the built .pkg file (usually from parent recipe) |
| `software_title` | Human-readable software title (e.g., "Firefox.app") |
| `version` | Software version string |
| `fleet_api_base` | Fleet base URL (e.g., https://fleet.example.com) |
| `fleet_api_token` | Fleet API token with software management permissions |
| `team_id` | Fleet team ID to upload the package to |

### Optional Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| \`platform\` | \`darwin\` | Platform: darwin, windows, linux, ios, or ipados |
| \`self_service\` | \`true\` | Whether package is available for self-service installation |
| \`automatic_install\` | \`false\` | Auto-install on hosts without this software |
| \`labels_include_any\` | \`[]\` | List of label names - software available on hosts with ANY of these |
| \`labels_exclude_any\` | \`[]\` | List of label names - software excluded from hosts with ANY of these |
| \`install_script\` | \`""\` | Custom install script body |
| \`uninstall_script\` | \`""\` | Custom uninstall script body |
| \`pre_install_query\` | \`""\` | Pre-install osquery SQL condition |
| \`post_install_script\` | \`""\` | Post-install script body |

### Output Variables (Direct Mode)

| Variable | Description |
|----------|-------------|
| `fleet_title_id` | Fleet software title ID (may be None for duplicates) |
| `fleet_installer_id` | Fleet installer ID (may be None for duplicates) |
| `hash_sha256` | SHA-256 hash of uploaded package |

### Output Variables (GitOps Mode)

| Variable | Description |
|----------|-------------|
| `cloudfront_url` | CloudFront URL for the uploaded package |
| `pull_request_url` | URL of the created pull request |
| `git_branch` | Name of the Git branch created for the PR |
| `hash_sha256` | SHA-256 hash of uploaded package |

---

## Advanced Examples

### Self-Service Only for Specific Labels

```yaml
Process:
- Arguments:
    pkg_path: '%pkg_path%'
    software_title: '%NAME%'
    version: '%version%'
    fleet_api_base: '%FLEET_API_BASE%'
    fleet_api_token: '%FLEET_API_TOKEN%'
    team_id: '%FLEET_TEAM_ID%'
    self_service: true
    labels_include_any:
      - workstations
      - developers
  Processor: FleetImporter
```

### Automatic Installation with Exclusions

```yaml
Process:
- Arguments:
    pkg_path: '%pkg_path%'
    software_title: '%NAME%'
    version: '%version%'
    fleet_api_base: '%FLEET_API_BASE%'
    fleet_api_token: '%FLEET_API_TOKEN%'
    team_id: '%FLEET_TEAM_ID%'
    automatic_install: true
    labels_exclude_any:
      - servers
      - kiosk
  Processor: FleetImporter
```

### With Custom Scripts

```yaml
Process:
- Arguments:
    pkg_path: '%pkg_path%'
    software_title: '%NAME%'
    version: '%version%'
    fleet_api_base: '%FLEET_API_BASE%'
    fleet_api_token: '%FLEET_API_TOKEN%'
    team_id: '%FLEET_TEAM_ID%'
    self_service: true
    pre_install_query: 'SELECT 1 FROM apps WHERE bundle_id = "com.example.app" AND version < "2.0";'
    install_script: |
      #!/bin/bash
      # Custom installation logic
      echo "Installing..."
    post_install_script: |
      #!/bin/bash
      # Verify installation
      echo "Verifying..."
  Processor: FleetImporter
```

---

## Troubleshooting

### Package Already Exists

The processor uses a **two-layer detection strategy** to avoid uploading duplicates:

**Layer 1: Proactive Check (Before Upload)**

Before attempting upload, the processor queries Fleet's API to search for existing packages:

1. Searches for the software title using `/api/v1/fleet/software/titles`
2. Uses smart matching: exact match → case-insensitive → fuzzy match (e.g., "Zoom" matches "zoom.us")
3. Checks if the version exists in the software's `versions` array or `software_package` object
4. If found: Skips upload entirely, calculates hash from local file, exits gracefully

**Layer 2: Upload-Time Detection (Safety Net)**

If the proactive check misses something (network issue, timing, stale data), Fleet's API provides a fallback:

1. Fleet returns HTTP 409 Conflict when a duplicate package is uploaded
2. Processor catches the 409 error and exits gracefully
3. Calculates hash from local file and sets output variables

**Result:**

- Output variables: `fleet_title_id` and `fleet_installer_id` are set to `None`, `hash_sha256` contains the calculated hash
- No error is raised - this is expected idempotent behavior
- Running the same recipe multiple times is safe and won't create duplicates

**Note:** Fleet's API doesn't yet support hash-based lookups (tracked in [fleetdm/fleet#32965](https://github.com/fleetdm/fleet/issues/32965)), so the processor relies on title/version matching rather than content hash comparison.

### Version Detection Issues

The processor requires Fleet v4.74.0 or higher. If you see version-related errors:

```bash
# Check your Fleet version
curl -H "Authorization: Bearer $FLEET_API_TOKEN" \
  "$FLEET_API_BASE/api/v1/fleet/version"
```

### Authentication Errors

Ensure your Fleet API token has the required permissions:

- Read and write access to software management
- Access to the specified team

### Label Conflicts

Fleet's API only allows either \`labels_include_any\` OR \`labels_exclude_any\`, not both. If you specify both, the processor will fail with an error.

---

## Development

### Code Style

This processor follows AutoPkg's strict code style requirements:

```bash
# Validate Python syntax
python3 -m py_compile FleetImporter/FleetImporter.py

# Check formatting (Black)
python3 -m black --check FleetImporter/FleetImporter.py

# Check import sorting
python3 -m isort --check-only FleetImporter/FleetImporter.py

# Run linter
python3 -m flake8 FleetImporter/FleetImporter.py
```

All checks must pass before code can be contributed to AutoPkg repositories.

### Testing

Test the processor with a sample recipe:

```bash
# Create test environment
export FLEET_API_BASE="https://fleet.example.com"
export FLEET_API_TOKEN="your-test-token"
export FLEET_TEAM_ID="1"

# Run test recipe with verbose output
autopkg run -vv GoogleChrome.fleet.recipe.yaml
```

---

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Ensure all code style checks pass
5. Submit a pull request

---

## License

See [LICENSE](LICENSE) file for details.

---

## Support

For issues or questions:

- Open an issue in this repository
- Review existing [issues](https://github.com/kitzy/fleetimporter/issues)
- Check the [AutoPkg discussion forums](https://github.com/autopkg/autopkg/discussions)

---

## Related Links

- [Fleet Documentation](https://fleetdm.com/docs)
- [Fleet Software Management API](https://fleetdm.com/docs/rest-api/rest-api#software)
- [AutoPkg Documentation](https://github.com/autopkg/autopkg/wiki)
- [AutoPkg Recipe Format](https://github.com/autopkg/autopkg/wiki/Recipe-Format)
