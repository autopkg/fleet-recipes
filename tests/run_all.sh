#!/bin/bash

# Change to the repository root (parent of tests directory)
cd "$(dirname "$0")/.." || exit 1

# Run all Fleet recipes in subdirectories, excluding _templates
for recipe in */*.fleet.recipe.yaml; do
    # Skip anything in _templates directory
    if [[ "$recipe" == _templates/* ]]; then
        continue
    fi
    
    echo "Running $recipe..."
    # Use ./ prefix to ensure we run the local recipe, not one from AutoPkg's repo cache
    autopkg run -v "./$recipe"
done
