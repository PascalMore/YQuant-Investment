# MEMORY.md - YQuant 长期记忆

> 本文件存储 YQuant 的长期记忆，包括重要决策、项目背景、技术架构等关键信息。

## 项目概述

- **项目名称**：YQClaw-Investment 智能量化投资系统
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
└── auto_push.sh
```

---

_Last updated: 2026-04-24_

## Promoted From Short-Term Memory (2026-05-27)

<!-- openclaw-memory-promotion:memory:memory/2026-04-16.md:1:41 -->
- # 2026-04-16 日记 ## 今日事件 ### 飞书问题排查（晚间） - **现象**：飞书发消息小Q无响应，提示 "AI service is temporarily overloaded" - **诊断过程**： 1. Context 满（99.9%）→ 重启 Gateway 后解决 2. 重启后飞书仍然无响应 3. dedup 文件显示 20:11 后就没有收到任何消息 4. 检查 `feishu-pairing.json` 发现是空的 `"requests": []` 5. Gateway status 显示 Feishu: OK，但实际消息接收断开 - **权限配置**（已确认正确）： - `contact:user.base:readonly` - `m:chat`, `m:message` - `im:message.group_at_msg:readonly` - `im:message.p2p_msg:readonly` - `im:message:send_as_bot` - `im:resource` - 事件订阅：`im.message.receive_v1` - 机器人能力：已开启 - **可能原因**： 1. 应用是「开发中」状态，只有管理员自己能找到 2. 需要发布应用才能让其他用户使用 3. 或者需要确认找的是正确的机器人（应用名而非"小Q"） - **待确认**：应用发布状态 + 是否找对了机器人 ## 系统状态 | 组件 | 状态 | 备注 | |------|------|------| | 飞书 | ⚠️ 断开 | 消息接收断开 | | Context | ✅ 已清零 | 重启后恢复正常 | | Cron Jobs | ❌ 失效 | nextRun=null | | daily_stock_analysis | ❌ SIGKILL | 问题未解决 | ## 明日待办 - [ ] 继续排查飞书 1:1 DM 接收问题 [score=0.898 recalls=7 avg=0.996 source=memory/2026-04-16.md:1-41]
<!-- openclaw-memory-promotion:memory:memory/2026-04-07.md:1:42 -->
- # 2026-04-07 Daily Memory ## Daily Stock Analysis 项目配置 ### 环境变量 (.env) 路径 `~/.openclaw/workspace/skills/investment/research/daily_stock_analysis/.env` ### 当前自选股配置 `STOCK_LIST=002594,00981,01801` ⚠️ **已知问题：** 00981 和 01801 不是有效股票代码，只有 002594 能正常解析。需要确认正确的股票代码。 ### 已修复 Bug - **main.py AI分析器检查**：改为 `GeminiAnalyzer(config=config)` 统一 LiteLLM 管理（原来只检查 gemini_api_key/openai_api_key，漏掉 deepseek） - **socksio**：安装 `httpx[socks]` 解决 SOCKS 代理兼容问题 ### 代理配置 ``` USE_PROXY=true PROXY_HOST=172.25.240.1 # WSL2 Windows宿主机IP（Clash代理） PROXY_PORT=7897 ``` ### LLM 多渠道配置 ``` LLM_CHANNELS=minimax,deepseek,gemini LITELLM_MODEL=minimax/MiniMax-M2.7 LITELLM_FALLBACK_MODELS=deepseek/deepseek-chat,gemini/gemini-2.5-flash LLM_MINIMAX_BASE_URL=https://api.minimax.chat/v LLM_MINIMAX_API_KEYS=sk-cp-6zYqByU7U26dpVHSh0Ys_cgJLZjrsyC4zLBet8QHThZRutXseCCKgx3MB9GTRP_eaUlLNCWwaQsjk0Z_8_UFkcv-uo0avsfR5JThPMCnzplyotV3x1-8MXY LLM_MINIMAX_MODELS=MiniMax-M2.7 ``` ### Systemd 服务 路径：`~/.config/systemd/user/daily-stock-analysis.service` - 执行：`/usr/bin/python3 main.py` - SCHEDULE_TIME=07:30 触发自选股分析 - 代理通过 .env 读取（动态获取WSL2网关IP方案被回退） ### Crontab（最终） ``` 0 8 * * 1-5 daily-market-analysis --output email # 08:00 全球市场报告 ``` [score=0.841 recalls=5 avg=1.000 source=memory/2026-04-07.md:1-42]
<!-- openclaw-memory-promotion:memory:memory/2026-05-04.md:22:46 -->
- 清理了 `smart-money/2026-05-03/` 目录下的残留文件，最终结构： ``` 2026-05-03/ ├── image/ │ ├── portfolio_20260503_2130.jpg │ ├── portfolio_20260503_2136.jpg │ ├── portfolio_20260503_2139.jpg │ ├── portfolio_20260503_2142.jpg │ └── portfolio_20260503_2143.jpg └── message/ ├── portfolio_20260423_2340.txt/.xlsx (80PF11234 景顺灵活1号) ├── portfolio_20260423_2345.txt/.xlsx (80PF11242 易方达均衡配置) └── portfolio_20260423_2350.txt/.xlsx (80PF11238 常春藤优选3号) ``` ### 5. Message Pipeline 数据验证 - 80PF11234：48 行 ✅ - 80PF11242：46 行 ✅ - 80PF11238：47 行 ✅（注意原始数据中有 `GOOOG.US` 多了一个 O） ## 修改的文件 - `skills/data/data-pipeline/scripts/run_message_pipeline.py`： - COLUMN_ALIASES 添加半角括号映射 - `save_excel()` 函数改为使用传入的 filename - 新增 `save_raw_txt()` 函数保存原始数据 [score=0.816 recalls=3 avg=1.000 source=memory/2026-05-04.md:22-46]
<!-- openclaw-memory-promotion:memory:memory/2026-05-02.md:23:57 -->
- Excel → flatten_to_nested() → nested JSON → image_portfolio_normalizer → normalized → MongoDB ``` ### 5. 测试数据 - `示例_5产品_250持仓.xlsx`: 1天×5产品×236持仓 → MongoDB ✅ - `示例_5产品_250持仓_base64.txt`: zlib+base64 压缩版 (740 chars) - `mock_3days_decoded.json`: 3天×5产品×708持仓（手动修复版） ### 6. 文件传输 - 建议通过文件传输而非聊天复制传递 base64（聊天复制会导致字符损坏） - 图片保存路径: `skills/data/source/smart-money/YYYY-MM-DD/` ### 7. 目录清理 - 已删除冗余 `workspace-yquant/data/` 目录 - 已删除 `skills/data/data/` 目录 ## MongoDB 连接信息 - Host: 172.25.240.1:27017 - Database: tradingagents - Collections: portfolio_basic_info, portfolio_nav, portfolio_position ## PaddleOCR Table-to-Excel Skill 新增 ### 8. 新增技能：paddleocr_table2excel - **目录**：`skills/common/paddleocr_table2excel/` - **虚拟环境**：`.venv/`（Python 3.10.12，完全隔离） - **核心脚本**：`scripts/table_ocr.py`（Pipeline + TablePreprocessor + TableDetector + parse_row） - **文档**：`SKILL.md` ### 9. 技术栈 - PaddlePaddle 3.0.0 + PaddleOCR 2.7.3 + Paddlex 3.5.1（全程 CPU 推理，离线运行） - opencv-contrib-python 4.6.0.66 - numpy<2（必须先安装以确保 ABI 兼容） - openpyxl 3.1.5 ### 10. 关键设计决策 [score=0.814 recalls=3 avg=1.000 source=memory/2026-05-02.md:23-57]

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
