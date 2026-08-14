#!/usr/bin/env bash
# Usage:
#   bash tools/check_spelling.sh                 # scan all git-tracked files
#   bash tools/check_spelling.sh path/to/file …  # scan specific files/dirs
#
# Exits 0 if clean, 1 if any violations are found. Binary files are skipped
# automatically, as is this script itself (it contains the banned-word list).

set -euo pipefail

SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"

BANNED_WORDS=(
    "recognized" "recognizes" "recognizing" "unrecognized"
    "color" "colors" "colored" "colorize" "colorization"
    "fiber" "fibers"
    "favorite" "favorites"
    "center" "centers" "centered" "centering"
    "analyze" "analyzes" "analyzed" "analyzing" "analyzer" "analyzers"
    "behavior" "behaviors"
    "caliber" "calibers"
    "neighbor" "neighbors"
    "honor" "honors" "honored"
    "flavor" "flavors"
    "harbor" "harbors"
    "humor"
    "labeling" "labeled"
    "modeling" "modeled"
    "traveling" "traveled"
    "canceled" "canceling"
    "minimized" "minimizing" "minimization"
    "optimize" "optimizes" "optimized" "optimizing" "optimization"
    "organize" "organizes" "organized" "organizing" "organization"
    "serialize" "serializes" "serialized" "serialization"
    "deserialize" "deserialized"
    "normalize" "normalized" "normalizing" "normalization"
    "initialize" "initializes" "initialized" "initializing" "initialization"
    "visualize" "visualized" "visualizing" "visualization"
    "synchronize" "synchronized" "synchronizing" "synchronization"
    "localize" "localized" "localizing" "localization"
    "specialize" "specialized" "specializing" "specialization"
)

join_words() { local IFS="|"; echo "${BANNED_WORDS[*]}"; }
PATTERN="\\b($(join_words))\\b"

# Build the file list: explicit args (files or dirs), else all git-tracked files.
FILES=()
if [[ $# -gt 0 ]]; then
    for arg in "$@"; do
        if [[ -d "$arg" ]]; then
            while IFS= read -r -d '' f; do FILES+=("$f"); done \
                < <(find "$arg" -type f -not -path '*/.git/*' -print0)
        elif [[ -f "$arg" ]]; then
            FILES+=("$arg")
        fi
    done
else
    while IFS= read -r f; do FILES+=("$f"); done < <(git ls-files)
fi

FOUND=0
for f in "${FILES[@]}"; do
    [[ -f "$f" ]] || continue
    abs="$(cd "$(dirname "$f")" && pwd)/$(basename "$f")"
    [[ "$abs" == "$SELF" ]] && continue          # skip self (holds the word list)
    case "$f" in .git/*) continue ;; esac
    # Generated lockfiles carry external package names (e.g. css-color-parser)
    # that cannot be respelled and cannot carry a spelling-ignore marker.
    case "$(basename "$f")" in pnpm-lock.yaml|package-lock.json|yarn.lock) continue ;; esac
    # grep -I skips binary files; -n line numbers; -E extended regex (case-sensitive).
    # Lines containing "spelling-ignore" are exempt — use sparingly, for unavoidable
    # external identifiers (e.g. API event names, CLI flags like -no-color).
    matches="$(grep -InE "$PATTERN" "$f" 2>/dev/null | grep -v 'spelling-ignore' || true)"
    if [[ -n "$matches" ]]; then
        echo "$matches"
        FOUND=1
    fi
done

if [[ $FOUND -ne 0 ]]; then
    echo "FAIL: 'murican spellings found." >&2
    exit 1
fi

echo "OK: no muricanisms found."
exit 0
