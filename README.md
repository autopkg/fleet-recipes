# FleetImporter AutoPkg Processor

Upload a freshly built installer to Fleet using the Software API, then create or update the corresponding YAML in your Fleet GitOps repo and open a pull request. This processor is designed for CI use in GitHub Actions and can also be run locally.

> **⚠️ Experimental:** This processor uses Fleet's [experimental software management API](https://fleetdm.com/docs/rest-api/rest-api#list-software), which is subject to breaking changes. Fleet may introduce API changes that require corresponding updates to this processor. **Production use is not recommended** due to the experimental nature of the underlying Fleet API.

## Current Limitations

- Fleet's API does not yet support searching for existing packages by hash. The processor therefore cannot determine if a package has already been uploaded without attempting an upload. When Fleet returns a `409` conflict (package already exists), the processor exits gracefully without performing GitOps operations. A feature request to add hash-based lookups is being tracked in [fleetdm/fleet#32965](https://github.com/fleetdm/fleet/issues/32965).

---

## Features

- Uploads a `.pkg` to Fleet for a specific team
- Creates a feature branch named `<software-title>-<version>`
- Writes or updates a per-title software YAML file in `lib/macos/software`
- Ensures the team YAML references that software file in `software.packages`
- Commits, pushes, and opens a GitHub pull request
- Idempotent where practical and fails loudly on API errors

---

## Requirements

- **macOS**: Required for AutoPkg execution
- **Python 3.9+**: For the FleetImporter processor
- **AutoPkg 2.7+**: For recipe processing
- **Git**: For GitOps repository operations
- **Fleet API Access**: Fleet server v4.74.0+ with software management permissions
- **GitHub Access**: Personal access token with `repo` and `pull-requests` permissions

---

## Why YAML?

