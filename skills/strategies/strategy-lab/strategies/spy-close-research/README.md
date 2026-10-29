# spy-close-research

Strategy Lab 首版研究样例：对 2024 年 SPY 日收盘做固定问题的真实取数统计
（日收益均值、日收益标准差、年化波动率、首末收盘变化）。

只做统计；不交易、不进化、不伪造平台研究条目。需求与预算冻结在
[spec.md](spec.md)（按 [DESIGN-06-001 §5.2](../../../../../docs/design/06_strategy/DESIGN-06-001-strategy-lab.md)）。

本目录是 `skills/strategies/strategy-lab/strategies/` 下的策略实例（2026-10-30 由
`strategy-lab/spy-close-research/` 迁入 `strategy-lab/strategies/spy-close-research/`）；
`strategy-lab/` 根层只保留研发工具（SKILL、README、CLI、templates、tests），
具体实例统一放其 `strategies/` 子目录。

## 目录

- `spec.md`：窗口、口径、数据身份、预算与验收。
- `research.py`：主脚本；按相对路径加载 `../../scripts/quantdinger.py`（工具目录
  `strategy-lab/scripts`）的 `fetch_klines`（不建包）。
- `reports/latest.csv`：标准化真实窗口 OHLCV（不写提取时间，便于两次运行直接比对）。
- `reports/report.md`：统计、来源、时间、限制、复现命令（每次运行覆盖为最新结果）。

## 执行

凭据由主控经既有安全机制注入进程环境；本目录不保存任何凭据。两次执行都真实取数，
第二次不使用第一次 CSV 冒充接入：

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python skills/strategies/strategy-lab/strategies/spy-close-research/research.py --data-api human
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python skills/strategies/strategy-lab/strategies/spy-close-research/research.py --data-api human
```

- `--data-api human`：Human `/api/indicator/kline`（JWT）；`--data-api agent`：Agent
  `/api/agent/v1/klines`（R token）。不申请 token；无凭据按退出码 `4` 阻塞披露。
- 每次运行 ≤4 个数据请求、≤180s；两次合计 ≤8 个请求。退出码 `0` 成功。
- 二次执行核对（指标/CSV 一致性、计数）由独立 Verify 写 `reports/replay-check.md`；
  Developer 只交付脚本与首次产物，不做冒充一致的比对。

## 当前状态与阻塞

- `reports/` 内已有的报告与 `replay-check.md` 是 2026-10-30 目录迁移**前**运行的真实产物，
  其中的旧路径命令原文保留作为历史记录，不改写、不代表迁移后重新执行通过。
- 2026-10-29（Asia/Shanghai）：同脚本两次真实执行在部署 origin
  `http://127.0.0.1:15000` 上被平台业务层拒绝——Human 两次均 HTTP 200 + `code=0`
  `No data found`（USStock 上游取数为空）；对照探针 Crypto BTCUSDT 同端点上游 504。
  endpoint 本身在线（路由/参数正确），但该部署的上游行情源当日不可用。
- 上述为平台数据前提缺口，不是脚本逻辑失败；未产生任何统计产物，
  不以 fixture/随机数据替代。前提恢复后重跑上方命令即可。
