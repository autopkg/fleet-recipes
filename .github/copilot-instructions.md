# Fleet AutoPkg Recipes

This repository contains AutoPkg processors and recipes for Fleet device management platform integration. The main component is a Python processor that uploads software packages to Fleet and creates GitOps pull requests for configuration management.

Always reference these instructions first and fallback to search or bash commands only when you encounter unexpected information that does not match the info here.

## Communication Style

### Git Commit Messages and Pull Requests
- **NEVER use emojis** in commit messages or PR descriptions
- Use clear, professional language
- Focus on technical details and implementation specifics
- When creating PRs, always use `gh pr create --web` to open the browser for final review

### PR Creation Workflow
1. Create feature branch: `git checkout -b feature-name`
2. Stage changes: `git add <files>`
3. Commit with clear message (no emojis): `git commit -m "Description"`
4. Push branch: `git push -u origin feature-name`
5. Create PR with `--web` flag: `gh pr create --title "Title" --body "Description" --web`
6. The `--web` flag opens the browser for final review before submission

## Working Effectively

### Bootstrap and Setup (macOS required for AutoPkg)
- Install pre-commit for automated code style validation:
  - `python3 -m pip install --upgrade pip`
  - `python3 -m pip install pre-commit` -- takes 10-30 seconds. NEVER CANCEL.
  - `pre-commit install` -- installs git hooks
  - Note: The processor uses only native Python libraries available in AutoPkg's bundled Python (no external dependencies required for runtime)
- Install AutoPkg (macOS only):
  - Download the latest release from https://github.com/autopkg/autopkg/releases/latest
  - Install the `.pkg` file (e.g., `autopkg-2.7.3.pkg`)
  - Verify installation: `autopkg version`
  - Installation takes 1-2 minutes. NEVER CANCEL.
- Configure AutoPkg repositories:
  - `autopkg repo-add https://github.com/autopkg/recipes.git` -- takes 30-60 seconds. NEVER CANCEL.
  - `autopkg repo-add https://github.com/autopkg/homebysix-recipes.git` -- takes 30-60 seconds. NEVER CANCEL.
  - Note: This repository contains its own FleetImporter processor, so no additional repo is needed for Fleet integration
- Validate Python syntax and code style:
  - `pre-commit run --all-files` -- runs all code style checks (black, isort, flake8, recipe validation)

### Critical macOS Setup Notes
- AutoPkg ONLY works on macOS. Do not attempt to install on Linux/Windows.
- Install AutoPkg from GitHub releases: https://github.com/autopkg/autopkg/releases/latest
- Ensure Xcode Command Line Tools: `xcode-select --install`
- Python 3.9+ is required: `python3 --version`

### Environment Variables for Local Testing
- For Direct Mode (Fleet API):
  - `export FLEET_API_BASE="https://fleet.example.com"`
  - `export FLEET_API_TOKEN="your-fleet-api-token"`
  - `export FLEET_TEAM_ID="1"`
- For GitOps Mode (S3/GitHub):
  - `export AWS_S3_BUCKET="your-fleet-packages-bucket"`
  - `export AWS_CLOUDFRONT_DOMAIN="d1234567890abc.cloudfront.net"`
  - `export FLEET_GITOPS_REPO_URL="https://github.com/org/fleet-gitops.git"`
  - `export FLEET_GITOPS_GITHUB_TOKEN="your-github-token"`
  - `export FLEET_GITOPS_SOFTWARE_DIR="lib/macos/software"`
  - `export FLEET_GITOPS_TEAM_YAML_PATH="teams/workstations.yml"`
- Set `GIT_TERMINAL_PROMPT=0` to prevent interactive Git authentication prompts

### Testing and Validation
- Test AutoPkg Python has required modules: `/Library/AutoPkg/Python3/Python.framework/Versions/Current/bin/python3 -c "import yaml, urllib.request, json; print('Dependencies OK')"`
- Validate recipe YAML syntax: `python3 -c "import yaml; yaml.safe_load(open('GitHub/GithubDesktop.fleet.direct.recipe.yaml'))"`
- Test Git operations: `git status && git log --oneline -5`
- Run direct mode recipe locally (macOS only): `autopkg run GitHub/GithubDesktop.fleet.direct.recipe.yaml -v`
- Run gitops mode recipe locally (macOS only): `autopkg run GitHub/GithubDesktop.fleet.gitops.recipe.yaml -v`