AutoPkg [supports both XML (plist) and YAML recipe formats](https://github.com/autopkg/autopkg/wiki/Recipe-Format#overview). I personally find YAML more readable and maintainable than XML, especially for recipes that may be edited by hand or reviewed in code. YAML's indentation and lack of angle brackets make it easier to scan and less error-prone for most users.

Additionally, Fleet's GitOps workflow is driven by YAML files for software configuration and team assignments. By using YAML for both AutoPkg recipes and Fleet GitOps files, this repository maintains consistency and makes it easier to reason about the entire workflow. Aligning with Fleet's format also reduces friction when integrating new tools or automations.

---

## Recipe Configuration

### Environment Variable Configuration

All recipe arguments use environment variables for maximum flexibility. The processor provides sensible defaults for optional arguments, so you only need to set the variables relevant to your environment.

**Required Environment Variables:**
```bash
FLEET_API_BASE="https://fleet.myorg.com"
FLEET_API_TOKEN="your-fleet-token"
FLEET_TEAM_ID="1"
FLEET_GITOPS_REPO_URL="https://github.com/myorg/fleet-gitops"
FLEET_GITOPS_GITHUB_TOKEN="your-github-token"
FLEET_GITOPS_AUTHOR_EMAIL="autopkg-bot@myorg.com"
FLEET_TEAM_YAML_PATH="teams/workstations.yml"
```

### Argument Order Convention

All recipe arguments use environment variables and are organized in logical groups:

1. **Parent recipe requirements** - Special arguments needed by upstream recipes (e.g., `%GITHUB_DESKTOP_BUILD%`)
2. **Core package info** - `%pkg_path%`, `%NAME%`, `%version%` (inherited from parent recipe)
3. **Fleet API configuration** - `%FLEET_API_BASE%`, `%FLEET_API_TOKEN%`, `%FLEET_TEAM_ID%`
4. **Software configuration** - `%FLEET_PLATFORM%`, `%FLEET_SOFTWARE_SLUG%`, install behavior
5. **Git/GitHub configuration** - Repository URLs, tokens, branch, author info
6. **GitOps file paths** - Team YAML path, software directory, path prefixes/suffixes
7. **Optional features** - Branch prefix, PR labels, reviewer assignment

The processor provides sensible defaults for most optional arguments, so you typically only need to set 7-10 environment variables for your entire AutoPkg setup.

---

## Inputs


All inputs can be provided as AutoPkg variables in your recipe or via `-k` overrides.

| Name | Required | Type | Description |
|------|----------|------|-------------|
| `pkg_path` | Yes | str | Path to the built `.pkg` file. |
| `software_title` | Yes | str | Human readable title, for example `Firefox`. |
| `version` | Yes | str | Version string used in YAML and branch name. |
| `fleet_api_base` | Yes | str | Fleet base URL, for example `https://fleet.example.com`. |
| `fleet_api_token` | Yes | str | Fleet API token. |
| `team_id` | Yes | int | Fleet Team ID for the upload. |
| `git_repo_url` | Yes | str | HTTPS URL of your Fleet GitOps repo. |
| `team_yaml_path` | Yes | str | Path to team YAML in repo, for example `teams/workstations.yml`. |
| `github_repo` | Yes | str | `owner/repo` for PR creation. |
| `platform` | No | str | Defaults to `darwin`. Accepts `darwin`, `windows`, `linux`, `ios`, `ipados`. |
| `self_service` | No | bool | Make available in self service. Default `true`. |
| `automatic_install` | No | bool | On macOS, create automatic install policy. Default `false`. |
| `labels_include_any` | No | list[str] | Labels required for targeting. Only one of include or exclude may be set. |
| `labels_exclude_any` | No | list[str] | Labels to exclude from targeting. |
| `install_script` | No | str | Optional install script contents. |
| `uninstall_script` | No | str | Optional uninstall script contents. |
| `pre_install_query` | No | str | Optional osquery condition. |
| `post_install_script` | No | str | Optional post install script contents. |
| `git_base_branch` | No | str | Base branch to branch from and open PR to. Default `main`. |
| `git_author_name` | No | str | Commit author name. Default `autopkg-bot`. |
| `git_author_email` | No | str | Commit author email. Default `autopkg-bot@example.com`. |
| `software_dir` | No | str | Directory for per title YAML. Default `lib/macos/software`. |
| `package_yaml_suffix` | No | str | Suffix for per title YAML. Default `.yml`. |
| `team_yaml_package_path_prefix` | No | str | Path prefix used inside team YAML. Default `../lib/macos/software/`. |
| `github_token` | No | str | GitHub token. If empty, uses `FLEET_GITOPS_GITHUB_TOKEN` env. When set, the processor rewrites the repo URL with the token so `git clone` and `git push` authenticate without prompts. |
| `pr_labels` | No | list[str] | Labels to set on the PR. |
| `PR_REVIEWER` | No | str | GitHub username to assign as PR reviewer. |
| `software_slug` | No | str | Override slug used for file and branch names. Defaults to normalized `software_title`. |
| `branch_prefix` | No | str | Optional prefix for branch names, for example `autopkg`. |

---

## YAML Format

This processor uses Fleet's v4.74.0+ YAML format where targeting keys (`self_service`, `labels_include_any`, `labels_exclude_any`) are stored in the team YAML software section, not in individual package YAML files.

**Package YAML Structure:**

```yaml
name: "Firefox"
version: "129.0.2"
platform: "darwin"
hash_sha256: "abc123..."         # if provided by Fleet response
automatic_install: false        # optional macOS only
pre_install_query:               # optional
  query: "SELECT 1;"
install_script:                  # optional
  contents: |
    #!/bin/bash
    echo "custom install"
uninstall_script:                # optional
  contents: |
    #!/bin/bash
    echo "custom uninstall"
post_install_script:             # optional
  contents: |
    #!/bin/bash
    echo "post"
```

**Team YAML Reference:**

Package reference with targeting metadata in `teams/workstations.yml`:

```yaml
software:
  packages:
    - path: ../lib/macos/software/firefox.package.yml
      self_service: true
      labels_include_any:
        - "Workstations"
```

---

## Outputs

| Name | Description |
|------|-------------|
| `fleet_title_id` | Fleet software title ID returned by the upload API. |
| `fleet_installer_id` | Fleet installer ID returned by the upload API. |
| `git_branch` | Created branch name. |
| `pull_request_url` | URL of the created or found pull request. |
| `hash_sha256` | SHA-256 hash of the uploaded package, as returned by Fleet. |

---

---

## Example AutoPkg Recipe Integration

Add the processor after your build step. Example excerpt from a YAML recipe:

```yaml
Process:
- Arguments:
    # Parent recipe requirements
    pkg_path: '%pkg_path%'
    
    # Core package info (from parent recipe)
    software_title: '%NAME%'
    version: '%version%'
    
    # Fleet API configuration
    fleet_api_base: '%FLEET_API_BASE%'
    fleet_api_token: '%FLEET_API_TOKEN%'
    team_id: '%FLEET_TEAM_ID%'
    
    # Software configuration
    self_service: true
    
    # Git/GitHub configuration
    git_repo_url: '%FLEET_GITOPS_REPO_URL%'
    github_token: '%FLEET_GITOPS_GITHUB_TOKEN%'
    
    # GitOps file paths
    team_yaml_path: '%FLEET_TEAM_YAML_PATH%'
    
    # Optional features
    skip_pkg_upload: false
    verbose_mode: true
  Processor: FleetImporter
```

---

## Behavior and Idempotency

- If the team YAML already references the package file, the processor does not add a duplicate.
- If the per title YAML exists, it is updated in place.
- If there are no changes to commit, the job exits cleanly without pushing a branch or creating a PR.
- Only one of `labels_include_any` or `labels_exclude_any` may be set. The processor enforces this.

---

## Permissions

- Fleet API token must allow software uploads scoped to the target team.
- GitHub token must be able to push branches to the GitOps repo and open PRs.

---

## Troubleshooting

- **401 or 403 from Fleet**  
  Verify `fleet_api_base`, token value, and that the token has rights to upload for `team_id`.

- **400 from Fleet on upload**  
  Check that the file is a valid installer for the chosen platform. For `.pkg` you can omit custom scripts unless you need overrides.

- **Git failure on push**  
  Ensure the token used by Actions can push to the repo. Check branch protection rules and required status checks. If you block direct pushes to branches that do not exist yet, create an exception for the bot or switch to a service account PAT.

- **Labels error in GitOps sync**  
  Fleet GitOps requires that labels referenced in software YAML exist in your GitOps configuration. Add missing labels or remove them from the package YAML.

- **422 on PR creation**  
  This indicates a PR already exists. The processor searches for an open PR with the same head and base and returns that URL.

- **Nothing to commit**  
  If the YAML already matches the intended state, there will be no diff. This is normal. The processor will exit cleanly without creating a branch or PR.

---

## Security Notes

- When a GitHub token is provided, the processor rewrites the Git repository URL with the token so that cloning and pushing use authenticated HTTPS URLs without prompts. `GIT_TERMINAL_PROMPT` is set to `0` to prevent interactive authentication.
- Consider scoping the GitHub token to the target repo only.
- Rotate API tokens periodically.

---

## Conventions

- Branch name format: `<software-slug>-<version>` or `<branch_prefix>/<software-slug>-<version>` if `branch_prefix` is set.
- Per title YAML default directory: `lib/macos/software`. Override via `software_dir` if your repo uses a different layout.
- Team YAML reference uses a relative `path` entry. Adjust `team_yaml_package_path_prefix` if your repo structure differs.

---

## FAQ

**Q: Can it skip creating a PR and push directly to main?**  
Branch and PR is deliberate. If you want direct commits, you can set the base and head to the same branch and adjust the code. That is not recommended for audited changes.

**Q: What about label management?**  
This processor assumes labels already exist in GitOps. Managing label creation is out of scope to keep changes atomic and reviewable.

---

## References

- AutoPkg Processors: https://github.com/autopkg/autopkg/wiki/Processors  
- Fleet GitOps YAML software docs: https://fleetdm.com/docs/configuration/yaml-files#software  
- Fleet example team YAML and per title examples:  
  - Team file pattern similar to `teams/workstations.yml`  
  - Per title example similar to `lib/macos/software/*.yml`

---

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.
