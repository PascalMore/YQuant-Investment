# MEMORY.md - YQuant 长期记忆

> 本文件存储 YQuant 的长期记忆，包括重要决策、项目背景、技术架构等关键信息。

## 项目概述

- **项目名称**：YQuant-Investment 智能量化投资系统
- **目录**：workspace-yquant
- **目标**：对标顶级对冲基金的量化投研体系

## 身份定义

- **角色**：YQuant（量化金融工程师）
- **用户**：Pascal Mao
- **沟通语言**：中文（专业术语可直接使用）

## 技术栈

- **核心语言**：Python > C++/Rust
- **量化框架**：VeighNa / NautilusTrader / Hummingbot / QUANTAXIS
- **数据源**：Tushare Pro / AKshare / Binance API / Finnhub 等
- **智能体框架**：OpenClaw 多智能体框架
- **AI编程**：Claude Code（MiniMax M2.7 API）— **默认编程方式**，除非用户明确不使用

## 子智能体团队

- @YQuant/data-collector
- @YQuant/researcher
- @YQuant/strategist
- @YQuant/risk-manager
- @YQuant/portfolio-manager
- @YQuant/reporter
- @YQuant/common
- @YQuant/data-engineer
- @YQuant/devops

## 目录结构

```
workspace-yquant/
├── soul.md / identity.md / agents.md / claude.md
├── HEARTBEAT.md / USER.md / TOOLS.md / MEMORY.md
├── memory/                    # 每日记忆文件
├── skills/
│   ├── common/              # 通用工具
│   ├── data/                # 数据采集
│   ├── research/            # 投研分析
│   ├── strategies/          # 策略回测
│   ├── risk/                # 风险管控
│   ├── portfolio/           # 组合管理
│   ├── reports/             # 复盘报告
│   ├── infra/               # 基础设施
│   └── knowledge/           # 知识库
├── scripts/                 # 项目维护脚本
│   └── auto_push.sh
```

---

_Last updated: 2026-04-24_

## Promoted From Short-Term Memory (2026-05-29)