### File Validation
- Always validate YAML syntax when modifying recipe files
- Pre-commit automatically runs on `git commit`, catching issues before they're committed
- Test environment variable substitution in recipes
- **ALWAYS write recipes in YAML format, not XML** - This repository uses YAML recipes exclusively

### Runtime Dependencies
- **The FleetImporter processor uses ONLY native Python libraries** - no external pip packages required at runtime
- AutoPkg's bundled Python 3.10+ includes all necessary modules: `urllib`, `json`, `yaml`, `hashlib`, etc.
- Development dependency (pre-commit) manages black, isort, flake8 automatically - no manual installation needed

## Code Style Requirements

ALL Python code must pass these checks before being committed:

### Pre-Commit Hooks (Automated)
The repository uses pre-commit hooks to automatically validate code style on every commit:
- **Black**: Consistent code formatting across the AutoPkg ecosystem
- **isort**: Standardized import organization
- **Flake8 with Bugbear**: Code quality, unused variables, style violations
- **AutoPkg Recipe Validation**: Ensures recipes follow the style guide

### Usage
- **Automatic**: Hooks run on every `git commit`
- **Manual validation**: `pre-commit run --all-files`
- **Fix formatting issues**: Pre-commit will auto-fix black and isort issues; just review and re-stage the changes
- **Configuration**: Uses `.flake8` and `.pre-commit-config.yaml` for project-specific settings

**CRITICAL**: All tools must pass without errors before any code can be contributed to this repository. This is a hard requirement of the FleetImporter project.

## Validation Scenarios

### After Making Code Changes
- ALWAYS run AutoPkg code style requirements (required by AutoPkg project):
  - `pre-commit run --all-files` -- validates syntax, formatting, imports, and linting
- Test YAML parsing: `python3 -c "import yaml; [yaml.safe_load(open(f)) for f in ['GitHub/GithubDesktop.fleet.direct.recipe.yaml', 'GitHub/GithubDesktop.fleet.gitops.recipe.yaml', 'Anthropic/Claude.fleet.direct.recipe.yaml']]"`
- Validate Git operations work correctly
- If modifying the processor, test with a sample recipe using autopkg (requires macOS)

### Manual Testing Workflow
- Create temporary directory and clone a test GitOps repository
- Set environment variables for Fleet API and GitHub tokens
- Run autopkg with sample recipe and inspect created branch/YAML changes
- Verify no sensitive data is logged or committed

## Build and Test Commands

### Syntax Validation (Linux/macOS)
- `python3 -m py_compile FleetImporter/FleetImporter.py` -- takes < 1 second
- `python3 -c "import yaml; yaml.safe_load(open('Anthropic/Claude.fleet.direct.recipe.yaml'))"` -- takes < 1 second

### Full Recipe Testing (macOS only)
- `autopkg run Anthropic/Claude.fleet.direct.recipe.yaml -v` -- takes 5-15 minutes for download/build. NEVER CANCEL. Set timeout to 30+ minutes.
- `autopkg run GitHub/GithubDesktop.fleet.gitops.recipe.yaml -v` -- takes 5-15 minutes for download/build. NEVER CANCEL. Set timeout to 30+ minutes.

### Environment Testing
- Check Python version: `python3 --version` (requires 3.9+)
- Test Git: `git --version`
- Test AutoPkg: `autopkg version` (macOS only)

## Repository Structure

### Core Components
- `.github/` - GitHub workflows and configuration (including these instructions)
- `FleetImporter/` - Main AutoPkg processor for Fleet integration
  - `FleetImporter.py` - The processor implementation
- `README.md` - Comprehensive documentation
- `.gitignore` - Excludes Python cache and IDE files
- `.env.example` - Example environment variables for local testing

### Recipe Directories
**Every directory other than `.github`, `_templates`, and `FleetImporter` is a vendor recipe directory.**

The repository structure grows over time as new recipes are added. Current examples include:
- `Anthropic/` - Claude recipes
- `Caffeine/` - Caffeine recipes
- `GitHub/` - GitHub Desktop recipes
- `GPGSuite/` - GPG Suite recipes
- `Raycast Technologies/` - Raycast recipes
- `Signal/` - Signal recipes

