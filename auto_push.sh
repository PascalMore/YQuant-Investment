#!/bin/bash
set -euo pipefail

REPO_DIR="/home/pascal/.openclaw/workspace-yquant"
LOG_DIR="$REPO_DIR/logs/system/auto-push"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M')

mkdir -p "$LOG_DIR"
cd "$REPO_DIR"

echo "[$TIMESTAMP] Starting auto push" >> "$LOG_DIR/auto_push_$(date +%Y%m%d).log"

# Initialize submodules
git submodule update --init --recursive >> "$LOG_DIR/auto_push_$(date +%Y%m%d).log" 2>&1

# Commit submodules if they have changes
git submodule foreach --quiet '
    git add -A
    git diff --cached --quiet && exit 0
    # Check if HEAD is detached - if so, checkout to v1.0.0-preview first
    if ! git rev-parse --verify --symbolic-full-name HEAD@{upstream} 2>/dev/null; then
        git checkout v1.0.0-preview 2>/dev/null || git checkout main 2>/dev/null || true
    fi
    BRANCH=$(git symbolic-ref --quiet --short HEAD 2>/dev/null || echo "main")
    git commit -m "Auto commit sub: '"$TIMESTAMP"'"
    git push origin "$BRANCH"
' 2>>"$LOG_DIR/auto_push_$(date +%Y%m%d).log"

# Commit main repo if it has changes
git add -A
if git diff --cached --quiet; then
    echo "[$TIMESTAMP] No changes to commit" >> "$LOG_DIR/auto_push_$(date +%Y%m%d).log"
else
    git commit -m "Auto commit: $TIMESTAMP"
    git push origin main
    echo "[$TIMESTAMP] Pushed to GitHub" >> "$LOG_DIR/auto_push_$(date +%Y%m%d).log"
fi
