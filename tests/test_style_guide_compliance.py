#!/usr/bin/env python3
"""
Test suite to validate that all recipes comply with the style guide requirements
defined in CONTRIBUTING.md.

This validates:
1. Filename conventions (.fleet.recipe.yaml for combined recipes)
2. Identifier patterns (com.github.fleet.<SoftwareName>)
3. Single processor stage (FleetImporter only)
4. NAME variable exists in Input section
5. self_service (or SELF_SERVICE for legacy) must be set to true
6. automatic_install (or AUTOMATIC_INSTALL for legacy) must be set to false
7. categories (or CATEGORIES for legacy) required when self_service is true
8. gitops_mode (or GITOPS_MODE for legacy) variable exists in combined recipes (defaults to false)
9. FLEET_GITOPS_SOFTWARE_DIR must be set to "lib/macos/software"
10. FLEET_GITOPS_TEAM_YAML_PATH must be set to "teams/workstations.yml"
11. Categories use only supported values
12. Process arguments: lowercase Input variables auto-pass (preferred) or use %UPPERCASE% (legacy)
13. Vendor folder structure
14. Only one of labels_include_any/labels_exclude_any (or LABELS_* for legacy) can be set

Note: The validator accepts both lowercase (preferred for AutoPkg type preservation)
and UPPERCASE (legacy) variable naming conventions.
"""

import glob
import os
import sys

import yaml


