#!/bin/bash

set -euo pipefail

for minorversion in {5..12}; do
    version="3.$minorversion"
    echo "$version"
    docker run --rm -v "$PWD:/app" -w /app python:"$version" python -m unittest discover -s . || true
    echo
done
