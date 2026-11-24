#!/usr/bin/env bash
# 一键后台启动 BTC5m 受控实盘窗口（运维薄胶水，不改变任何交易语义）。
#
# 本脚本只做四件事：切目录、准备虚拟环境与日志、生成审计授权编号、
# 把现有 launcher 以 nohup 后台派发一次。所有前置检查、账户事实、
# 屏障轮换与风控语义都由 tools/predictfun/btc5m_launch.py 负责。
#
# 重要：脚本返回 0 只代表“已派发”，不代表实盘窗口启动成功。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PYTHON="$ROOT/.venv/bin/python"
BOT_TOOLS="$ROOT/skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits/tools/predictfun"
LAUNCHER="$BOT_TOOLS/btc5m_launch.py"
DEFAULT_CONFIG="$BOT_TOOLS/btc5m-controlled-paper.json"

# 与 btc5m_control.RUN_ID_PATTERN 一致：^[a-z0-9][a-z0-9_-]{0,63}$
RUN_ID_PATTERN='^[a-z0-9][a-z0-9_-]{0,63}$'

# 沿用已验证的主控 scratch 路径，不新增任何服务或平台目录。
TMPDIR_BASE="/home/pascal/.hermes/profiles/yquant/cache/scratch"

usage() {
  cat <<'EOF'
用法: scripts/start-btc5m-live.sh [--authorization-ref ID] [--config FILE]

以 nohup 后台派发一次 BTC5m 受控实盘窗口，参数固定为
  --auto-prepare --operations-mode unattended
并由现有 launcher 自行完成账户事实、对账、旧屏障轮换与风控检查。

选项:
  --authorization-ref ID  审计用授权编号（小写字母/数字/-/_，最长 64）。
                          省略时自动生成一个唯一编号。编号只是审计引用，
                          不替代人工授权，也绝不构成交易许可。
  --config FILE           使用指定的受控配置；默认使用随仓库提供的
                          btc5m-controlled-paper.json。路径含空格时需引号。
  --help                  显示本说明并退出，无任何副作用。

风险提示:
  * 这会启动真实交易（BSC 链上 Predict 账户），不是演练。
  * 需要 Linux/WSL 环境、仓库根 .venv/bin/python、可用的 keyring、
    skills/.env 中的存储凭据与网络访问；Windows 原生环境不适用。
  * 脚本只派发一次：无自动重试、无自动重启、无告警看门狗。
  * 退出码 0 只表示子进程已派发；实盘是否真正成交请查看日志与实盘状态。
EOF
}

fail() {
  printf '拒绝执行: %s\n' "$1" >&2
  exit 2
}

AUTH_REF=""
CONFIG=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h)
      usage
      exit 0
      ;;
    --authorization-ref)
      [[ $# -ge 2 ]] || fail "--authorization-ref 缺少取值"
      AUTH_REF="$2"
      shift 2
      ;;
    --authorization-ref=*)
      AUTH_REF="${1#*=}"
      shift
      ;;
    --config)
      [[ $# -ge 2 ]] || fail "--config 缺少取值"
      CONFIG="$2"
      shift 2
      ;;
    --config=*)
      CONFIG="${1#*=}"
      shift
      ;;
    *)
      fail "未知参数: $1"
      ;;
  esac
done

# 参数与环境检查必须早于任何副作用（不建目录、不起子进程）。
if [[ -z "$AUTH_REF" ]]; then
  RANDOM_HEX="$(head -c 4 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  AUTH_REF="btc5m-auth-$(TZ=Asia/Shanghai date +%Y%m%d%H%M%S)-$(date +%s%N)-${RANDOM_HEX}"
fi
[[ "$AUTH_REF" =~ $RUN_ID_PATTERN ]] || fail "授权编号不符合 RUN_ID_PATTERN: $AUTH_REF"

[[ -x "$PYTHON" ]] || fail "缺少可执行解释器: $PYTHON"
[[ -f "$LAUNCHER" ]] || fail "缺少 launcher: $LAUNCHER"
if [[ -n "$CONFIG" ]]; then
  [[ -f "$CONFIG" ]] || fail "配置文件不存在: $CONFIG"
  # 相对路径按调用者 cwd 解析后转绝对，避免后续 cd 改变其含义。
  CONFIG="$(cd "$(dirname "$CONFIG")" && pwd)/$(basename "$CONFIG")"
else
  CONFIG="$DEFAULT_CONFIG"
  [[ -f "$CONFIG" ]] || fail "缺少默认配置: $CONFIG"
fi

# 日志：每次运行独占新目录，绝不覆盖旧输出。
umask 077
DATE="$(TZ=Asia/Shanghai date +%F)"
STAMP="$(TZ=Asia/Shanghai date +%Y%m%dT%H%M%S)-${RANDOM}-${RANDOM}"
EVIDENCE_ROOT="$ROOT/data/reports/${DATE}-btc5m-controlled-paper/evidence"
LOG_DIR="$EVIDENCE_ROOT/wrapper/${STAMP}-${AUTH_REF}"
LOG_FILE="$LOG_DIR/launch.log"
# 只创建真正的父目录（${LOG_DIR%/*}），不得产生名为 "<dir>.parent" 的冗余兄弟目录。
mkdir -p "${LOG_DIR%/*}"
# 非 -p：目录已存在即拒绝，绝不覆盖任何旧输出。
if ! mkdir "$LOG_DIR" 2>/dev/null; then
  fail "日志目录已存在，拒绝覆盖: $LOG_DIR"
fi

if mkdir -p "$TMPDIR_BASE" 2>/dev/null; then
  TMP_PATH="$TMPDIR_BASE"
else
  TMP_PATH="$LOG_DIR/tmp"
  mkdir -p "$TMP_PATH"
fi

cd "$ROOT"
unset PYTHONPATH
unset PYTHONHOME

nohup env TMPDIR="$TMP_PATH" "$PYTHON" "$LAUNCHER" \
  --auto-prepare \
  --operations-mode unattended \
  --authorization-ref "$AUTH_REF" \
  --config "$CONFIG" \
  >>"$LOG_FILE" 2>&1 </dev/null &
CHILD_PID=$!

json_escape() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  printf '%s' "$value"
}

printf '{\n  "dispatched_at": "%s",\n  "authorization_ref": "%s",\n  "pid": %s,\n  "cwd": "%s",\n  "argv": ["%s", "%s", "--auto-prepare", "--operations-mode", "unattended", "--authorization-ref", "%s", "--config", "%s"],\n  "log_file": "%s"\n}\n' \
  "$(TZ=Asia/Shanghai date --iso-8601=seconds)" "$(json_escape "$AUTH_REF")" "$CHILD_PID" \
  "$(json_escape "$ROOT")" "$(json_escape "$PYTHON")" "$(json_escape "$LAUNCHER")" \
  "$(json_escape "$AUTH_REF")" "$(json_escape "$CONFIG")" "$(json_escape "$LOG_FILE")" \
  >"$LOG_DIR/dispatch.json"

printf '已派发（仅代表子进程已启动，不代表实盘启动成功）\n'
printf '  授权编号(审计用): %s\n' "$AUTH_REF"
printf '  子进程 PID: %s\n' "$CHILD_PID"
printf '  日志绝对路径: %s\n' "$LOG_FILE"
printf '  工作目录: %s\n' "$ROOT"
printf '请人工确认实盘状态；本脚本无自动重试、无自动重启、无告警看门狗。\n'
