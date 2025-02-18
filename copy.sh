#!/bin/bash

# User Configuration
scan_dirs=("orchestrator")
ignore_paths=("tests")
ignore_wildcards=("__pycache__")
root_files=("") # e.g. pyproject.toml
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
        # First, find root files (if any)
        for file in "${root_files[@]}"; do
            find . -maxdepth 1 -name "$file"
        done

        # Then, find files in scan directories
        for dir in "${scan_dirs[@]}"; do
            eval "find \"$dir\" $ignore_clause -type f \( $ext_clause \)"
        done
    } | sort
}

# Function to strip docstrings from a Python file
strip_docstrings() {
    # The inline Python script uses the tokenize module to skip
    # over any docstring tokens (i.e. a STRING token immediately
    # following an INDENT). We pass the filename as the first argument.
    python3 - "$1" <<'EOF'
import sys, token, tokenize
fname = sys.argv[1]
with open(fname, "r") as source:
    result = []
    # Initialize prev_toktype so that a module-level docstring is detected.
    prev_toktype = token.INDENT
    last_lineno = -1
    last_col = 0
    tokgen = tokenize.generate_tokens(source.readline)
    for toktype, ttext, (slineno, scol), (elineno, ecol), ltext in tokgen:
        # Adjust spacing if needed
        if slineno > last_lineno:
            last_col = 0
        if scol > last_col:
            result.append(" " * (scol - last_col))
        # If a docstring is detected, skip it (don’t add anything)
        if toktype == token.STRING and prev_toktype == token.INDENT:
            pass
        else:
            result.append(ttext)
        prev_toktype = toktype
        last_col = ecol
        last_lineno = elineno
    sys.stdout.write("".join(result))
EOF
}

# Generate output
output="=== File Structure ===\n"

# Add file structure list
while IFS= read -r file; do
    output+="${file#./}\n"
done < <(find_files)

output+="\n=== File Contents ===\n"

# Add file contents with docstrings stripped
while IFS= read -r file; do
    output+="\n// FILE: ${file#./}\n"
    output+="$(strip_docstrings "$file")\n"
    output+="---\n"
done < <(find_files)

# Remove the last separator
output="${output%---*}"

# Copy to clipboard
if command -v xclip &>/dev/null; then
    echo -e "$output" | xclip -sel clip
    echo "Output copied to clipboard (xclip)"
else
    echo -e "$output"
    echo "Clipboard copy not available, printing to console."
fi
