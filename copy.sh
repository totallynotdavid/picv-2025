#!/bin/bash

# User Configuration
scan_dirs=("orchestrator")
ignore_dirs=("orchestrator/tests" "__pycache__")
root_files=("pyproject.toml")
allowed_extensions=("py")

# Function to build a find command string with proper escaping for ignoring dirs
build_find_ignore() {
  local find_cmd=""
  for dir in "${ignore_dirs[@]}"; do
    find_cmd+="! -path '*/$dir/*' -a "
  done
    if [[ -n $find_cmd ]]; then
        find_cmd="${find_cmd::-3}"

    else
    find_cmd="-print"
    fi
    echo "$find_cmd"
}


# Build the find command for structure
find_structure_cmd=(find "${scan_dirs[@]}" $(build_find_ignore) -type f -name "*.py" -print0)

# File Structure
output="=== File Structure ===\n"
while IFS= read -r -d $'\0' file; do
  output+="${file#./}\n"
done < <( "${find_structure_cmd[@]}" )

# Build the find command for content (same as structure for consistency)
find_content_cmd=(find "${scan_dirs[@]}"  $(build_find_ignore) -name "*.py")

output+="\n=== File Contents ===\n"
while IFS= read -r -d $'\0' file; do
  output+="\n// FILE: ${file#./}\n"
  output+=$(cat "$file")
  output+="\n---\n"
done < <("${find_content_cmd[@]}" -print0 ) 


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
