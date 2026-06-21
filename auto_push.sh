#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${YQUANT_WORKSPACE:-$SCRIPT_DIR}"
LOG_DIR="$REPO_DIR/logs/system/auto-push"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M')

mkdir -p "$LOG_DIR"
cd "$REPO_DIR"

echo "[$TIMESTAMP] Starting auto push" >> "$LOG_DIR/auto_push_$(date +%Y%m%d).log"

# Handle each submodule individually
for submod in skills/apps/TradingAgents-CN skills/research/daily_stock_analysis; do
    if [ ! -d "$submod" ]; then
        continue
    fi
    
    cd "$REPO_DIR/$submod"
    
    # Ensure we're on main branch, not detached HEAD
    if ! git symbolic-ref --quiet HEAD >/dev/null 2>&1; then
        git checkout main
    fi
    
    BRANCH=$(git symbolic-ref --quiet --short HEAD 2>/dev/null || echo "main")
    
    # Fetch and pull latest first
    git fetch origin
    git pull --ff origin "$BRANCH" 2>/dev/null || true
    
    # Check if there are local changes to commit
    if git diff origin/"$BRANCH" --quiet; then
        echo "[$TIMESTAMP] $submod: up to date with remote" >> "$LOG_DIR/auto_push_$(date +%Y%m%d).log"
    else
        git add -A
        git commit -m "Auto commit sub: $TIMESTAMP"
        git push origin "$BRANCH"
        echo "[$TIMESTAMP] $submod: pushed to $BRANCH" >> "$LOG_DIR/auto_push_$(date +%Y%m%d).log"
    fi
done

# Back to main repo
cd "$REPO_DIR"

# Update submodule pointers if changed
git submodule update --init --recursive

# Commit main repo if it has changes
git add -A
if git diff --cached --quiet; then
    echo "[$TIMESTAMP] No changes to commit" >> "$LOG_DIR/auto_push_$(date +%Y%m%d).log"
else
    git commit -m "Auto commit: $TIMESTAMP"
    git push origin main
    echo "[$TIMESTAMP] Pushed to GitHub" >> "$LOG_DIR/auto_push_$(date +%Y%m%d).log"
fi

echo "[$TIMESTAMP] Auto push completed" >> "$LOG_DIR/auto_push_$(date +%Y%m%d).log"
