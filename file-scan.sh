#!/bin/bash

set -euo pipefail

EXCLUDE_DIRS=".git*|.ruff_cache|node_modules|venv|__pycache__|.DS_Store"
OUTPUT_FILE="scan_$(date '+%Y%m%d_%H%M%S').txt"

{
    echo "Current location: $(pwd)"
    echo
    echo "Directory Structure:"
    echo "------------------"
    tree -a -I "${EXCLUDE_DIRS}" --noreport . || echo "Warning: tree command failed"
} > "$OUTPUT_FILE"

echo "Scan complete! Output saved to: $OUTPUT_FILE"