class StyleGuideValidator:
    """Validates recipe files against style guide requirements."""

    # Supported Fleet categories from style guide
    SUPPORTED_CATEGORIES = {
        "Browsers",
        "Communication",
        "Developer tools",
        "Productivity",
    }

    def __init__(self):
        self.errors = []
        self.warnings = []
        self.recipe_count = 0
        self.combined_count = 0
        self.legacy_count = 0

    def validate_all_recipes(self):
        """Find and validate all recipe files."""
        recipe_files = glob.glob("**/*.recipe.yaml", recursive=True)
        # Exclude FleetImporter directory and template files
        recipe_files = [
            f
            for f in recipe_files
            if "FleetImporter" not in f and "_templates" not in f
        ]

        print(f"=== Style Guide Compliance Validation ===")
        print(f"Found {len(recipe_files)} recipe files to validate\n")

        for recipe_file in sorted(recipe_files):
            self.validate_recipe(recipe_file)

        return self.report_results()

    def validate_recipe(self, recipe_path):
        """Validate a single recipe file."""
        self.recipe_count += 1
        print(f"📋 Validating: {recipe_path}")

        # Validate filename convention
        self.validate_filename(recipe_path)

        # Validate vendor folder structure
        self.validate_vendor_folder(recipe_path)

        # Parse YAML and validate syntax
        try:
            with open(recipe_path, "r") as f:
                data = yaml.safe_load(f)
            print(f"   ✅ YAML syntax: Valid")
        except yaml.YAMLError as e:
            self.errors.append(f"{recipe_path}: YAML syntax error - {e}")
            print(f"   ❌ YAML syntax: Invalid - {e}")
            return
        except Exception as e:
            self.errors.append(f"{recipe_path}: Failed to parse YAML - {e}")
            print(f"   ❌ YAML parsing: Failed - {e}")
            return

        # Validate required AutoPkg recipe fields
        self.validate_required_fields(recipe_path, data)

        # Determine recipe type from filename
        is_combined = (
            ".fleet.recipe.yaml" in recipe_path
            and ".direct." not in recipe_path
            and ".gitops." not in recipe_path
        )
        is_legacy_direct = ".fleet.direct.recipe.yaml" in recipe_path
        is_legacy_gitops = ".fleet.gitops.recipe.yaml" in recipe_path

        if is_combined:
            self.combined_count += 1
        elif is_legacy_direct or is_legacy_gitops:
            self.legacy_count += 1
            self.warnings.append(
                f"{recipe_path}: Using legacy recipe format. Consider migrating to combined format (.fleet.recipe.yaml)"
            )

        # Validate identifier pattern
        self.validate_identifier(
            recipe_path, data, is_combined, is_legacy_direct, is_legacy_gitops
        )

        # Validate single processor stage
        self.validate_single_processor(recipe_path, data)

        # Validate Input section
        input_section = data.get("Input", {})
        if not input_section:
            self.errors.append(f"{recipe_path}: Missing Input section")
            return

        # Validate NAME exists
        self.validate_name(recipe_path, input_section)

        # Validate SELF_SERVICE requirement
        self.validate_self_service(recipe_path, input_section)

        # Validate AUTOMATIC_INSTALL requirement
        self.validate_automatic_install(recipe_path, input_section)

        # Validate GITOPS_MODE exists for combined recipes
        if is_combined:
            self.validate_gitops_mode(recipe_path, input_section)

        # Validate GitOps-specific paths (only for combined and legacy GitOps recipes)
        if is_combined or is_legacy_gitops:
            self.validate_gitops_software_dir(recipe_path, input_section)
            self.validate_gitops_team_yaml_path(recipe_path, input_section)

        # Validate categories requirement (when self_service is true)
        self.validate_categories_requirement(recipe_path, input_section)

        # Validate categories values (if present)
        self.validate_categories(recipe_path, input_section)

        # Validate label targeting (only one of include/exclude)
        self.validate_label_targeting(recipe_path, input_section)

        # Validate Process section arguments
        process_list = data.get("Process", [])
        if process_list and len(process_list) > 0:
            args = process_list[0].get("Arguments", {})
            self.validate_process_arguments(recipe_path, args, is_combined)

        print(f"   ✅ Validation complete\n")

    def validate_filename(self, recipe_path):
        """Validate filename follows convention: <SoftwareName>.fleet.recipe.yaml or legacy formats"""
        filename = os.path.basename(recipe_path)

        # Check for combined recipe format (preferred)
        is_combined = (
            filename.endswith(".fleet.recipe.yaml")
            and ".direct." not in filename
            and ".gitops." not in filename
        )
        # Check for legacy formats
        is_legacy = filename.endswith(".fleet.direct.recipe.yaml") or filename.endswith(
            ".fleet.gitops.recipe.yaml"
        )

        if not (is_combined or is_legacy):
            self.errors.append(
                f"{recipe_path}: Filename must end with .fleet.recipe.yaml (preferred) or legacy .fleet.direct/gitops.recipe.yaml"
            )
            print(
                f"   ❌ Filename convention: Invalid (must be .fleet.recipe.yaml or .fleet.direct/gitops.recipe.yaml)"
            )
        elif is_combined:
            print(f"   ✅ Filename convention: {filename} (combined format)")
        else:
            mode = "direct" if ".fleet.direct." in filename else "gitops"
            print(
                f"   ⚠️  Filename convention: {filename} (legacy {mode} format - consider migrating to combined)"
            )

    def validate_vendor_folder(self, recipe_path):
        """Validate recipe is in a vendor folder (not at root)."""
        path_parts = recipe_path.split(os.sep)

        # Should be VendorName/RecipeFile.yaml, so at least 2 parts
        if len(path_parts) < 2:
            self.errors.append(
                f"{recipe_path}: Recipe must be in a vendor folder (e.g., VendorName/Recipe.yaml)"
            )
            print(f"   ❌ Vendor folder: Recipe at root (must be in vendor subfolder)")
        else:
            vendor_folder = path_parts[-2]
            # Check for spaces in folder name
            if " " in vendor_folder:
                self.errors.append(
                    f"{recipe_path}: Vendor folder '{vendor_folder}' contains spaces"
                )
                print(f"   ❌ Vendor folder: '{vendor_folder}' (no spaces allowed)")
            else:
                print(f"   ✅ Vendor folder: {vendor_folder}")

    def validate_required_fields(self, recipe_path, data):
        """Validate required AutoPkg recipe fields exist."""
        required_fields = ["Description", "Identifier", "Input", "Process"]
        missing = [field for field in required_fields if field not in data]

        if missing:
            self.errors.append(
                f"{recipe_path}: Missing required AutoPkg fields: {missing}"
            )
            print(f"   ❌ Required fields: Missing {missing}")
        else:
            print(
                f"   ✅ Required fields: All present (Description, Identifier, Input, Process)"
            )

    def validate_identifier(
        self, recipe_path, data, is_combined, is_legacy_direct, is_legacy_gitops
    ):
        """Validate identifier follows pattern: com.github.fleet.<SoftwareName> or legacy patterns"""
        identifier = data.get("Identifier", "")

        if not identifier:
            self.errors.append(f"{recipe_path}: Missing Identifier field")
            print(f"   ❌ Identifier: Missing")
            return

        expected_prefix = "com.github.fleet."
        if not identifier.startswith(expected_prefix):
            self.errors.append(
                f"{recipe_path}: Identifier must start with '{expected_prefix}', got '{identifier}'"
            )
            print(
                f"   ❌ Identifier: '{identifier}' (must start with '{expected_prefix}')"
            )
            return

        # Check identifier format
        has_direct_id = ".direct." in identifier
        has_gitops_id = ".gitops." in identifier
        has_mode_in_id = has_direct_id or has_gitops_id

        if is_combined:
            # Combined recipes should NOT have .direct. or .gitops. in identifier
            if has_mode_in_id:
                self.errors.append(
                    f"{recipe_path}: Combined recipe identifier should not contain '.direct.' or '.gitops.', got '{identifier}'"
                )
                print(
                    f"   ❌ Identifier: '{identifier}' (should be 'com.github.fleet.<SoftwareName>' for combined recipes)"
                )
            else:
                print(f"   ✅ Identifier: {identifier} (combined format)")
        elif is_legacy_direct:
            # Legacy direct recipes should have .direct. in identifier
            if not has_direct_id:
                self.errors.append(
                    f"{recipe_path}: Direct recipe identifier must contain '.direct.', got '{identifier}'"
                )
                print(
                    f"   ❌ Identifier: '{identifier}' (must contain '.direct.' for direct mode)"
                )
            else:
                print(f"   ✅ Identifier: {identifier} (legacy direct mode)")
        elif is_legacy_gitops:
            # Legacy gitops recipes should have .gitops. in identifier
            if not has_gitops_id:
                self.errors.append(
                    f"{recipe_path}: GitOps recipe identifier must contain '.gitops.', got '{identifier}'"
                )
                print(
                    f"   ❌ Identifier: '{identifier}' (must contain '.gitops.' for gitops mode)"
                )
            else:
                print(f"   ✅ Identifier: {identifier} (legacy gitops mode)")

    def validate_single_processor(self, recipe_path, data):
        """Validate recipe has single processor stage: FleetImporter."""
        process_list = data.get("Process", [])

        if not process_list:
            self.errors.append(f"{recipe_path}: Missing Process section")
            print(f"   ❌ Process section: Missing")
            return

        if len(process_list) != 1:
            self.warnings.append(
                f"{recipe_path}: Process has {len(process_list)} processors (style guide recommends single FleetImporter processor)"
            )
            print(
                f"   ⚠️  Process stages: {len(process_list)} (style guide recommends 1)"
            )
        else:
            print(f"   ✅ Process stages: 1 (single processor)")

        # Check that FleetImporter is present
        has_fleet_importer = False
        for item in process_list:
            if isinstance(item, dict):
                processor = item.get("Processor", "")
                if "FleetImporter" in processor:
                    has_fleet_importer = True
                    print(f"   ✅ Processor type: {processor}")
                    break

        if not has_fleet_importer:
            self.errors.append(
                f"{recipe_path}: FleetImporter processor not found in Process"
            )
            print(f"   ❌ Processor type: FleetImporter not found")

    def validate_name(self, recipe_path, input_section):
        """Validate NAME variable exists in Input section."""
        name = input_section.get("NAME")

        if name is None:
            self.errors.append(f"{recipe_path}: Missing NAME in Input section")
            print(f"   ❌ NAME: Missing (required)")
        else:
            print(f"   ✅ NAME: {name}")

    def validate_categories(self, recipe_path, input_section):
        """Validate categories (lowercase, preferred) or CATEGORIES (legacy) use only supported values."""
        # Check for lowercase (preferred) or UPPERCASE (legacy)
        categories = input_section.get("categories")
        if categories is None:
            categories = input_section.get("CATEGORIES", [])

        if not categories:
            # Categories are optional, just note it
            print(f"   ℹ️  categories: None specified (optional)")
            return

        invalid_categories = []
        for category in categories:
            if category not in self.SUPPORTED_CATEGORIES:
                invalid_categories.append(category)

        if invalid_categories:
            self.errors.append(
                f"{recipe_path}: Invalid categories {invalid_categories}. "
                f"Must be one of: {sorted(self.SUPPORTED_CATEGORIES)}"
            )
            print(f"   ❌ categories: {categories} (invalid: {invalid_categories})")
        else:
            print(f"   ✅ categories: {categories}")

    def validate_self_service(self, recipe_path, input_section):
        """Validate self_service (lowercase, preferred) or SELF_SERVICE (legacy) is set to true."""
        # Check for lowercase (preferred) or UPPERCASE (legacy)
        # Can't use 'or' because False is falsy
        self_service = input_section.get("self_service")
        if self_service is None:
            self_service = input_section.get("SELF_SERVICE")

        if self_service is None:
            self.errors.append(f"{recipe_path}: Missing self_service in Input section")
            print(f"   ❌ self_service: Missing (required)")
        elif self_service is not True:
            self.errors.append(
                f"{recipe_path}: self_service must be set to true, got {self_service}"
            )
            print(f"   ❌ self_service: {self_service} (must be true)")
        else:
            print(f"   ✅ self_service: true")

    def validate_automatic_install(self, recipe_path, input_section):
        """Validate automatic_install (lowercase, preferred) or AUTOMATIC_INSTALL (legacy) is set to false."""
        # Check for lowercase (preferred) or UPPERCASE (legacy)
        # Can't use 'or' because False is falsy
        automatic_install = input_section.get("automatic_install")
        if automatic_install is None:
            automatic_install = input_section.get("AUTOMATIC_INSTALL")

        if automatic_install is None:
            self.errors.append(
                f"{recipe_path}: Missing automatic_install in Input section"
            )
            print(f"   ❌ automatic_install: Missing (required)")
        elif automatic_install is not False:
            self.errors.append(
                f"{recipe_path}: automatic_install must be set to false, got {automatic_install}"
            )
            print(f"   ❌ automatic_install: {automatic_install} (must be false)")
        else:
            print(f"   ✅ automatic_install: false")

    def validate_gitops_mode(self, recipe_path, input_section):
        """Validate gitops_mode (lowercase, preferred) or GITOPS_MODE (legacy) is present in combined recipes and set to false by default."""
        # Check for lowercase (preferred) or UPPERCASE (legacy)
        gitops_mode = input_section.get("gitops_mode")
        if gitops_mode is None:
            gitops_mode = input_section.get("GITOPS_MODE")

        if gitops_mode is None:
            self.errors.append(
                f"{recipe_path}: Missing gitops_mode in Input section (required for combined recipes)"
            )
            print(f"   ❌ gitops_mode: Missing (required for combined recipes)")
        elif gitops_mode is not False:
            self.errors.append(
                f"{recipe_path}: gitops_mode must default to false, got {gitops_mode}"
            )
            print(f"   ❌ gitops_mode: {gitops_mode} (must default to false)")
        else:
            print(f"   ✅ gitops_mode: false (default)")

    def validate_categories_requirement(self, recipe_path, input_section):
        """Validate categories (lowercase, preferred) or CATEGORIES (legacy) is present when self_service is true."""
        # Check for lowercase (preferred) or UPPERCASE (legacy)
        # Can't use 'or' because False is falsy
        self_service = input_section.get("self_service")
        if self_service is None:
            self_service = input_section.get("SELF_SERVICE")
        
        categories = input_section.get("categories")
        if categories is None:
            categories = input_section.get("CATEGORIES")

        # Only validate if self_service is explicitly true
        if self_service is True:
            if categories is None:
                self.errors.append(
                    f"{recipe_path}: categories is required when self_service is true"
                )
                print(f"   ❌ categories: Missing (required when self_service is true)")
            elif not categories:
                self.errors.append(
                    f"{recipe_path}: categories must not be empty when self_service is true"
                )
                print(
                    f"   ❌ categories: Empty (must have at least one category when self_service is true)"
                )
            else:
                print(f"   ✅ categories: {categories} (required with self_service)")

    def validate_label_targeting(self, recipe_path, input_section):
        """Validate that only one of labels_include_any/labels_exclude_any (lowercase, preferred) or LABELS_INCLUDE_ANY/LABELS_EXCLUDE_ANY (legacy) is set."""
        # Check for lowercase (preferred) or UPPERCASE (legacy)
        labels_include = input_section.get("labels_include_any")
        if labels_include is None:
            labels_include = input_section.get("LABELS_INCLUDE_ANY")
        
        labels_exclude = input_section.get("labels_exclude_any")
        if labels_exclude is None:
            labels_exclude = input_section.get("LABELS_EXCLUDE_ANY")

        # Check if both are set to non-empty values
        has_include = labels_include is not None and labels_include
        has_exclude = labels_exclude is not None and labels_exclude

        if has_include and has_exclude:
            self.errors.append(
                f"{recipe_path}: Cannot set both labels_include_any and labels_exclude_any (mutually exclusive)"
            )
            print(
                f"   ❌ Label Targeting: Both labels_include_any and labels_exclude_any are set (mutually exclusive)"
            )
        elif has_include:
            print(f"   ✅ Label Targeting: labels_include_any only")
        elif has_exclude:
            print(f"   ✅ Label Targeting: labels_exclude_any only")
        else:
            print(f"   ✅ Label Targeting: None (valid)")

    def validate_gitops_software_dir(self, recipe_path, input_section):
        """Validate FLEET_GITOPS_SOFTWARE_DIR is set to 'lib/macos/software'."""
        software_dir = input_section.get("FLEET_GITOPS_SOFTWARE_DIR")
        expected = "lib/macos/software"

        if software_dir is None:
            self.errors.append(
                f"{recipe_path}: Missing FLEET_GITOPS_SOFTWARE_DIR in Input section"
            )
            print(f"   ❌ FLEET_GITOPS_SOFTWARE_DIR: Missing (required for GitOps)")
        elif software_dir != expected:
            self.errors.append(
                f"{recipe_path}: FLEET_GITOPS_SOFTWARE_DIR must be '{expected}', got '{software_dir}'"
            )
            print(
                f"   ❌ FLEET_GITOPS_SOFTWARE_DIR: '{software_dir}' (must be '{expected}')"
            )
        else:
            print(f"   ✅ FLEET_GITOPS_SOFTWARE_DIR: '{expected}'")

    def validate_gitops_team_yaml_path(self, recipe_path, input_section):
        """Validate FLEET_GITOPS_TEAM_YAML_PATH is set to 'teams/workstations.yml'."""
        team_yaml_path = input_section.get("FLEET_GITOPS_TEAM_YAML_PATH")
        expected = "teams/workstations.yml"

        if team_yaml_path is None:
            self.errors.append(
                f"{recipe_path}: Missing FLEET_GITOPS_TEAM_YAML_PATH in Input section"
            )
            print(f"   ❌ FLEET_GITOPS_TEAM_YAML_PATH: Missing (required for GitOps)")
        elif team_yaml_path != expected:
            self.errors.append(
                f"{recipe_path}: FLEET_GITOPS_TEAM_YAML_PATH must be '{expected}', got '{team_yaml_path}'"
            )
            print(
                f"   ❌ FLEET_GITOPS_TEAM_YAML_PATH: '{team_yaml_path}' (must be '{expected}')"
            )
        else:
            print(f"   ✅ FLEET_GITOPS_TEAM_YAML_PATH: '{expected}'")

    def validate_process_arguments(self, recipe_path, args, is_combined):
        """Validate Process section arguments reference Input variables correctly.
        
        Note: As of AutoPkg convention update, lowercase Input variables (self_service,
        automatic_install, etc.) are automatically passed to processors with native types
        preserved. They do NOT need to be in the Arguments section. Only UPPERCASE
        variables that use %VARIABLE% substitution need to be in Arguments.
        
        Legacy recipes may still use %SELF_SERVICE% syntax in Arguments.
        """
        # Check self_service argument - it's OK if not present (auto-passed from Input)
        # or if it uses the legacy %SELF_SERVICE% pattern
        self_service_arg = args.get("self_service")
        if self_service_arg is not None and self_service_arg != "%SELF_SERVICE%":
            # Present but not using correct pattern
            self.errors.append(
                f"{recipe_path}: Process argument 'self_service' should be '%SELF_SERVICE%' or omitted (auto-passed), got '{self_service_arg}'"
            )
            print(
                f"   ❌ Process self_service: '{self_service_arg}' (should be '%SELF_SERVICE%' or omitted)"
            )
        elif self_service_arg == "%SELF_SERVICE%":
            print(f"   ✅ Process self_service: '%SELF_SERVICE%' (legacy pattern)")
        else:
            print(f"   ✅ Process self_service: omitted (auto-passed from Input)")

        # Check automatic_install argument - same logic
        automatic_install_arg = args.get("automatic_install")
        if automatic_install_arg is not None and automatic_install_arg != "%AUTOMATIC_INSTALL%":
            self.errors.append(
                f"{recipe_path}: Process argument 'automatic_install' should be '%AUTOMATIC_INSTALL%' or omitted (auto-passed), got '{automatic_install_arg}'"
            )
            print(
                f"   ❌ Process automatic_install: '{automatic_install_arg}' (should be '%AUTOMATIC_INSTALL%' or omitted)"
            )
        elif automatic_install_arg == "%AUTOMATIC_INSTALL%":
            print(f"   ✅ Process automatic_install: '%AUTOMATIC_INSTALL%' (legacy pattern)")
        else:
            print(f"   ✅ Process automatic_install: omitted (auto-passed from Input)")

        # Check combined recipe Process arguments (includes GitOps support)
        if is_combined:
            software_dir_arg = args.get("gitops_software_dir")
            if software_dir_arg != "%FLEET_GITOPS_SOFTWARE_DIR%":
                self.errors.append(
                    f"{recipe_path}: Process argument 'gitops_software_dir' must be '%FLEET_GITOPS_SOFTWARE_DIR%', got '{software_dir_arg}'"
                )
                print(
                    f"   ❌ Process gitops_software_dir: '{software_dir_arg}' (must be '%FLEET_GITOPS_SOFTWARE_DIR%')"
                )
            else:
                print(
                    f"   ✅ Process gitops_software_dir: '%FLEET_GITOPS_SOFTWARE_DIR%'"
                )

            team_yaml_path_arg = args.get("gitops_team_yaml_path")
            if team_yaml_path_arg != "%FLEET_GITOPS_TEAM_YAML_PATH%":
                self.errors.append(
                    f"{recipe_path}: Process argument 'gitops_team_yaml_path' must be '%FLEET_GITOPS_TEAM_YAML_PATH%', got '{team_yaml_path_arg}'"
                )
                print(
                    f"   ❌ Process gitops_team_yaml_path: '{team_yaml_path_arg}' (must be '%FLEET_GITOPS_TEAM_YAML_PATH%')"
                )
            else:
                print(
                    f"   ✅ Process gitops_team_yaml_path: '%FLEET_GITOPS_TEAM_YAML_PATH%'"
                )

    def report_results(self):
        """Print final validation report and return exit code."""
        print("\n" + "=" * 70)
        print("Style Guide Compliance Report")
        print("=" * 70)
        print(f"\n📊 Statistics:")
        print(f"   Total recipes validated: {self.recipe_count}")
        print(f"   Combined recipes: {self.combined_count}")
        print(f"   Legacy recipes: {self.legacy_count}")
        print(f"\n🔍 Validation Results:")
        print(f"   Errors: {len(self.errors)}")
        print(f"   Warnings: {len(self.warnings)}")

        if self.errors:
            print(f"\n❌ ERRORS ({len(self.errors)}):")
            for error in self.errors:
                print(f"   • {error}")

        if self.warnings:
            print(f"\n⚠️  WARNINGS ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"   • {warning}")

        if not self.errors and not self.warnings:
            print("\n✅ All recipes comply with the style guide!")
            print("\nValidated requirements:")
            print("   ✅ YAML syntax is valid")
            print(
                "   ✅ Required AutoPkg fields present (Description, Identifier, Input, Process)"
            )
            print("   ✅ Filename conventions (.fleet.direct/gitops.recipe.yaml)")
            print("   ✅ Vendor folder structure (no spaces, proper organization)")
            print("   ✅ Identifier patterns (com.github.fleet.direct/gitops.<Name>)")
            print("   ✅ Single processor stage (FleetImporter)")
            print("   ✅ NAME variable exists in all recipes")
            print("   ✅ self_service set to true in all recipes")
            print("   ✅ automatic_install set to false in all recipes")
            print(
                "   ✅ FLEET_GITOPS_SOFTWARE_DIR set to 'lib/macos/software' in GitOps recipes"
            )
            print(
                "   ✅ FLEET_GITOPS_TEAM_YAML_PATH set to 'teams/workstations.yml' in GitOps recipes"
            )
            print("   ✅ Categories use only supported values (when specified)")
            print("   ✅ Lowercase Input variables auto-pass or legacy %UPPERCASE% patterns used correctly")
            return 0
        elif self.errors:
            print("\n❌ Style guide compliance validation FAILED")
            print("\nPlease fix the errors listed above.")
            return 1
        else:
            print("\n⚠️  Style guide compliance validation completed with warnings")
            return 0


def main():
    """Main entry point."""
    validator = StyleGuideValidator()
    exit_code = validator.validate_all_recipes()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
