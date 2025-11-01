# FleetImporter for AutoPkg

Automatically build and upload macOS installer packages to [Fleet](https://fleetdm.com) using AutoPkg.

**What it does:** Takes any AutoPkg recipe, builds a .pkg installer, and uploads it to Fleet for software deployment to your managed devices.

---

## Quick Start

### 1. Install AutoPkg

```bash
brew install autopkg
```


### 2. Add This Repository

```bash
# Add common recipe sources
autopkg repo-add https://github.com/autopkg/recipes.git
autopkg repo-add https://github.com/autopkg/homebysix-recipes.git

# Add FleetImporter
autopkg repo-add https://github.com/kitzy/fleetimporter.git
```

### 3. Configure Fleet Credentials

Set your Fleet API details in AutoPkg preferences:

```bash
defaults write com.github.autopkg FLEET_API_BASE "https://fleet.example.com"
defaults write com.github.autopkg FLEET_API_TOKEN "your-fleet-api-token"
defaults write com.github.autopkg FLEET_TEAM_ID "1"
```

### 4. Run a Recipe

```bash
autopkg run Claude.fleet -v
```

That's it! AutoPkg will download Claude, build an installer, and upload it to Fleet.

---

## How It Works

1. **AutoPkg downloads** the software (Chrome, Claude, GitHub Desktop, etc.)
2. **Builds a .pkg installer** using existing AutoPkg recipes
3. **FleetImporter uploads** the package to your Fleet server
4. **Fleet deploys** the software to your managed devices

---

## What You Can Deploy

FleetImporter works with any AutoPkg recipe that produces a `.pkg` file. Examples included in this repo:

- **Claude** (Anthropic AI assistant)
- **Google Chrome** (web browser)
- **GitHub Desktop** (Git client)
- **GPG Suite** (encryption tools)
- **Caffeine** (prevent sleep utility)
- **Signal** (encrypted messaging)
- **RubyMine** (Ruby IDE)

You can create recipes for any macOS software that has an AutoPkg recipe.

---

## Basic Recipe Example

Here's the complete recipe for Claude:

```yaml
Description: "Builds Claude.pkg and uploads to Fleet."
Identifier: com.github.kitzy.fleet.Claude
Input:
  NAME: Claude
MinimumVersion: "2.0"
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
    - Developer Tools
    icon: Claude.png
  Processor: com.github.kitzy.FleetImporter/FleetImporter
```

**That's all you need!** The recipe:
- Uses an existing AutoPkg recipe to build Claude.pkg
- Uploads it to Fleet as "Claude"
- Makes it available for self-service installation
- Categorizes it under "Developer Tools"
- Uses a custom icon

---

## Deployment Options

### Self-Service Installation

Make software available in Fleet Desktop for users to install themselves:

```yaml
self_service: true
```

### Automatic Installation

Install software automatically on devices that don't have it:

```yaml
automatic_install: true
```

### Target Specific Devices

Only make software available to devices with certain labels:

```yaml
labels_include_any:
  - workstations
  - developers
```

Or exclude from specific devices:

```yaml
labels_exclude_any:
  - servers
  - kiosk
```

### Organize with Categories

Group software in Fleet Desktop:

```yaml
categories:
  - Browser
  - Productivity
```

### Add Custom Icons

Use a custom icon (PNG, square, 120×120 to 1024×1024 px):

```yaml
icon: Claude.png
```

Place the icon file next to your recipe.

---

## GitOps Mode (Advanced)

For organizations using Git-based configuration management, FleetImporter supports uploading to S3 and creating pull requests instead of direct Fleet uploads.

### Why GitOps?

- **Version control:** All software deployments tracked in Git
- **Review process:** Changes go through pull request workflow
- **CDN delivery:** Packages served from CloudFront instead of Fleet
- **Team collaboration:** Software definitions managed as code

### GitOps Setup

```bash
# S3 and CloudFront
export AWS_S3_BUCKET="my-fleet-packages"
export AWS_CLOUDFRONT_DOMAIN="cdn.example.com"

# GitOps repository
export FLEET_GITOPS_REPO_URL="https://github.com/org/fleet-gitops.git"
export FLEET_GITOPS_TEAM_YAML_PATH="teams/workstations.yml"
export FLEET_GITOPS_GITHUB_TOKEN="your-github-token"
```

### GitOps Recipe

```yaml
Process:
- Arguments:
    pkg_path: "%pkg_path%"
    software_title: "%NAME%"
    version: "%version%"
    gitops_mode: true
    aws_s3_bucket: "%AWS_S3_BUCKET%"
    aws_cloudfront_domain: "%AWS_CLOUDFRONT_DOMAIN%"
    gitops_repo_url: "%FLEET_GITOPS_REPO_URL%"
    gitops_team_yaml_path: "%FLEET_GITOPS_TEAM_YAML_PATH%"
    github_token: "%FLEET_GITOPS_GITHUB_TOKEN%"
    self_service: true
  Processor: com.github.kitzy.FleetImporter/FleetImporter
```

### What GitOps Mode Does

1. Uploads package to S3
2. Generates CloudFront URL
3. Creates YAML files in your GitOps repo
4. Opens a pull request for review
5. After PR merge, Fleet syncs the changes

---

## Configuration Reference

### Required Settings (Direct Mode)

| Setting | Description | Example |
|---------|-------------|---------|
| `fleet_api_base` | Your Fleet server URL | `https://fleet.example.com` |
| `fleet_api_token` | Fleet API token | `your-api-token` |
| `team_id` | Fleet team ID | `1` |
| `pkg_path` | Path to installer | `%pkg_path%` (from parent recipe) |
| `software_title` | Software name | `Google Chrome` |
| `version` | Version number | `%version%` (from parent recipe) |

### Optional Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `self_service` | `true` | Show in Fleet Desktop for self-install |
| `automatic_install` | `false` | Auto-install on devices without this software |
| `categories` | `[]` | Category names for grouping |
| `labels_include_any` | `[]` | Only devices with these labels |
| `labels_exclude_any` | `[]` | Skip devices with these labels |
| `icon` | - | Path to PNG icon file |
| `install_script` | - | Custom installation script |
| `uninstall_script` | - | Custom uninstall script |
| `pre_install_query` | - | osquery query to run before install |
| `post_install_script` | - | Script to run after install |

### GitOps Settings

| Setting | Required | Description |
|---------|----------|-------------|
| `gitops_mode` | No | Set to `true` to enable GitOps |
| `aws_s3_bucket` | Yes* | S3 bucket name |
| `aws_cloudfront_domain` | Yes* | CloudFront domain |
| `gitops_repo_url` | Yes* | GitOps repo URL |
| `gitops_team_yaml_path` | Yes* | Path to team YAML |
| `github_token` | Yes* | GitHub token |
| `s3_retention_versions` | No | Keep N old versions (default: 3) |

*Required when `gitops_mode: true`

---

## Requirements

- **macOS** (AutoPkg only runs on macOS)
- **AutoPkg 2.7+**
- **Fleet server 4.74.0+** with software management enabled
- **Fleet API token** with software management permissions

---

## Troubleshooting

### "Package already exists"

This is normal! FleetImporter checks if the package is already uploaded and skips re-uploading. You'll see this if you run the same recipe twice.

### "Authentication failed"

Check your Fleet API token:

```bash
# Test your token
curl -H "Authorization: Bearer $FLEET_API_TOKEN" \
  "$FLEET_API_BASE/api/v1/fleet/version"
```

### "Recipe not found"

Make sure you've added the necessary recipe repositories:

```bash
autopkg repo-list
autopkg repo-add https://github.com/autopkg/recipes.git
```

### Need More Help?

- Check [Fleet's documentation](https://fleetdm.com/docs)
- Review [AutoPkg documentation](https://github.com/autopkg/autopkg/wiki)
- Open an [issue](https://github.com/kitzy/fleetimporter/issues)

---

## Advanced Examples

### Enterprise Deployment with All Options

```yaml
Process:
- Arguments:
    pkg_path: "%pkg_path%"
    software_title: "Google Chrome"
    version: "%version%"
    fleet_api_base: "%FLEET_API_BASE%"
    fleet_api_token: "%FLEET_API_TOKEN%"
    team_id: "%FLEET_TEAM_ID%"
    self_service: true
    automatic_install: false
    categories:
      - Browser
      - Productivity
    labels_include_any:
      - workstations
    labels_exclude_any:
      - servers
    icon: Chrome.png
    pre_install_query: 'SELECT 1 FROM apps WHERE bundle_id = "com.google.Chrome" AND version < "130.0";'
    install_script: |
      #!/bin/bash
      echo "Installing Chrome..."
    post_install_script: |
      #!/bin/bash
      echo "Chrome installed successfully"
  Processor: com.github.kitzy.FleetImporter/FleetImporter
```

### Automatic Updates for Critical Software

```yaml
Process:
- Arguments:
    pkg_path: "%pkg_path%"
    software_title: "Security Tool"
    version: "%version%"
    fleet_api_base: "%FLEET_API_BASE%"
    fleet_api_token: "%FLEET_API_TOKEN%"
    team_id: "%FLEET_TEAM_ID%"
    automatic_install: true
    labels_exclude_any:
      - test-devices
  Processor: com.github.kitzy.FleetImporter/FleetImporter
```

---

## Creating Your Own Recipes

1. Find an existing AutoPkg recipe for your software:
   ```bash
   autopkg search "Firefox"
   ```

2. Create a new recipe file (e.g., `Firefox.fleet.recipe.yaml`):
   ```yaml
   Description: "Builds Firefox.pkg and uploads to Fleet."
   Identifier: com.github.yourname.fleet.Firefox
   Input:
     NAME: Firefox
   MinimumVersion: "2.0"
   ParentRecipe: com.github.autopkg.pkg.Firefox
   Process:
   - Arguments:
       pkg_path: "%pkg_path%"
       software_title: "%NAME%"
       version: "%version%"
       fleet_api_base: "%FLEET_API_BASE%"
       fleet_api_token: "%FLEET_API_TOKEN%"
       team_id: "%FLEET_TEAM_ID%"
       self_service: true
     Processor: com.github.kitzy.FleetImporter/FleetImporter
   ```

3. Run it:
   ```bash
   autopkg run Firefox.fleet.recipe.yaml -v
   ```

---

## License

See [LICENSE](LICENSE) file.

---

## Links

- [Fleet Documentation](https://fleetdm.com/docs)
- [AutoPkg Documentation](https://github.com/autopkg/autopkg/wiki)
- [Report Issues](https://github.com/kitzy/fleetimporter/issues)

