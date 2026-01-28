# fleet-recipes

A community-maintained repo of AutoPkg recipes for uploading macOS installer packages to Fleet. Contributions are welcome!

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
- **boto3 1.18.0+**: Required for GitOps mode S3 operations (optional for direct mode)
  - Must be installed manually into AutoPkg's Python environment:
    ```bash
    /Library/AutoPkg/Python3/Python.framework/Versions/Current/bin/python3 -m pip install boto3>=1.18.0
    ```
  - Direct mode uses only native Python libraries (no external dependencies)

---

## Recipe variables

FleetImporter recipes support the following variables. Configuration can be set via AutoPkg preferences or recipe overrides.

| Variable | Direct Mode | GitOps Mode | Default | Description |
|----------|-------------|-------------|---------|-------------|
| **Mode Control** | | | | |
| `GITOPS_MODE` | Optional | Required | `false` | Set to `true` to enable GitOps mode |
| **Package Information** | | | | |
| `pkg_path` | Required | Required | - | Path to the .pkg file (typically from parent recipe) |
| `software_title` | Required | Required | - | Software display name |
| `version` | Required | Required | - | Software version (typically from parent recipe) |
| `display_name` | Optional | Optional | `software_title` | Custom display name for the software package in Fleet |
| **Fleet API (Direct Mode)** | | | | |
| `FLEET_API_BASE` | Required | Not used | - | Fleet server URL (e.g., `https://fleet.example.com`) |
| `FLEET_API_TOKEN` | Required | Not used | - | Fleet API authentication token |
| `FLEET_TEAM_ID` | Required | Not used | - | Fleet team ID for software assignment |
| **AWS S3 (GitOps Mode)** | | | | |
| `AWS_S3_BUCKET` | Not used | Required | - | S3 bucket name for package storage |
| `AWS_CLOUDFRONT_DOMAIN` | Not used | Required | - | CloudFront domain for package URLs |
| `AWS_ACCESS_KEY_ID` | Not used | Optional | - | AWS access key (can use `~/.aws/credentials` instead) |
| `AWS_SECRET_ACCESS_KEY` | Not used | Optional | - | AWS secret key (can use `~/.aws/credentials` instead) |
| `AWS_DEFAULT_REGION` | Not used | Required | `us-east-1` | AWS region for S3 operations |
| **GitOps Repository** | | | | |
| `FLEET_GITOPS_REPO_URL` | Not used | Required | - | Git repository URL for Fleet configuration |
| `FLEET_GITOPS_GITHUB_TOKEN` | Not used | Required | - | GitHub token with repository write permissions |
| `FLEET_GITOPS_SOFTWARE_DIR` | Not used | Optional | `lib/macos/software` | Directory for software YAML files in GitOps repo |
| `FLEET_GITOPS_TEAM_YAML_PATH` | Not used | Optional | `teams/workstations.yml` | Path to team YAML file in GitOps repo |
| **Software Configuration** | | | | |
| `self_service` | Optional | Optional | `true` | Show software in Fleet Desktop |
| `automatic_install` | Optional | Optional | `false` | Auto-install on matching devices |
| `categories` | Optional | Optional | `[]` | Categories for self-service (Browsers, Communication, Developer tools, Productivity) |
| `labels_include_any` | Optional | Optional | `[]` | Only install on devices with these labels |
| `labels_exclude_any` | Optional | Optional | `[]` | Exclude devices with these labels |
| `icon` | Optional | Optional | - | Path to PNG icon (square, 120-1024px, max 100KB). Auto-extracts from app bundle if not provided |
| `install_script` | Optional | Optional | - | Custom installation script |
| `uninstall_script` | Optional | Optional | - | Custom uninstall script |
| `pre_install_query` | Optional | Optional | - | osquery to run before install |
| `post_install_script` | Optional | Optional | - | Script to run after install |
| **Auto-Update Policies** | | | | |
| `automatic_update` | Optional | Optional | `false` | Create/update policies for automatic version detection and installation |
| `auto_update_policy_query` | Optional | Optional | Auto-generated | Custom osquery for version detection (uses `%VERSION%` placeholder). Auto-generates from bundle ID if not provided |
| `AUTO_UPDATE_POLICY_NAME` | Optional | Optional | `autopkg-auto-update-%NAME%` | Policy name template (%NAME% replaced with slugified software title) |
| **GitOps-Specific Options** | | | | |
| `s3_retention_versions` | Not used | Optional | `0` | Number of old package versions to retain in S3 (0 = no pruning) |

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

