#!/usr/bin/env bash
# BTC5m 官方历史每日摄入 wrapper — 03-018 §9（仓库内模板）。
#
# 约束（Design §9）：
# * bash 严格模式；固定 cd 到项目根。
# * 显式使用项目 .venv/bin/python（不依赖交互 shell 的 PYTHONPATH）。
# * 只跑 daily --apply；不回填、不改 cron、不外发、不调用 LLM。
# * 不 source 秘密文件，不硬编码凭据。显式注入业务入口 _api_key 约定的
#   key 环境变量（优先），或 key-file 环境变量指定的私有普通文件（如 0600）。
#   仅在运行时读取；缺失/空/不安全时只停止 Predict，不阻塞 Binance。
#   长期 job 必须另行授权配置稳定私有来源，不能依赖会被清理的临时文件。
# * 不后台运行、不吞 exit（exec 透传退出码）。
#
# 主控在 Verify + Review 通过后，才把本文件安装到当前 yquant profile 的
# scripts/ 目录并创建唯一 job。本模板本身不安装、不调度。

set -euo pipefail

PROJECT_ROOT="/home/pascal/workspace/yquant-investment"
PYTHON_BIN="${PROJECT_ROOT}/.venv/bin/python"
ENTRY="${PROJECT_ROOT}/skills/data/data-pipeline/scripts/run_btc5m_history.py"

cd "${PROJECT_ROOT}"

exec "${PYTHON_BIN}" "${ENTRY}" daily --apply --max-days-per-source 7 --wall-seconds 1800
