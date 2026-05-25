# RFC-02-003: 酒店价格抓取系统重构
## 元数据（Metadata）
| 项 | 值 |
|---|---|
| 状态 | 评审中 |
| 作者 | YQuant |
| 创建日期 | 2026-05-25 |
| 最后更新 | 2026-05-25 |
| 所属模块 | common |
| 依赖RFC | 无 |
| 替代RFC | 无 |
| AI适配 | OpenClaw/Claude Code |
| 标签 | #架构 #数据 #自动化 #爬虫 #报告 |

## 1. 执行摘要（Executive Summary）
统一 Jalan、Booking、Ctrip 三个平台酒店房价抓取流程，采用平台适配器架构、标准化数据模型和统一 Excel/邮件输出，按每周一定时任务执行。成功标准是三平台可独立运行、结果合并到单一报表、单平台失败不阻断全局任务。

## 2. 背景与动机（Background & Motivation）
- 现状痛点：
  - 三个平台脚本 `jalan.py`、`booking.py`、`trip.py` 各自独立运行，重复代码严重，`send_mail()` 在三个脚本中重复实现。
  - 邮件账号和授权码硬编码在脚本内，未使用统一 `skills/.env` 配置。
  - 无统一数据模型，当前输出为三个独立 Excel，后续汇总和比对成本高。
  - Cookie 过期无统一管理，Trip.com 依赖手动 Selenium 初始化，失效只能靠日志人工发现。
  - 缺少统一错误处理、限流和重试策略，网络异常与解析失败的可观测性较差。
- 业务价值：
  - 抓取效率提升：统一调度后可在可控限流下并发抓取。
  - 配置集中化：邮件、运行参数和酒店配置统一管理。
  - 维护成本降低：统一代码库、统一输出、统一错误处理。
- 触发原因：
  - 需求驱动：需要每周稳定生成单份酒店价格周报并邮件发送。
  - 风险驱动：当前脚本硬编码密钥、重复逻辑和弱错误恢复已影响可维护性。

## 3. 目标与非目标（Goals & Non-Goals）
### 3.1 必须目标（Must-Have）
- [ ] 统一平台适配器架构，抽象 `BaseHotelScraper` 基类。
- [ ] 标准化数据模型，统一为 `HotelPriceRecord`。
- [ ] 合并 Excel 输出，三平台结果写入同一工作簿。
- [ ] 使用 `skills/.env` 读取邮件配置。
- [ ] 每周一 06:10 CST 调度执行。
- [ ] 单平台失败不影响其他平台继续抓取和出报表。

### 3.2 非目标（Out of Scope）
- [ ] 不实现自动 Cookie 刷新，Trip.com 仍保留 Selenium 手动初始化流程。
- [ ] 不改写原有 `skills/common/su-scraper/` 目录，旧代码保留作为参考。
- [ ] 不接入 MongoDB 或其他数据库，仅输出 Excel 并邮件发送。

## 4. 整体设计（Overall Design）
### 4.1 核心设计哲学
平台适配器模式：统一接口，统一调度，统一输出。

### 4.2 架构总览
```text
HotelPriceScheduler（调度器）
├── JalanScraper（适配器）
├── BookingScraper（适配器）
├── TripScraper（适配器）
├── ExcelExporter（导出服务）
└── EmailService（邮件服务）
```

### 4.3 模块分工
- `HotelPriceScheduler`：读取配置、编排平台执行、聚合结果、控制失败隔离。
- `BaseHotelScraper`：定义抓取、Cookie 校验、平台标识等统一接口。
- `JalanScraper` / `BookingScraper` / `TripScraper`：封装平台 URL 构造、Cookie 注入、页面解析逻辑。
- `ExcelExporter`：输出统一工作簿，负责 summary、平台明细和错误记录。
- `EmailService`：复用 `skills/common/utils/email/send_email.py` 发送周报附件，配置来自 `skills/.env` 的 `EMAIL_SENDER` / `EMAIL_PASSWORD` / `EMAIL_RECEIVERS`。

## 5. 详细设计（Detailed Design）
### 5.1 业务流程（Flow）
- 触发条件：
  - 每周一 06:10 CST 由 Cron 调度触发。
  - 也支持手工执行单平台或全量抓取。
- 核心处理逻辑：
  1. 读取 `config.yaml` 配置，加载酒店列表和查询参数。
  2. 初始化三个平台适配器，并发执行抓取任务，使用 `Semaphore` 控制并发。
  3. 每个平台返回标准化 `HotelPriceRecord` 列表和错误记录。
  4. 聚合结果后导出 `hotel_prices_YYYY-MM-DD.xlsx`。
  5. 将报表发送至 `EMAIL_RECEIVERS`，邮件发送复用 `skills/common/utils/email/send_email.py`。
- 正常分支：
  - 适配器成功抓取报价，记录标准双人间价格，写入 summary 和平台明细页。
- 异常降级分支：
  - 单平台网络失败、Cookie 失效或解析异常时，仅写入 `errors` sheet 和运行元数据，不中断其他平台。

### 5.2 数据模型（Data Model）
| 字段 | 类型 | 说明 | 约束 |
|---|---|---|---|
| hotel_name | string | 酒店名称 | 非空 |
| platform | string | 平台来源（jalan/booking/trip） | 非空，枚举 |
| checkin_date | date | 入住日期 | 非空 |
| room_type | string | 房型（标准双人间） | 可空，解析失败时为空 |
| price | decimal | 价格 | 可空，满房或失败时为空 |
| currency | string | 币种（JPY/CNY） | 非空 |
| status | string | 状态（正常/满房/抓取失败） | 非空，枚举 |
| created_at | datetime | 记录时间 | 非空 |