<!-- openclaw-memory-promotion:memory:memory/2026-04-06.md:60:105 -->
- 上证指数: 3880.10 (↓1.00%) 深证成指: 13352.90 (↓0.99%) 创业板指: 3149.60 (↓0.73%) 科创50: 1256.21 (↓0.47%) 上涨 716 / 下跌 4746 涨停 38 / 跌停 46 成交额 16689亿 ``` ### 待完成 - [ ] 解决 litellm 代理问题（可能需要配置代理凭据或切换网络） - [ ] 补充 `analyzer_service` 模块 - [ ] 配置邮件推送（TOOLS.md 中已有 SMTP 配置） - [ ] 飞书 Webhook URL 待确认 - [ ] Tavily API Key（新闻搜索）待配置 --- ## 夜间调试记录 (2026-04-06 01:20-02:08) ### litellm/MiniMax 兼容性问题 ✅ 根因确认 **问题描述：** litellm 调用 MiniMax API 失败，报 `invalid api key (2049)` **根本原因：** - litellm MiniMax provider 使用 OpenAI 兼容端点 `/v1/chat/completions` - MiniMax 实际使用 Anthropic 兼容端点 `/v1/messages` - 即使配置了正确的 `base_url: "https://api.minimaxi.com/anthropic"`，litellm 内部仍然拼接错误路径 **测试验证：** - ✅ 直接用 `requests.post` 调用 MiniMax `/v1/messages` 成功 - ❌ litellm.completion() 始终调用错误端点 ### API Key 状态 | API | Key 格式 | 状态 | |-----|----------|------| | MiniMax | `sk-cp-6zYqByU7...` | ❌ 无效 (2049) - 可能已过期/被撤销 | | Gemini | - | ⚠️ Quota exceeded | | DeepSeek | 未知 | ❓ 未配置 | ### litellm Config 位置 ``` /home/pascal/.openclaw/workspace/skills/investment/research/daily_stock_analysis/litellm_config.yaml ``` [score=0.801 recalls=3 avg=0.692 source=memory/2026-04-06.md:60-105]

## Promoted From Short-Term Memory (2026-06-06)

<!-- openclaw-memory-promotion:memory:memory/2026-06-01.md:60:61 -->
- if not previous_zone or previous_zone not in ZONE_RANK: return None # 而非 "update" [score=0.898 recalls=0 avg=0.620 source=memory/2026-06-01.md:60-61]
<!-- openclaw-memory-promotion:memory:memory/2026-06-01.md:64:67 -->
- prev_zone = previous.get("pool_zone") or None # "" → None action = self._zone_delta_action(prev_zone, curr_zone) if action is None: stock_pool_zone = existing.get("pool_zone") or None [score=0.898 recalls=0 avg=0.620 source=memory/2026-06-01.md:64-67]
<!-- openclaw-memory-promotion:memory:memory/2026-06-01.md:68:68 -->
- action = self._zone_delta_action(stock_pool_zone, curr_zone) or "update" [score=0.898 recalls=0 avg=0.620 source=memory/2026-06-01.md:68-68]

## Promoted From Short-Term Memory (2026-06-08)

<!-- openclaw-memory-promotion:memory:memory/2026-06-01.md:49:49 -->
- `_zone_delta_action` 收到的 `previous["pool_zone"]` 是空字符串 `""` 而非 `None`，导致 `previous_zone not in ZONE_RANK` 分支返回 `"update"` 而非 `None`，`if action is None` 的备用逻辑永远不触发。 [score=0.897 recalls=0 avg=0.620 source=memory/2026-06-01.md:49-49]

## Promoted From Short-Term Memory (2026-06-11)

<!-- openclaw-memory-promotion:memory:memory/2026-05-03.md:1:30 -->
- # 2026-05-03 Daily Memory ## Smart Money Portfolio Pipeline 上线 ### 目录结构 ``` data/source/smart-money/{日期}/ ├── image/ # 图片截图（OCR处理） └── message/ # 文本/CSV数据 ``` ### 核心文件 - `skills/data/data-pipeline/scripts/smart_money_watcher.py` — 自动监控新文件并触发 pipeline - `start_smart_money_watcher.sh` — 启动脚本（start/stop/status） ### Pipeline 流程 - **Image**: OCR (PaddleOCR) → Excel → Normalize → Validate → MongoDB - **Message**: Parse → Excel → Normalize → Validate → MongoDB ### 今日数据（2026-05-03） - 收到 4 张持仓截图（21:30 ~ 21:42） - 处理结果：47 → 46 → 46 → 46 条记录 - 所有数据已入库 MongoDB（tradingagents 数据库） - 目录已创建：`data/source/smart-money/2026-05-03/image/` ### 待完成 - [ ] 将 smart_money_watcher 注册为 systemd 服务（开机自启） - [ ] 持仓对比分析（三张图差异） - [ ] 确认 message 目录的文本 pipeline 是否正常工作 [score=0.976 recalls=4 avg=1.000 source=memory/2026-05-03.md:1-30]

## Promoted From Short-Term Memory (2026-06-18)

<!-- openclaw-memory-promotion:memory:memory/2026-06-12-1852.md:18:19 -->
- 只需要把 API Key 发给我就行。 user: Conversation info (untrusted metadata): [score=0.871 recalls=0 avg=0.620 source=memory/2026-06-12-1852.md:18-19]
<!-- openclaw-memory-promotion:memory:memory/2026-06-12-1852.md:22:25 -->
- "chat_id": "user:ou_4ba9dccf7c86e42b89a1efef6f3a09ea", "message_id": "om_x100b6d891e777cacc31f968c043ecd5", "sender_id": "ou_4ba9dccf7c86e42b89a1efef6f3a09ea", "sender": "用户724532", [score=0.871 recalls=0 avg=0.620 source=memory/2026-06-12-1852.md:22-25]
<!-- openclaw-memory-promotion:memory:memory/2026-06-12-1903.md:9:9 -->
- user: Conversation info (untrusted metadata): [score=0.871 recalls=0 avg=0.620 source=memory/2026-06-12-1903.md:9-9]
<!-- openclaw-memory-promotion:memory:memory/2026-06-12-1903.md:12:15 -->
- "chat_id": "user:ou_4ba9dccf7c86e42b89a1efef6f3a09ea", "message_id": "om_x100b6d8a16c40ca8c344869a797b2cf", "sender_id": "ou_4ba9dccf7c86e42b89a1efef6f3a09ea", "sender": "用户724532", [score=0.871 recalls=0 avg=0.620 source=memory/2026-06-12-1903.md:12-15]
<!-- openclaw-memory-promotion:memory:memory/2026-06-12-1903.md:16:16 -->
- "timestamp": "Fri 2026-06-12 18:54 GMT+8" [score=0.871 recalls=0 avg=0.620 source=memory/2026-06-12-1903.md:16-16]
<!-- openclaw-memory-promotion:memory:memory/2026-06-12-1903.md:20:20 -->
- Sender (untrusted metadata): [score=0.871 recalls=0 avg=0.620 source=memory/2026-06-12-1903.md:20-20]

