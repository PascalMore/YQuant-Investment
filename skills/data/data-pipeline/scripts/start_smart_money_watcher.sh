#!/bin/bash
# Smart Money Watcher 启动脚本
# Usage: ./start_smart_money_watcher.sh [start|stop|status]

NAME="smart_money_watcher"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="python3"
PYTHON_SCRIPT="$SCRIPT_DIR/skills/data/data-pipeline/scripts/smart_money_watcher.py"
PID_FILE="$SCRIPT_DIR/.smart_money_watcher.pid"
LOG_FILE="$SCRIPT_DIR/logs/smart_money_watcher.log"

mkdir -p "$SCRIPT_DIR/logs"

start() {
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "$NAME is already running (PID=$(cat "$PID_FILE"))"
        return 1
    fi
    echo "Starting $NAME..."
    cd "$SCRIPT_DIR"
    nohup $PYTHON "$PYTHON_SCRIPT" > "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    echo "$NAME started (PID=$(cat "$PID_FILE"))"
}

stop() {
    if [ ! -f "$PID_FILE" ]; then
        echo "$NAME is not running"
        return 1
    fi
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "Stopping $NAME (PID=$PID)..."
        kill "$PID"
        rm -f "$PID_FILE"
        echo "$NAME stopped"
    else
        echo "$NAME is not running (stale PID file)"
        rm -f "$PID_FILE"
    fi
}

status() {
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "$NAME is running (PID=$(cat "$PID_FILE"))"
    else
        echo "$NAME is not running"
    fi
}

case "$1" in
    start) start ;;
    stop) stop ;;
    status) status ;;
    *) echo "Usage: $0 {start|stop|status}" ;;
esac
