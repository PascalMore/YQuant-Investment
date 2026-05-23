#!/bin/bash
set -euo pipefail

REPO_DIR="/home/pascal/.openclaw/workspace-yquant"
LOG_DIR="$REPO_DIR/logs/system/auto-push"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M')

mkdir -p "$LOG_DIR"
cd "$REPO_DIR"

echo "[$TIMESTAMP] Starting auto push" >> "$LOG_DIR/auto_push_$(date +%Y%m%d).log"

# For submodules, we need to checkout the branch explicitly, not just use update
# git submodule update --init only checks out the recorded commit
# So we use a different approach - foreach with explicit checkout

# Handle each submodule individually
for submod in skills/apps/TradingAgents-CN skills/research/daily_stock_analysis; do
    if [ ! -d "$submod" ]; then
        continue
    fi
    
    cd "$REPO_DIR/$submod"
    
    # Check if there are changes
    if git diff --cached --quiet && git diff --quiet; then
        echo "[$TIMESTAMP] $submod: no changes" >> "$LOG_DIR/auto_push_$(date +%Y%m%d).log"
        continue
    fi
    
    # Stage all changes
    git add -A
    
    # If we're in detached HEAD, checkout to the tracked branch
    if ! git symbolic-ref --quiet HEAD >/dev/null 2>&1; then
        # Get the configured branch from .gitmodules or default
        TRACKED_BRANCH=$(git for-each-ref --format='%(upstream:short)' HEAD 2>/dev/null | cut -d/ -f2 || echo "v1.0.0-preview")
        git checkout "$TRACKED_BRANCH" 2>/dev/null || git checkout main 2>/dev/null || true
    fi
    
    BRANCH=$(git symbolic-ref --quiet --short HEAD 2>/dev/null || echo "main")
    git commit -m "Auto commit sub: $TIMESTAMP"
    git push origin "$BRANCH"
    echo "[$TIMESTAMP] $submod: pushed to $BRANCH" >> "$LOG_DIR/auto_push_$(date +%Y%m%d).log"
done

# Back to main repo
cd "$REPO_DIR"

# Commit main repo if it has changes
git add -A
if git diff --cached --quiet; then
    echo "[$TIMESTAMP] No changes to commit" >> "$LOG_DIR/auto_push_$(date +%Y%m%d).log"
else
    git commit -m "Auto commit: $TIMESTAMP"
    git push origin main
    echo "[$TIMESTAMP] Pushed to GitHub" >> "$LOG_DIR/auto_push_$(date +%Y%m%d).log"
fi