Each vendor directory contains combined recipes that support both modes:
- `<VendorName>/<SoftwareTitle>.fleet.recipe.yaml` - Combined recipe (supports both direct and GitOps modes)

**Template directory:**
- `_templates/Template.fleet.recipe.yaml` - Base template for creating new recipes

### Recipe Types
This repository uses a combined recipe approach:
- **Combined Recipe** (`.fleet.recipe.yaml`): Single recipe file that supports both direct and GitOps modes
  - Use `_templates/Template.fleet.recipe.yaml` as the starting point for all new recipes
  - Mode is controlled by the `GITOPS_MODE` input variable (default: `false` for direct mode)
  - Users can override to GitOps mode via recipe overrides or AutoPkg preferences
  - All mode-specific credentials come from AutoPkg preferences/environment variables
  
**Legacy recipe types** (for reference, not used in new recipes):
- **Direct Mode** (`.fleet.direct.recipe.yaml`): Upload packages directly to Fleet via API
- **GitOps Mode** (`.fleet.gitops.recipe.yaml`): Upload to S3 and create pull requests for Git-based configuration

All recipes follow a consistent directory structure: `<VendorName>/<SoftwareName>.fleet.recipe.yaml`

### Recipe Structure Understanding
AutoPkg recipes follow this pattern:
- `Description` - Human readable description
- `Identifier` - Unique identifier for the recipe
- `Input` - Variables like `NAME` for the software title
- `MinimumVersion` - Required AutoPkg version
- `ParentRecipe` - Upstream recipe that builds the package
- `Process` - Array of processors, including FleetImporter with Arguments

Example recipe structure:
```yaml
Description: 'Builds [Software].pkg and uploads to Fleet'
Identifier: com.github.yourorg.fleet.SoftwareName
Input:
  NAME: Software Name
MinimumVersion: '2.0'
ParentRecipe: com.github.author.pkg.SoftwareName
Process:
- Arguments:
    # FleetImporter arguments here
    icon: SoftwareName.png  # Optional: path to icon file (PNG, square, 120x120-1024x1024px)
  Processor: FleetImporter
```

### Icon Support
The FleetImporter processor automatically extracts and uploads application icons from `.pkg` files:
- **Automatic Extraction**: Extracts icons from `.app` bundles inside packages automatically
- **Format**: PNG (automatically converted from macOS `.icns` format)
- **Size Limit**: Maximum 100 KB (Fleet requirement)
- **Size Optimization**: Automatically compresses large icons by resizing to 512px, 256px, or 128px
- **Manual Override**: Add `icon: IconFilename.png` to recipe Arguments to use a custom icon instead
- **Skip Extraction**: Set `skip_icon_extraction: true` to disable automatic extraction
- **Path**: Manual icon paths are relative to recipe file directory or absolute
- **API**: Uses Fleet's `PUT /api/v1/fleet/software/titles/:id/icon` endpoint
- **Timing**: Icon is uploaded immediately after package upload (both direct and GitOps modes)
- **GitOps**: Icons are copied to `lib/icons/` directory in GitOps repository with relative path references

**How automatic extraction works:**
1. Expands the `.pkg` file using `pkgutil --expand`
2. Finds the `.app` bundle within the package
3. Reads `CFBundleIconFile` from `Info.plist`
4. Locates the `.icns` file in `Contents/Resources/`
5. Converts to PNG using macOS `sips` tool
6. Compresses if needed to meet 100 KB limit
7. Uploads to Fleet or copies to GitOps repo

**Example with automatic icon extraction (recommended):**
```yaml
Process:
- Arguments:
    pkg_path: "%pkg_path%"
    software_title: "%NAME%"
    version: "%version%"
    fleet_api_base: "%FLEET_API_BASE%"
    fleet_api_token: "%FLEET_API_TOKEN%"
    team_id: "%FLEET_TEAM_ID%"
    self_service: true
    # No icon parameter - will auto-extract from package
  Processor: com.github.fleet.FleetImporter/FleetImporter
```

**Example with manual icon override:**
```yaml
Process:
- Arguments:
    pkg_path: "%pkg_path%"
    software_title: "%NAME%"
    version: "%version%"
    fleet_api_base: "%FLEET_API_BASE%"
    fleet_api_token: "%FLEET_API_TOKEN%"
    team_id: "%FLEET_TEAM_ID%"
    self_service: true
    icon: CustomIcon.png  # Use custom icon instead of auto-extraction
  Processor: com.github.fleet.FleetImporter/FleetImporter
```

