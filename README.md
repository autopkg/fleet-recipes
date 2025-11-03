# FleetImporter for AutoPkg

AutoPkg processor for uploading macOS installer packages to Fleet.

## Getting started

Download AutoPkg from [AutoPkg releases](https://github.com/autopkg/autopkg/releases/latest) and install.

Run `autopkg repo-add fleet-recipes` to add this repo.

## Overview

FleetImporter extends AutoPkg to integrate with Fleet's software management. It supports two deployment modes:

- **Direct mode**: Upload packages directly to Fleet via API
- **GitOps mode**: Upload to S3 and create pull requests for Git-based configuration management

## Requirements

- **Python 3.9+**: Required by FleetImporter processor
- **AutoPkg 2.3+**: Required for recipe execution
- **boto3>=1.18.0**: Required for GitOps mode S3 operations
  - Automatically installed when needed if not present
  - Uses only native Python libraries for direct mode

---

## Direct mode

Upload packages directly to your Fleet server.

### Required configuration

Set via AutoPkg preferences (recommended):

```bash
defaults write com.github.autopkg FLEET_API_BASE "https://fleet.example.com"
defaults write com.github.autopkg FLEET_API_TOKEN "your-fleet-api-token"
defaults write com.github.autopkg FLEET_TEAM_ID "1"
```

Or via environment variables:

```bash
export FLEET_API_BASE="https://fleet.example.com"
export FLEET_API_TOKEN="your-fleet-api-token"
export FLEET_TEAM_ID="1"
```

### Required recipe arguments

```yaml
Process:
- Arguments:
    pkg_path: "%pkg_path%"              # From parent recipe
    software_title: "%NAME%"             # Software display name
    version: "%version%"                 # From parent recipe
    fleet_api_base: "%FLEET_API_BASE%"
    fleet_api_token: "%FLEET_API_TOKEN%"
    team_id: "%FLEET_TEAM_ID%"
  Processor: com.github.kitzy.FleetImporter/FleetImporter
```

### Optional recipe arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `self_service` | boolean | `true` | Show in Fleet Desktop |
| `automatic_install` | boolean | `false` | Auto-install on matching devices |
| `categories` | array | `[]` | Categories (Browsers, Communication, Developer tools, Productivity) |
| `labels_include_any` | array | `[]` | Only install on devices with these labels |
| `labels_exclude_any` | array | `[]` | Exclude devices with these labels |
| `icon` | string | - | Path to PNG icon (square, 120-1024px) |
| `install_script` | string | - | Custom installation script |
| `uninstall_script` | string | - | Custom uninstall script |
| `pre_install_query` | string | - | osquery to run before install |
| `post_install_script` | string | - | Script to run after install |

### Example recipe

```yaml
Description: "Builds Claude.pkg and uploads to Fleet."
Identifier: com.github.fleet.Claude
Input:
  NAME: Claude
MinimumVersion: "2.3"
ParentRecipe: com.github.kitzy.pkg.Claude
Process:
- Arguments:
    pkg_path: "%pkg_path%"
    software_title: "%NAME%"
    version: "%version%"
    fleet_api_base: "%FLEET_API_BASE%"
    fleet_api_token: "%FLEET_API_TOKEN%"
    team_id: "%FLEET_TEAM_ID%"
    self_service: true
    categories:
    - Developer tools
    icon: Claude.png
  Processor: com.github.FleetImporter/FleetImporter
```

---

## GitOps mode

Upload packages to S3 and create GitOps pull requests for Fleet configuration management.

> **Note:** GitOps mode requires you to provide your own S3 bucket and CloudFront distribution. When Fleet operates in GitOps mode, it deletes any packages not defined in the YAML files during sync ([fleetdm/fleet#34137](https://github.com/fleetdm/fleet/issues/34137)). By hosting packages externally and using pull requests, you can stage updates and merge them at your own pace.

> **Dependency:** GitOps mode requires `boto3>=1.18.0` for S3 operations. If not already installed, the processor will automatically install it using pip when GitOps mode is first used.

### Required infrastructure

- AWS S3 bucket for package storage
- CloudFront distribution pointing to the S3 bucket
- AWS credentials configured (via `~/.aws/credentials` or environment variables)

### Required configuration

Set via AutoPkg preferences (recommended):

```bash
defaults write com.github.autopkg AWS_S3_BUCKET "my-fleet-packages"
defaults write com.github.autopkg AWS_CLOUDFRONT_DOMAIN "cdn.example.com"
defaults write com.github.autopkg AWS_ACCESS_KEY_ID "your-access-key"
defaults write com.github.autopkg AWS_SECRET_ACCESS_KEY "your-secret-key"
defaults write com.github.autopkg AWS_DEFAULT_REGION "us-east-1"
defaults write com.github.autopkg FLEET_GITOPS_REPO_URL "https://github.com/org/fleet-gitops.git"
defaults write com.github.autopkg FLEET_GITOPS_GITHUB_TOKEN "your-github-token"
```

Or via environment variables:

```bash
export AWS_S3_BUCKET="my-fleet-packages"
export AWS_CLOUDFRONT_DOMAIN="cdn.example.com"
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_DEFAULT_REGION="us-east-1"
export FLEET_GITOPS_REPO_URL="https://github.com/org/fleet-gitops.git"
export FLEET_GITOPS_GITHUB_TOKEN="your-github-token"
```

### Required recipe arguments

```yaml
Process:
- Arguments:
    pkg_path: "%pkg_path%"
    software_title: "%NAME%"
    version: "%version%"
    gitops_mode: true
    aws_s3_bucket: "%AWS_S3_BUCKET%"
    aws_cloudfront_domain: "%AWS_CLOUDFRONT_DOMAIN%"
    aws_access_key_id: "%AWS_ACCESS_KEY_ID%"
    aws_secret_access_key: "%AWS_SECRET_ACCESS_KEY%"
    aws_default_region: "%AWS_DEFAULT_REGION%"
    gitops_repo_url: "%FLEET_GITOPS_REPO_URL%"
    gitops_software_dir: "%FLEET_GITOPS_SOFTWARE_DIR%"
    gitops_team_yaml_path: "%FLEET_GITOPS_TEAM_YAML_PATH%"
    github_token: "%FLEET_GITOPS_GITHUB_TOKEN%"
  Processor: com.github.kitzy.FleetImporter/FleetImporter
```

### Optional recipe arguments

All [optional arguments](#optional-recipe-arguments) from direct mode, plus:

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `s3_retention_versions` | integer | `3` | Number of old package versions to retain in S3 |
| `aws_access_key_id` | string | - | AWS access key ID for S3 operations |
| `aws_secret_access_key` | string | - | AWS secret access key for S3 operations |
| `aws_default_region` | string | `us-east-1` | AWS region for S3 operations |
| `gitops_software_dir` | string | `lib/macos/software` | Directory for software YAML files |
| `gitops_team_yaml_path` | string | - | Path to team YAML file (e.g., `teams/workstations.yml`) |

### Example recipe

```yaml
Description: "Builds Claude.pkg, uploads to S3, and creates GitOps PR."
Identifier: com.github.fleet.gitops.Claude
Input:
  NAME: Claude
  FLEET_GITOPS_SOFTWARE_DIR: lib/macos/software
  FLEET_GITOPS_TEAM_YAML_PATH: teams/workstations.yml
MinimumVersion: "2.3"
ParentRecipe: com.github.kitzy.pkg.Claude
Process:
- Arguments:
    pkg_path: "%pkg_path%"
    software_title: "%NAME%"
    version: "%version%"
    gitops_mode: true
    aws_s3_bucket: "%AWS_S3_BUCKET%"
    aws_cloudfront_domain: "%AWS_CLOUDFRONT_DOMAIN%"
    aws_access_key_id: "%AWS_ACCESS_KEY_ID%"
    aws_secret_access_key: "%AWS_SECRET_ACCESS_KEY%"
    aws_default_region: "%AWS_DEFAULT_REGION%"
    gitops_repo_url: "%FLEET_GITOPS_REPO_URL%"
    gitops_software_dir: "%FLEET_GITOPS_SOFTWARE_DIR%"
    gitops_team_yaml_path: "%FLEET_GITOPS_TEAM_YAML_PATH%"
    github_token: "%FLEET_GITOPS_GITHUB_TOKEN%"
    s3_retention_versions: 3
    self_service: true
    categories:
    - Developer tools
    icon: Claude.png
  Processor: com.github.FleetImporter/FleetImporter
```

### GitOps workflow

1. Package is uploaded to S3
2. CloudFront URL is generated
3. Software YAML files are created in GitOps repo
4. Pull request is opened for review

## Requirements

- macOS (AutoPkg requirement)
- AutoPkg 2.7+
- Fleet 4.74.0+ with software management enabled
- Fleet API token with software management permissions
- For GitOps: AWS credentials, S3 bucket, CloudFront distribution, GitHub token

---

## Troubleshooting

### Common issues

**AutoPkg not found**
- Ensure AutoPkg is installed: `autopkg version`
- Download from [AutoPkg releases](https://github.com/autopkg/autopkg/releases/latest) if needed

**Recipe execution fails**
- Verify environment variables are set correctly
- Check AutoPkg recipe dependencies: `autopkg list-repos`
- Run with verbose output: `autopkg run -v YourRecipe.recipe.yaml`

**Fleet API authentication errors**
- Verify `FLEET_API_BASE` URL is correct and accessible
- Check that `FLEET_API_TOKEN` has software management permissions
- Ensure `FLEET_TEAM_ID` exists and is accessible with your token

**GitOps mode issues**
- Verify AWS credentials are configured
- Check S3 bucket permissions for upload/delete operations
- Ensure GitHub token has repository write permissions
- Verify GitOps repository URL and paths are correct

**Package upload failures**
- Check package file exists and is readable
- Verify package is a valid macOS installer (.pkg)
- Ensure sufficient disk space and network connectivity

### Debug commands

```bash
# Check AutoPkg installation
autopkg version

# List installed repos
autopkg list-repos

# Validate recipe syntax
autopkg verify YourRecipe.recipe.yaml

# Run with maximum verbosity
autopkg run -vvv YourRecipe.recipe.yaml
```

## Getting help

- Ask questions in the [#autopkg channel](https://macadmins.slack.com/archives/C056155B4) on MacAdmins Slack
- Open an [issue](https://github.com/kitzy/fleetimporter/issues) for bugs or feature requests
- See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines

---

## License

See [LICENSE](LICENSE) file.
