#!/bin/bash

# User Configuration
scan_dirs=("orchestrator")
ignore_paths=("tests")
ignore_wildcards=("__pycache__")
root_files=("")
allowed_extensions=("py")

# Function to build ignore clause
build_ignore_clause() {
    local clause=""
    for path in "${ignore_paths[@]}"; do
        clause="$clause -not -path \"*/${path}/*\""
    done
    for wildcard in "${ignore_wildcards[@]}"; do
        clause="$clause -not -path \"*/${wildcard}/*\""
    done
    echo "$clause"
}

# Function to build extension clause
build_extension_clause() {
    local clause=""
    for ext in "${allowed_extensions[@]}"; do
        [ -n "$clause" ] && clause="$clause -o"
        clause="$clause -name \"*.${ext}\""
    done
    echo "$clause"
}

# Build and execute find command for structure
find_files() {
    local ignore_clause
    local ext_clause
    
    ignore_clause=$(build_ignore_clause)
    ext_clause=$(build_extension_clause)
    
    # Combine root files and directory search
    {
        # First, find root files
        for file in "${root_files[@]}"; do
            find . -maxdepth 1 -name "$file"
        done

        # Then, find files in scan directories
        for dir in "${scan_dirs[@]}"; do
            eval "find \"$dir\" $ignore_clause -type f \( $ext_clause \)"
        done
    } | sort
}

# Generate output
output="=== File Structure ===\n"

# Add file structure
while IFS= read -r file; do
    output+="${file#./}\n"
done < <(find_files)

output+="\n=== File Contents ===\n"

# Add file contents
while IFS= read -r file; do
    output+="\n// FILE: ${file#./}\n"
    output+="$(cat "$file")\n"
    output+="---\n"
done < <(find_files)

# Remove last separator
output="${output%---*}"

# Copy to clipboard
if command -v xclip &>/dev/null; then
    echo -e "$output" | xclip -sel clip
    echo "Output copied to clipboard (xclip)"
else
    echo -e "$output"
    echo "Clipboard copy not available, printing to console."
fi