## Promoted From Short-Term Memory (2026-06-19)

<!-- openclaw-memory-promotion:memory:memory/2026-06-12-1903.md:23:25 -->
- "label": "用户724532 (ou_4ba9dccf7c86e42b89a1efef6f3a09ea)", "id": "ou_4ba9dccf7c86e42b89a1efef6f3a09ea", "name": "用户724532" [score=0.889 recalls=0 avg=0.620 source=memory/2026-06-12-1903.md:23-25]
<!-- openclaw-memory-promotion:memory:memory/2026-06-12-1852.md:11:11 -->
- 可以，你发过来吧。 [score=0.879 recalls=0 avg=0.620 source=memory/2026-06-12-1852.md:11-11]
<!-- openclaw-memory-promotion:memory:memory/2026-06-12-1903.md:29:31 -->
- [message_id: om_x100b6d8a16c40ca8c344869a797b2cf] 用户724532: YQuant 设置fallback 为minimax/MiniMax-M2.7, codex/gpt-5.5, minimax/MiniMax-M2.7-highspeed assistant: [score=0.862 recalls=0 avg=0.620 source=memory/2026-06-12-1903.md:29-31]
<!-- openclaw-memory-promotion:memory:memory/2026-06-12-1852.md:9:9 -->
- assistant: [score=0.859 recalls=0 avg=0.620 source=memory/2026-06-12-1852.md:9-9]

## Promoted From Short-Term Memory (2026-06-20)

<!-- openclaw-memory-promotion:memory:memory/2026-06-12-1852.md:13:13 -->
- 我帮你加两个地方： [score=0.867 recalls=0 avg=0.620 source=memory/2026-06-12-1852.md:13-13]

## Promoted From Short-Term Memory (2026-06-21)

<!-- openclaw-memory-promotion:memory:memory/2026-06-16.md:29:29 -->
- 30 20 * * 1-5 cd /home/pascal/.openclaw/workspace-yquant/skills/reports/daily-smartmoney-analysis/scripts && /home/pascal/.openclaw/workspace-yquant/skills/research/daily_stock_analysis/.venv/bin/python3.10 daily_export_report.py [score=0.890 recalls=0 avg=0.620 source=memory/2026-06-16.md:29-29]

## Promoted From Short-Term Memory (2026-06-22)

<!-- openclaw-memory-promotion:memory:memory/2026-06-15-1002.md:9:9 -->
- user: Conversation info (untrusted metadata): [score=0.909 recalls=0 avg=0.620 source=memory/2026-06-15-1002.md:9-9]
<!-- openclaw-memory-promotion:memory:memory/2026-06-15-1002.md:12:15 -->
- "chat_id": "user:ou_4ba9dccf7c86e42b89a1efef6f3a09ea", "message_id": "om_x100b6dc1f75f34b0c43732c0b8e65a0", "sender_id": "ou_4ba9dccf7c86e42b89a1efef6f3a09ea", "sender": "用户724532", [score=0.909 recalls=0 avg=0.620 source=memory/2026-06-15-1002.md:12-15]
<!-- openclaw-memory-promotion:memory:memory/2026-06-15-1002.md:16:16 -->
- "timestamp": "Mon 2026-06-15 09:55 GMT+8" [score=0.909 recalls=0 avg=0.620 source=memory/2026-06-15-1002.md:16-16]
<!-- openclaw-memory-promotion:memory:memory/2026-06-15-1002.md:20:20 -->
- Sender (untrusted metadata): [score=0.909 recalls=0 avg=0.620 source=memory/2026-06-15-1002.md:20-20]

## Promoted From Short-Term Memory (2026-06-23)

<!-- openclaw-memory-promotion:memory:memory/2026-06-15-1002.md:23:25 -->
- "label": "用户724532 (ou_4ba9dccf7c86e42b89a1efef6f3a09ea)", "id": "ou_4ba9dccf7c86e42b89a1efef6f3a09ea", "name": "用户724532" [score=0.926 recalls=0 avg=0.620 source=memory/2026-06-15-1002.md:23-25]
