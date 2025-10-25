#!/bin/bash

set -euo pipefail

declare -A results

for minorversion in {5..14}; do
    version="3.$minorversion"
    echo "$version"
    if docker run --rm -v "$PWD:/app" -w /app python:"$version" python -m unittest discover -s .; then
        results["$version"]="SUCCESS"
    else
        results["$version"]="FAILURE"
    fi
    echo
done

for version in "${!results[@]}"; do
    echo "Python $version: ${results[$version]}"
done