---

## GitOps mode

Upload packages to S3 and create GitOps pull requests for Fleet configuration management.

> **Note:** GitOps mode requires you to provide your own S3 bucket and CloudFront distribution. When Fleet operates in GitOps mode, it deletes any packages not defined in the YAML files during sync ([fleetdm/fleet#34137](https://github.com/fleetdm/fleet/issues/34137)). By hosting packages externally and using pull requests, you can stage updates and merge them at your own pace.

### Switching to GitOps mode

**Prerequisites:**
1. Install boto3 into AutoPkg's Python environment (required for S3 operations):
   ```bash
   /Library/AutoPkg/Python3/Python.framework/Versions/Current/bin/python3 -m pip install boto3>=1.18.0
   ```

2. Create a recipe override and set `GITOPS_MODE: true`:
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
- AWS credentials with read/write access to the S3 bucket

### Required configuration

Set via AutoPkg preferences:

```bash
defaults write com.github.autopkg AWS_S3_BUCKET "my-fleet-packages"
defaults write com.github.autopkg AWS_CLOUDFRONT_DOMAIN "cdn.example.com"
defaults write com.github.autopkg AWS_ACCESS_KEY_ID "your-access-key"
defaults write com.github.autopkg AWS_SECRET_ACCESS_KEY "your-secret-key"
defaults write com.github.autopkg AWS_DEFAULT_REGION "us-east-1"
defaults write com.github.autopkg FLEET_GITOPS_REPO_URL "https://github.com/org/fleet-gitops.git"
defaults write com.github.autopkg FLEET_GITOPS_GITHUB_TOKEN "your-github-token"
```

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

## Custom scripts

FleetImporter supports custom install, uninstall, and post-install scripts. Scripts can be provided as **inline content** or as **file paths**.

### Inline scripts

Provide the script content directly in the recipe:

```yaml
Input:
  UNINSTALL_SCRIPT: |
    #!/bin/bash
    rm -rf "/Applications/MyApp.app"
    rm -rf "$HOME/Library/Application Support/MyApp"
```

### Script files

Reference a script file stored alongside the recipe:

```yaml
Input:
  UNINSTALL_SCRIPT: uninstall-myapp.sh
```

FleetImporter automatically detects file paths (scripts ending in `.sh` or containing `/`) and reads the file content. Relative paths are resolved relative to the recipe directory.

**Benefits of script files:**
- Keeps recipes clean and readable
- Makes scripts easier to maintain and test independently
- Supports syntax highlighting in editors
- Enables script reuse across multiple recipes

### Using scripts with overrides

When creating AutoPkg overrides with `autopkg make-override`, script file references continue to work because:

1. **Script files stay with the original recipe** - The override only changes Input values, not companion files
2. **Paths resolve to the original recipe directory** - AutoPkg's `RECIPE_DIR` always points to the original recipe location
3. **You can override with custom scripts** by:
   - Providing inline script content in your override
   - Specifying an absolute path to your own script file
   - Copying the script to your override directory and using a relative path

**Example override customization:**

```yaml
Input:
  # Option 1: Use inline script
  UNINSTALL_SCRIPT: |
    #!/bin/bash
    echo "Custom uninstall logic"
  
  # Option 2: Use absolute path to custom script
  UNINSTALL_SCRIPT: /path/to/my-custom-uninstall.sh
  
  # Option 3: Default - uses original recipe's script file
  UNINSTALL_SCRIPT: uninstall-myapp.sh
```

### Supported script parameters

All three script parameters support both inline and file path modes:

- `install_script`: Custom installation script
- `uninstall_script`: Custom uninstall script
- `post_install_script`: Script to run after installation

---

## Auto-update policy automation

FleetImporter can automatically create Fleet policies that detect outdated software versions and trigger automatic updates via policy automation. When enabled, a policy is created for each software package that:

1. **Detects outdated versions**: Uses osquery to find hosts running any version except the latest
2. **Triggers installation**: Automatically installs the updated package when policy fails

### Enabling auto-update policies

Auto-update policies are **disabled by default** for backward compatibility. Enable them via recipe overrides:

```bash
# Enable in a recipe override (per-recipe control)
autopkg make-override VendorName/SoftwareName.fleet.recipe.yaml
# Edit the override to set automatic_update: true
autopkg run SoftwareName.fleet.recipe.yaml
```

### How it works

When `automatic_update` is set to `true`, FleetImporter:

1. **Builds version query**: Creates an osquery SQL query to detect outdated versions using one of two modes:

   **Automatic Bundle ID Mode** (Recommended):
   If no custom query is provided, the processor automatically:
   - Extracts the bundle identifier from the `.pkg` file
   - Generates a default query using the `apps` table with `!=` comparison
   - Works for most standard macOS applications
   - Requires no manual configuration

   **Custom Query Mode** (Advanced use cases):
   Define `auto_update_policy_query` in your recipe with a `%VERSION%` placeholder:
   ```yaml
   auto_update_policy_query: |
     SELECT 1 WHERE NOT EXISTS (
       SELECT 1 FROM apps WHERE bundle_identifier = 'com.github.GitHubClient' AND bundle_short_version != '%VERSION%'
     );
   ```
   The `%VERSION%` placeholder is replaced with the actual version at runtime. Use custom queries for:
   - Non-standard bundle ID detection
   - Windows registry-based detection
   - Linux package managers
   - Custom osquery tables or complex version logic

2. **Creates policy** (Direct mode): Uses Fleet API to create or update a policy with:
   - Descriptive name (e.g., `autopkg-auto-update-github-desktop`)
   - Version detection query (custom or auto-generated)
   - Link to install package automatically on policy failure
   - Platform targeting (macOS only)

3. **Creates policy YAML** (GitOps mode): Writes policy definition to `lib/policies/` 

### Policy naming

Policy names are generated from the `AUTO_UPDATE_POLICY_NAME` template:

- **Default template**: `autopkg-auto-update-%NAME%`
- **%NAME% placeholder**: Replaced with slugified software title
- **Slugification**: Converts to lowercase, removes special characters, replaces spaces with hyphens
- **Customization**: Override `AUTO_UPDATE_POLICY_NAME` in your recipe to use a different naming pattern

Examples:
- `GitHub Desktop` → `autopkg-auto-update-github-desktop`
- `Visual Studio Code` → `autopkg-auto-update-visual-studio-code`
- `1Password 8` → `autopkg-auto-update-1password-8`

### SQL injection prevention

All bundle identifiers and versions are automatically escaped to prevent SQL injection:

- Single quotes are doubled: `com.o'reilly.app` → `com.o''reilly.app`
- Query remains safe even with malicious input
- Tested against common injection patterns (OR clauses, UNION, DROP TABLE, etc.)

### Important considerations

1. **Query modes**: 
   - **Custom queries** (via `auto_update_policy_query`) give full control and support any osquery table
   - **Automatic mode** extracts CFBundleIdentifier from `.pkg` files and works for standard macOS apps
   - If automatic extraction fails and no custom query is provided, policy creation is skipped with a warning

2. **Version comparison**: Uses exact version matching with `!=` comparison. Policies pass when no apps exist with incorrect versions (app not installed OR all instances have correct version). Policies fail when any app instance has a version that doesn't match the required version.

3. **Policy cleanup**: Policies are NOT automatically deleted when software is removed. You should manually delete outdated policies or implement cleanup automation.

4. **Error handling**: Policy creation failures are logged as warnings and don't block package uploads. Check AutoPkg output for any policy-related errors.

5. **Team vs global policies**:
   - Direct mode: Creates team-specific policies when `FLEET_TEAM_ID` > 0, global policies when `FLEET_TEAM_ID` = 0
   - GitOps mode: Policy scope determined by GitOps repository structure

6. **Idempotency**: Existing policies with the same name are updated (not duplicated) when recipes run again

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
- Open an [issue](https://github.com/autopkg/fleet-recipes/issues) for bugs or feature requests
- See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines

---

## License

See [LICENSE](LICENSE) file.
