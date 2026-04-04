#!/bin/bash
# Pre-commit hook: block files that could contain PII from being committed.
# This is a safety net in addition to .gitignore.

BLOCKED_PATTERNS=(
    "anonymizer_mapping*.json"
    "*.jsonl"
    "transcripts/"
)

staged_files=$(git diff --cached --name-only)

for pattern in "${BLOCKED_PATTERNS[@]}"; do
    matches=$(echo "$staged_files" | grep -E "$pattern" || true)
    if [ -n "$matches" ]; then
        echo "BLOCKED: Attempted to commit files matching '$pattern':"
        echo "$matches"
        echo ""
        echo "These files may contain PII and must never be committed."
        exit 1
    fi
done
