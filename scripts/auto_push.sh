#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${YQUANT_WORKSPACE:-$(cd "$SCRIPT_DIR/.." && pwd)}"
YINGLONG_DIR="${YQUANT_YINGLONG_DIR:-$HOME/workspace/yq-yinglong}"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M')

# ─────────────────────────────────────────────────────
# push_repo: push a repo and all its submodules
#   $1 = repo path
#   $2 = prefix (yquant / yinglong)
# ─────────────────────────────────────────────────────
push_repo() {
    local repo_path="$1"
    local prefix="$2"
    local log_dir="$repo_path/logs/system/auto-push"
    local log_file="$log_dir/auto_push_$(date +%Y%m%d).log"

    mkdir -p "$log_dir"
    echo "[$TIMESTAMP] Starting auto push ($prefix)" >> "$log_file"

    cd "$repo_path"

    # ── Submodules: initialize BEFORE iterating .gitmodules ──
    # Required so each submodule working tree starts at the committed gitlink,
    # not whatever the parent's working tree currently has checked out.
    # Fail fast if a submodule is broken — do NOT use `|| true` here, otherwise
    # the next loop would silently work on a half-initialized tree.
    if [ -f "$repo_path/.gitmodules" ]; then
        git submodule update --init
        echo "[$TIMESTAMP] $prefix: submodules initialized" >> "$log_file"
    fi

    # ── Submodules (auto-detect from .gitmodules) ──
    if [ -f "$repo_path/.gitmodules" ]; then
        while IFS= read -r submod; do
            [ -z "$submod" ] && continue
            [ ! -d "$repo_path/$submod" ] && continue

            cd "$repo_path/$submod"

            # Ensure we're on a real branch, not detached HEAD
            if ! git symbolic-ref --quiet HEAD >/dev/null 2>&1; then
                git checkout main 2>/dev/null || true
            fi
            BRANCH=$(git symbolic-ref --quiet --short HEAD 2>/dev/null || echo "main")

            git fetch origin
            git pull --ff origin "$BRANCH" 2>/dev/null || true

            git add -A
            if git diff --cached --quiet; then
                echo "[$TIMESTAMP] $prefix/$submod: no working tree changes" >> "$log_file"
            else
                git commit -m "Auto commit sub ($prefix): $TIMESTAMP"
            fi

            if [ "$(git rev-list --count origin/"$BRANCH"..HEAD 2>/dev/null || echo 0)" -gt 0 ]; then
                git push origin "$BRANCH"
                echo "[$TIMESTAMP] $prefix/$submod: pushed to $BRANCH" >> "$log_file"
            else
                echo "[$TIMESTAMP] $prefix/$submod: up to date" >> "$log_file"
            fi
        done < <(git config -f "$repo_path/.gitmodules" --get-regexp '\.path$' | awk '{print $2}')
    fi

    # ── Main repo ──
    cd "$repo_path"
    # NOTE: do NOT run `git submodule update` here. After the loop above pushed
    # submodule heads to origin, a submodule update would reset each submodule
    # working tree back to the gitlink currently recorded by the main repo,
    # silently discarding any new submodule SHA before `git add -A` records it.
    # Submodule initialization has already happened above, before the loop.

    # Detect branch (default main)
    MAIN_BRANCH=$(git symbolic-ref --quiet --short HEAD 2>/dev/null || echo "main")

    git add -A
    if git diff --cached --quiet; then
        echo "[$TIMESTAMP] No working tree changes ($prefix)" >> "$log_file"
    else
        git commit -m "Auto commit ($prefix): $TIMESTAMP"
    fi

    if [ "$(git rev-list --count origin/"$MAIN_BRANCH"..HEAD 2>/dev/null || echo 0)" -gt 0 ]; then
        git push origin "$MAIN_BRANCH"
        echo "[$TIMESTAMP] Pushed to GitHub ($prefix) [$MAIN_BRANCH]" >> "$log_file"
    else
        echo "[$TIMESTAMP] Up to date with remote ($prefix) [$MAIN_BRANCH]" >> "$log_file"
    fi

    echo "[$TIMESTAMP] Completed ($prefix)" >> "$log_file"
}

# ── yquant-investment ──
push_repo "$REPO_DIR" "yquant"

# ── yinglong (skip silently if absent) ──
if [ -d "$YINGLONG_DIR/.git" ]; then
    push_repo "$YINGLONG_DIR" "yinglong"
else
    YQ_LOG="$REPO_DIR/logs/system/auto-push"
    mkdir -p "$YQ_LOG"
    echo "[$TIMESTAMP] Yinglong not found at $YINGLONG_DIR, skipped" >> "$YQ_LOG/auto_push_$(date +%Y%m%d).log"
fi

echo "[$TIMESTAMP] All done" >> "$REPO_DIR/logs/system/auto-push/auto_push_$(date +%Y%m%d).log"
