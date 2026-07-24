已弃用 — restart-clean 能力已 fuse 进 TradingAgents-CN submodule 内的
scripts/start_all.sh (pre-flight + 8 类退出码 + env 净化 + 端到端
smoke + scheduler jobs 校验) 与 scripts/stop_all.sh (单 PID 杀, 不带
process group)。

后续重启请直接使用:
  cd skills/apps/TradingAgents-CN && ./stop_all.sh && ./start_all.sh

(2026-07-24 Pascal 决策 K1.1)