## Common Tasks

### Creating New Recipes
- **Use the Template**: Start with `_templates/Template.fleet.recipe.yaml` as the base for all new recipes
- **Follow the Style Guide**: All new recipes must follow the formatting and naming conventions in `CONTRIBUTING.md` - see the "Style Guide" section for complete requirements
- Copy the template to your vendor directory: `cp _templates/Template.fleet.recipe.yaml VendorName/SoftwareName.fleet.recipe.yaml`
- Update the recipe metadata:
  - `Description`: Brief description of what the recipe does
  - `Identifier`: Follow pattern `com.github.fleet.SoftwareName`
  - `ParentRecipe`: Point to upstream AutoPkg recipe (e.g., `com.github.homebysix.pkg.SoftwareName`)
- Customize Input variables:
  - `NAME`: Software display name
  - `CATEGORIES`: Add appropriate categories for self-service
  - `ICON`: Leave empty for automatic extraction, or specify custom icon path
  - Adjust other optional variables as needed
- Set mode-specific defaults:
  - `GITOPS_MODE`: Set to `false` for direct mode by default
  - `FLEET_GITOPS_SOFTWARE_DIR` and `FLEET_GITOPS_TEAM_YAML_PATH`: Keep defaults unless you have specific requirements
- **Update PARENT_RECIPE_DEPENDENCIES.md**: If the recipe uses a parent from a repository not already listed in PARENT_RECIPE_DEPENDENCIES.md, add it to the documentation
  - Check the parent recipe's repository using `autopkg info <parent-recipe-id>`
  - Trace the full dependency chain (pkg recipes often depend on download recipes from other repos)
  - Add new repositories to both the "Quick Setup" section and the detailed repository list
- Test with `autopkg run VendorName/SoftwareName.fleet.recipe.yaml -v`
- All mode-specific credentials (API tokens, AWS keys, etc.) come from AutoPkg preferences or environment variables, NOT from the recipe Input section

### Modifying the Processor
- Edit `FleetImporter/FleetImporter.py`
- Validate syntax: `python3 -m py_compile FleetImporter/FleetImporter.py`
- Test import: `python3 -c "import sys; sys.path.insert(0, '.'); from FleetImporter.FleetImporter import FleetImporter"`
- Test with sample recipe on macOS

### Local Development Workflow
1. Make changes to processor or recipes
2. Validate Python syntax
3. Test YAML parsing
4. On macOS: Run autopkg with test recipe
5. Inspect generated branch and YAML files
6. Commit changes

## Timing Expectations

- Python dependency installation: 10-30 seconds
- AutoPkg installation (download + install .pkg): 1-2 minutes -- NEVER CANCEL
- AutoPkg repo addition: 30-60 seconds each -- NEVER CANCEL
- Recipe execution (full build): 5-15 minutes -- NEVER CANCEL. Set timeout to 30+ minutes
- Python syntax validation: < 1 second (measured: 0 seconds)
- YAML validation: < 1 second (measured: 0 seconds)
- Git operations: < 5 seconds (measured: 0 seconds)
- Batch YAML validation: < 1 second (measured: 0 seconds)
- Environment variable setup: < 1 second

## Platform Requirements

### macOS (Full Functionality)
- Required for AutoPkg execution
- Install AutoPkg from GitHub releases (no Homebrew required)
- All features available

### Linux/Windows (Limited)
- Can validate Python syntax and YAML
- Can test Git operations
- Cannot run AutoPkg recipes
- Useful for CI/CD validation

## Security Notes

- Never commit tokens or secrets to repository
- Use environment variables for sensitive data
- Set `GIT_TERMINAL_PROMPT=0` to prevent interactive authentication
- Tokens should have minimal required permissions
- Rotate Fleet API tokens periodically

## Troubleshooting

### Common Issues
- **AutoPkg not found**: Download and install from https://github.com/autopkg/autopkg/releases/latest (macOS only)
- **Python import errors**: For development tools: `pip install black isort flake8 flake8-bugbear PyYAML`
- **YAML syntax errors**: Validate with `python3 -c "import yaml; yaml.safe_load(open('file.yaml'))"`
- **Git authentication**: Set `FLEET_GITOPS_GITHUB_TOKEN` environment variable
- **Fleet API errors**: Verify `FLEET_API_TOKEN` and Fleet server URL

