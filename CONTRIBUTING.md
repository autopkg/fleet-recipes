# Contributing to FleetImporter

Thank you for your interest in contributing! Recipe additions and processor enhancements from the community are welcome.

## Ways to Contribute

### Become a Maintainer

I am actively looking for 2-3 additional maintainers to help maintain this repository and ensure it doesn't become dependent on a single person. Maintainers help with:

- Reviewing and merging pull requests
- Testing new recipes and processor changes
- Triaging issues and providing support
- Maintaining code quality and documentation
- Planning future enhancements

**Interested in becoming a maintainer?** Contact [@kitzy](https://macadmins.slack.com/team/U04QVKUR4) on the [MacAdmins Slack](https://macadmins.org/slack) to discuss. 

---

### Adding New Recipes

We encourage contributions of AutoPkg recipes for additional macOS software. All recipes use a **combined format** that supports both direct mode and GitOps mode in a single file.

**Use the template**: Start with `_templates/Template.fleet.recipe.yaml` as the base for all new recipes.

See the existing recipes in this repository for examples (Claude, Caffeine, GitHub Desktop, etc.).

#### Recipe Requirements

- Start from `_templates/Template.fleet.recipe.yaml` template
- Follow the established naming convention: `SoftwareName.fleet.recipe.yaml`
- Include appropriate categories from Fleet's supported list:
  - Browsers
  - Communication
  - Developer tools
  - Productivity
- Use automatic icon extraction (default behavior when `ICON: ""`)
- Use consistent formatting with existing recipes
- Reference an existing AutoPkg parent recipe that produces a `.pkg` file
- **Update [PARENT_RECIPE_DEPENDENCIES.md](PARENT_RECIPE_DEPENDENCIES.md)** if your recipe introduces a new parent repository not already listed

#### Recipe Structure

Place recipes in a folder named after the software vendor:

```
VendorName/
└── SoftwareName.fleet.recipe.yaml
```

## Style Guide

Recipes in this repository follow consistent formatting and naming conventions to ensure maintainability and predictability.

### Filename

Recipe filenames should follow the pattern:
- `<SoftwareName>.fleet.recipe.yaml` - Combined recipe supporting both modes

Where `<SoftwareName>` matches the `NAME` input variable used throughout the recipe chain.

### Vendor Folder

Each recipe resides in a subfolder named after the software vendor or publisher:
- Use the official company/vendor name (e.g., `GitHub`, `Anthropic`, `Signal`)
- Manual icon files (rarely needed) should use the software name as a prefix
- No spaces in folder names; use proper capitalization

### Parent Recipe

The recipe's `ParentRecipe` must be:
- Publicly available via a shared AutoPkg repository
- Part of the AutoPkg organization or well-established community repos
- Produces a standard Apple package (`.pkg`) file

### Identifier

Recipe identifiers should follow the pattern `com.github.fleet.<SoftwareName>`.

### Processing

Recipes should have a single processor stage: `FleetImporter`.

All arguments should be capable of being overridden by `Input` section variables using uppercase names with underscores (e.g., `%FLEET_API_BASE%`, `%SOFTWARE_TITLE%`).

### Required Arguments

All recipes must include these arguments in the `Input` section:
- `NAME`: Software display name (consistent with parent recipe)
- `self_service` must be set to `true`
- `automatic_install` must be set to `false`
- `categories`: At least one category (required when `self_service: true`)
- `gitops_mode`: Set to `false` by default (users can override to enable GitOps)
- GitOps-specific paths:
  - `FLEET_GITOPS_SOFTWARE_DIR` must be set to `lib/macos/software`
  - `FLEET_GITOPS_TEAM_YAML_PATH` must be set to `teams/workstations.yml`
- Auto-update policy automation (optional feature):
  - `AUTO_UPDATE_ENABLED`: Set to `false` by default (users can override to enable)
  - `AUTO_UPDATE_POLICY_NAME`: Set to `autopkg-auto-update-%NAME%` template

**Note:** Mode-specific credentials (API tokens, AWS keys, etc.) come from AutoPkg preferences or environment variables, NOT from the recipe Input section.

### Auto-Update Policies

As of the latest release, FleetImporter supports automatic creation of Fleet policies for version detection and automatic updates. This feature is:

- **Optional**: Disabled by default (`AUTO_UPDATE_ENABLED: false`)
- **User-controlled**: Users enable via recipe overrides or AutoPkg preferences
- **Backward compatible**: Existing recipes work without changes

#### Requirements for New Recipes

All new recipes must include the auto-update inputs in the template format:

```yaml
Input:
  NAME: Software Name
  self_service: true
  automatic_install: false
  categories:
  - Developer tools
  
  # Optional: Auto-update policy automation
  AUTO_UPDATE_ENABLED: false
  AUTO_UPDATE_POLICY_NAME: "autopkg-auto-update-%NAME%"
  
  gitops_mode: false
```

The inputs must also be passed to the FleetImporter processor arguments:

```yaml
Process:
- Arguments:
    # ... other arguments ...
    
    # Optional: Auto-update policy automation
    auto_update_enabled: "%AUTO_UPDATE_ENABLED%"
    auto_update_policy_name: "%AUTO_UPDATE_POLICY_NAME%"
    
  Processor: com.github.fleet.FleetImporter/FleetImporter
```

#### How Auto-Update Works

When `AUTO_UPDATE_ENABLED` is set to `true`:

1. **Version Detection**: Creates osquery SQL that detects hosts running outdated versions:
   ```sql
   SELECT * FROM programs WHERE name = 'Software Name' AND version != 'X.Y.Z'
   ```

2. **Policy Creation**:
   - Direct mode: Uses Fleet API to create/update policy with automatic installation
   - GitOps mode: Creates policy YAML file in `lib/policies/` directory

3. **Automatic Installation**: Policy failure triggers self-service installation of the latest version

See README.md for complete documentation on auto-update functionality.

### Categories

Use only these supported Fleet categories:
- `Browsers`
- `Communication`
- `Developer tools`
- `Productivity`

### Icons

Recipes should use automatic icon extraction (the default behavior):
- FleetImporter automatically extracts icons from .pkg files when `ICON: ""`
- No manual icon file needed in most cases
- Icons are extracted from the .app bundle, converted to PNG, and compressed to meet Fleet's 100 KB limit

Only include a manual icon file if automatic extraction is not technically possible:
- Must be PNG format
- Square dimensions between 120x120px and 1024x1024px
- Less than 100KB filesize (Fleet requirement)
- Named `<SoftwareName>.png`
- Referenced in recipe as `ICON: <SoftwareName>.png`

### Custom Scripts

Recipes can include custom install, uninstall, and post-install scripts. For maintainability and readability:

**Use separate script files when:**
- Script is longer than 3-5 lines
- Script contains complex logic or multiple operations
- Script may be reused or referenced by other recipes

**Use inline scripts when:**
- Script is very short (1-2 lines)
- Script is simple and self-explanatory

**Script file guidelines:**
- Store script files in the same vendor directory as the recipe (e.g., `VendorName/uninstall-softwarename.sh`)
- Use descriptive filenames: `install-<softwarename>.sh`, `uninstall-<softwarename>.sh`, etc.
- Include a shebang line (`#!/bin/bash`) at the top of the script
- Add comments explaining what the script does
- Reference in recipe using relative path: `UNINSTALL_SCRIPT: uninstall-softwarename.sh`

**Example with script file:**
```yaml
Input:
  UNINSTALL_SCRIPT: uninstall-elgato-stream-deck.sh
```

**Example with inline script (simple case):**
```yaml
Input:
  POST_INSTALL_SCRIPT: |
    #!/bin/bash
    echo "Installation complete"
```

### YAML Formatting

- Use 2-space indentation
- Quote string values consistently
- Use array format for lists (categories, labels)
- Validate YAML syntax before submitting

### Linting

All recipes must pass YAML validation:
```bash
python3 -c "import yaml; yaml.safe_load(open('Recipe.yaml'))"
```

### Enhancing the Processor

Improvements to `FleetImporter.py` are welcome, including:

- Bug fixes
- New features that align with Fleet's API capabilities
- Performance improvements
- Better error handling and logging
- Additional configuration options

#### Code Style Requirements

All Python code must pass AutoPkg's code style requirements before submission:

```bash
# Install development dependencies
python3 -m pip install black isort flake8 flake8-bugbear

# Format code
python3 -m black FleetImporter/FleetImporter.py
python3 -m isort FleetImporter/FleetImporter.py

# Validate (all must pass)
python3 -m py_compile FleetImporter/FleetImporter.py
python3 -m black --check --diff FleetImporter/FleetImporter.py
python3 -m isort --check-only --diff FleetImporter/FleetImporter.py
python3 -m flake8 FleetImporter/FleetImporter.py
```

## Submitting Changes

### Before You Submit

1. **Test your changes**: Run recipes locally to ensure they work
2. **Validate YAML**: Ensure all recipe files are valid YAML
3. **Run code checks**: For processor changes, pass all style checks
4. **Update documentation**: Add or update README sections as needed

### Using Pre-Commit Hooks

This repository includes pre-commit hooks that automatically validate AutoPkg recipes before commits. Using pre-commit is optional but highly recommended to catch issues early.

For details on using pre-commit with AutoPkg, see [Using pre-commit to validate AutoPkg recipes](https://www.elliotjordan.com/posts/pre-commit-02-autopkg/).

To enable pre-commit:

1. **Install pre-commit** (if not already installed):
   ```bash
   brew install pre-commit
   ```

2. **Activate the hooks** in your cloned repository:
   ```bash
   cd /path/to/fleet-recipes
   pre-commit install
   ```

Once installed, the hooks will automatically run when you attempt to commit changes. You can also manually run the checks on all files:

```bash
pre-commit run --all-files
```

The pre-commit configuration checks for:
- Valid AutoPkg recipe format and structure
- Prevention of AutoPkg overrides (`.recipe` files in recipe repos)
- Prevention of AutoPkg trust info files

### Pull Request Process

1. Fork the repository
2. Create a feature branch from `main`
3. Make your changes following the guidelines above
4. Ensure all tests pass in GitHub Actions
5. Submit a pull request with a clear description of your changes

### Pull Request Guidelines

- **Title**: Use a descriptive title (e.g., "Add Firefox recipes" or "Fix error handling in package upload")
- **Description**: Explain what changes you made and why
- **Testing**: Describe how you tested your changes
- **Related Issues**: Link to any related issues or discussions

## Questions or Ideas?

- Open an [issue](https://github.com/kitzy/fleetimporter/issues) for questions or feature requests
- Check existing issues and pull requests before starting work
- Ask for help in the [#autopkg channel](https://macadmins.slack.com/archives/C056155B4) on MacAdmins Slack
- Feel free to ask for help or clarification

## Code of Conduct

Be respectful and constructive in all interactions. This is a community project, and we appreciate your contributions!

## License

By contributing, you agree that your contributions will be licensed under the same license as the project (see [LICENSE](LICENSE)).