### 5.3 接口契约（API Contract）
本方案为本地批处理脚本，不对外暴露 HTTP API，内部契约统一为适配器接口：
- `scrape(self, hotel_id, checkin, checkout) -> List[HotelPriceRecord]`
- `validate_cookie(self) -> bool`
- `getname(self) -> str`

调度器内部入口建议为：
- `run(config_path, env_path, output_dir, platform=None, send_email=True) -> RunResult`

返回结构至少包含：
- `records`：成功抓取的标准化记录列表。
- `errors`：平台级或酒店级错误列表。
- `summary`：本次运行元数据和统计信息。

### 5.4 AI模型设计（如有）
本 RFC 不涉及 AI 模型推理。AI 适配范围是代码生成、重构落地和测试补全约束，不涉及在线模型服务。

## 6. AI实装规范（AI Implementation Rules）
### 6.1 必须执行
- 所有密钥必须从 `os.environ` 或 `.env` 读取，不得硬编码。
- 统一复用 `requests.Session`，平台请求间隔控制在 3 秒以上。
- 重试采用 exponential backoff，并将最终失败记录到错误输出。
- 核心逻辑补充单元测试，覆盖配置加载、错误隔离和报表写入。
- 变更需保留与旧版 `su-scraper` 的映射关系，便于回归验证。

### 6.2 先询问再执行
- 修改现有酒店配置结构并影响旧脚本兼容性。
- 新增浏览器自动化依赖或系统级运行前置条件。
- 调整邮件接收人、Cron 频率或输出目录约定。

### 6.3 绝对禁止
- 硬编码邮件账号、密码、Cookie 或其他敏感信息。
- 直接删除 `skills/common/su-scraper/` 历史脚本。
- 在无验证方案前对三平台解析逻辑做大范围合并重写。

## 7. 风险与应对（Risks & Mitigations）
| 风险 | 概率 | 影响 | 应对方案 | 降级策略 |
|---|---|---|---|---|
| Cookie 过期 | 中 | 高 | 校验失败后记录告警并提示人工更新 | 标记平台失败，其他平台继续 |
| 网站反爬 | 中 | 中 | 限流、UA 轮换、Session 复用 | 降低请求频率，仅输出可抓到的平台 |
| 单平台挂掉 | 中 | 低 | 调度器隔离异常，按平台收敛错误 | 生成部分成功报表并附错误摘要 |

## 8. 备选方案（Alternatives Considered）
- 维持三个脚本独立运行，再通过后处理脚本合并 Excel：
  - 优点：对旧代码改动最小。
  - 缺点：重复逻辑保留，错误处理和配置治理问题不解决。
  - 不选原因：无法降低长期维护成本。
- 直接将结果写入数据库再生成报表：
  - 优点：利于历史分析和查询。
  - 缺点：超出当前需求，增加部署和运维成本。
  - 不选原因：当前目标仅是稳定生成周报，ROI 不足。

## 9. 验收标准（Acceptance Criteria）
### 9.1 功能验收
- [ ] 三个平台均可独立抓取成功。
- [ ] Excel 输出包含所有平台数据和错误记录。
- [ ] 邮件正确发送到 `EMAIL_RECEIVERS`。
- [ ] Cron 调度正常触发并生成周报。

### 9.2 非功能验收
- [ ] 单平台失败不会导致全局任务失败。
- [ ] 邮件和 Cookie 凭据均来自 `skills/.env` 或外部文件。
- [ ] 请求限流、重试和日志记录符合平台访问约束。

## 10. 落地计划（Implementation Plan）
### 10.1 阶段划分
- 第一阶段：平台适配器重构，按 `Jalan -> Booking -> Trip` 顺序迁移。
- 第二阶段：实现调度器、Excel 导出和邮件服务。
- 第三阶段：补充集成测试、配置 Cron 并验证端到端流程。

### 10.2 任务清单
- 梳理旧版 `su-scraper` 配置与字段映射。
- 建立 `BaseHotelScraper`、`HotelPriceRecord` 和统一错误模型。
- 接入 `config.yaml` 与 `skills/.env`。
- 实现统一工作簿导出和周报邮件发送。
- 完成单平台失败隔离测试和手工 Cookie 初始化文档。

## 11. 开放问题（Open Questions）
- Cron 时间已统一为每周一 06:10 CST。
- `currency` 字段当前需求写为 `JPY/CNY`，但现有脚本主要固定为 `JPY`，是否需要支持跨币种输出还需明确。
- Summary sheet 是否只保留标准双人间最低价，还是保留平台首个匹配价格，需要在实现前统一口径。

## 12. 参考资料（References）
- 原 `su-scraper` 代码：`skills/common/su-scraper/scripts/`
- 酒店价格抓取技能说明：`skills/common/hotel_price_scraper/SKILL.md`
- 重构设计草案：`skills/common/hotel_price_scraper/REFACTOR_DESIGN.md`
- 邮件 `.env` 配置：`skills/.env`（`EMAIL_SENDER` / `EMAIL_PASSWORD` / `EMAIL_RECEIVERS`）

## 版本记录（Changelog）
| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V1.1 | 2026-05-25 | 统一 Cron 时间为每周一 06:10 CST，明确复用公共 `send_email.py` 与 `skills/.env` 邮件配置 | YQuant |
| V1.0 | 2026-05-25 | 初始创建酒店价格抓取系统重构 RFC | YQuant |
