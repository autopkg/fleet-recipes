# fleet-recipes

A community repo of AutoPkg recipes for uploading macOS installer packages to Fleet.

## Getting started

Run `autopkg repo-add fleet-recipes` to add this repo.

## Overview

FleetImporter extends AutoPkg to integrate with Fleet's software management. Recipes use a **combined format** that supports both deployment modes in a single file:

- **[Direct mode](#direct-mode)**: Upload packages directly to Fleet via API
- **[GitOps mode](#gitops-mode)**: Upload to S3 and create pull requests for Git-based configuration management

Mode is controlled by the `GITOPS_MODE` input variable (default: `false`). Users can switch modes via recipe overrides without maintaining separate recipe files.

## Requirements

- **Python 3.9+**: Required by FleetImporter processor
- **AutoPkg 2.3+**: Required for recipe execution
- **boto3 1.18.0+**: Required for GitOps mode S3 operations
  - Processor attempts automatic installation at import time if not present
  - If auto-installation fails, GitOps mode will not be available
  - Direct mode uses only native Python libraries (no external dependencies)

---

## Direct mode

Upload packages directly to your Fleet server. This is the **default mode** for all recipes.

### Running recipes in direct mode

```bash
# Set required configuration
defaults write com.github.autopkg FLEET_API_BASE "https://fleet.example.com"
defaults write com.github.autopkg FLEET_API_TOKEN "your-fleet-api-token"
defaults write com.github.autopkg FLEET_TEAM_ID "1"

# Run any recipe (defaults to direct mode)
autopkg run VendorName/SoftwareName.fleet.recipe.yaml
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
  Processor: com.github.fleet.FleetImporter/FleetImporter
```

### Optional recipe arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `self_service` | boolean | `true` | Show in Fleet Desktop |
| `automatic_install` | boolean | `false` | Auto-install on matching devices |
| `categories` | array | `[]` | Categories for self-service software (required when `self_service` is `true`). Valid values: Browsers, Communication, Developer tools, Productivity |
| `labels_include_any` | array | `[]` | Only install on devices with these labels |
| `labels_exclude_any` | array | `[]` | Exclude devices with these labels |
| `icon` | string | - | Path to PNG icon (square, 120-1024px, max 100KB). Paths are resolved relative to the recipe directory. If not provided, automatically extracts from app bundle. |
| `install_script` | string | - | Custom installation script |
| `uninstall_script` | string | - | Custom uninstall script |
| `pre_install_query` | string | - | osquery to run before install |
| `post_install_script` | string | - | Script to run after install |

---

## GitOps mode

Upload packages to S3 and create GitOps pull requests for Fleet configuration management.

> **Note:** GitOps mode requires you to provide your own S3 bucket and CloudFront distribution. When Fleet operates in GitOps mode, it deletes any packages not defined in the YAML files during sync ([fleetdm/fleet#34137](https://github.com/fleetdm/fleet/issues/34137)). By hosting packages externally and using pull requests, you can stage updates and merge them at your own pace.

> **Dependency:** GitOps mode requires `boto3>=1.18.0` for S3 operations. If not already installed, the processor will automatically install it using pip when GitOps mode is first used.

### Switching to GitOps mode

To use GitOps mode, create a recipe override and set `GITOPS_MODE: true`:

```bash
# Create an override
autopkg make-override VendorName/SoftwareName.fleet.recipe.yaml

# Edit the override to set GITOPS_MODE: true
# Then run it
autopkg run SoftwareName.fleet.recipe.yaml
```

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
  Processor: com.github.fleet.FleetImporter/FleetImporter
```

### Optional recipe arguments

All [optional arguments](#optional-recipe-arguments) from direct mode, plus:

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `s3_retention_versions` | integer | `0` | Number of old package versions to retain in S3 (0 = no pruning) |
| `aws_access_key_id` | string | - | AWS access key ID for S3 operations |
| `aws_secret_access_key` | string | - | AWS secret access key for S3 operations |
| `aws_default_region` | string | `us-east-1` | AWS region for S3 operations |
| `gitops_software_dir` | string | `lib/macos/software` | Directory for software YAML files |
| `gitops_team_yaml_path` | string | `teams/workstations.yml` | Path to team YAML file |

### GitOps workflow

1. Package is uploaded to S3
2. CloudFront URL is generated
3. Software YAML files are created in GitOps repo
4. Pull request is opened for review

---

## Automatic icon extraction

FleetImporter automatically extracts and uploads application icons from `.pkg` files without requiring manual icon files:

- **Automatic extraction**: Finds the `.app` bundle in the package, extracts the icon from `Info.plist`, and converts it to PNG format
- **Size optimization**: Automatically compresses icons that exceed Fleet's 100 KB limit by resizing to 512px, 256px, or 128px
- **Format conversion**: Converts macOS `.icns` files to PNG format using the built-in `sips` tool
- **Fallback**: If extraction fails, continues without an icon (or uses manual `icon` path if provided)
- **Override**: Specify `icon: path/to/icon.png` in your recipe to use a custom icon instead of auto-extraction

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

# Run style guide compliance tests
python3 tests/test_style_guide_compliance.py
```

---

## Getting help

- Ask questions in the [#autopkg channel](https://macadmins.slack.com/archives/C056155B4) on MacAdmins Slack
- Open an [issue](https://github.com/kitzy/fleetimporter/issues) for bugs or feature requests
- See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines

---

## License

See [LICENSE](LICENSE) file.