### Debug Commands
- `autopkg version` - Check AutoPkg installation
- `python3 --version` - Verify Python 3.9+
- `git --version` - Check Git availability
- `python3 -c "import yaml"` - Test YAML module availability

## Integration Details

### Fleet Integration
- Uploads .pkg files to Fleet software management
- Creates software YAML configurations
- Manages team-based software deployment

### GitOps Workflow
- Creates feature branches for software updates
- Updates team YAML configurations
- Opens pull requests for review
- Maintains idempotent operations

### GitHub Actions
- Runs on `macos-latest` runners
- Requires `contents: write` and `pull-requests: write` permissions
- Uses scheduled triggers for automated updates
- Supports manual dispatch for testing

## Common Command Outputs

### Repository Structure
```
ls -la
total 68
drwxr-xr-x 3 runner runner  4096 Sep 17 22:57 .
drwxr-xr-x 3 runner runner  4096 Sep 17 22:57 ..
drwxrwxr-x 7 runner runner  4096 Sep 17 22:57 .git
-rw-rw-r-- 1 runner runner   267 Sep 17 22:57 .gitignore
drwxr-xr-x 2 runner runner  4096 Sep 17 22:57 Anthropic
drwxr-xr-x 2 runner runner  4096 Sep 17 22:57 Caffeine
drwxr-xr-x 2 runner runner  4096 Sep 17 22:57 FleetImporter
drwxr-xr-x 2 runner runner  4096 Sep 17 22:57 GitHub
drwxr-xr-x 2 runner runner  4096 Sep 17 22:57 GPGSuite
drwxr-xr-x 2 runner runner  4096 Sep 17 22:57 Raycast Technologies
drwxr-xr-x 2 runner runner  4096 Sep 17 22:57 Signal
-rw-rw-r-- 1 runner runner 13740 Sep 17 22:57 README.md
```

### Python Dependencies Check
```
python3 -c "import yaml, urllib.request, json; print('Dependencies OK')"
Dependencies OK
```

### Git Status (Clean)
```
git status
On branch main
Your branch is up to date with 'origin/main'.
nothing to commit, working tree clean
```

### Environment Variables Setup
```
export FLEET_API_BASE="https://fleet.example.com"
export FLEET_API_TOKEN="your-fleet-token"
export FLEET_TEAM_ID="1"
export FLEET_GITOPS_GITHUB_TOKEN="your-github-token"
export AWS_S3_BUCKET="your-fleet-packages-bucket"
export AWS_CLOUDFRONT_DOMAIN="d1234567890abc.cloudfront.net"
export FLEET_GITOPS_REPO_URL="https://github.com/org/fleet-gitops.git"
export GIT_TERMINAL_PROMPT=0
```

## Quick Reference Commands

### Immediate Validation (Run These First)
```bash
python3 --version                                    # Should be 3.9+
/Library/AutoPkg/Python3/Python.framework/Versions/Current/bin/python3 -c "import yaml, urllib.request, json; print('Dependencies OK')"  # Test AutoPkg Python modules
python3 -m py_compile FleetImporter/FleetImporter.py # Validate syntax
git --version                                        # Check Git availability
```

### Full Validation Sequence
```bash
# Environment setup
export FLEET_GITOPS_GITHUB_TOKEN="your-token"
export FLEET_API_TOKEN="your-fleet-token"
export GIT_TERMINAL_PROMPT=0

# Validate all components
python3 -m py_compile FleetImporter/FleetImporter.py
python3 -c "import yaml; [yaml.safe_load(open(f)) for f in ['GitHub/GithubDesktop.fleet.direct.recipe.yaml', 'GitHub/GithubDesktop.fleet.gitops.recipe.yaml']]"
git status && git log --oneline -5
```

## References

- [AutoPkg Documentation](https://github.com/autopkg/autopkg/wiki) - Official AutoPkg wiki and documentation
- [AutoPkg Source Code](https://github.com/autopkg/autopkg) - AutoPkg main repository and source code
- Fleet GitOps YAML software docs: https://fleetdm.com/docs/configuration/yaml-files#software
- Fleet API documentation for software management integration: https://fleetdm.com/docs/rest-api/rest-api#software
- Fleet source code: https://github.com/fleetdm/fleet