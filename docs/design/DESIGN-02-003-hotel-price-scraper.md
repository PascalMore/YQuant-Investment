# DESIGN-02-003: 酒店价格抓取系统详细设计

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Implemented |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-06-14 |
| 最后更新 | 2026-06-14 |
| 来源 RFC | RFC-02-003-hotel-price-scraper.md |
| 来源 SPEC | SPEC-02-003-hotel-price-scraper.md |
| 目标模块 | common/hotel_price_scraper |

## 1. 设计摘要

在现有 hotel_price_scraper 框架上做增量重构：替换酒店配置（3→6 家）、新增双房型分类（double/twin）、精简平台（去掉 Trip），保持平台适配器架构不变。核心改动集中在 config.yaml、models.py、base.py（房型分类）、excel_exporter.py（Summary 交叉表）和 scheduler.py（去 Trip）。

## 2. 现状分析

### 相关目录与文件

| 路径 | 角色 |
|---|---|
| `skills/common/hotel_price_scraper/` | 主模块目录 |
| `skills/common/hotel_price_scraper/config.yaml` | 酒店配置 |
| `skills/common/hotel_price_scraper/models.py` | 数据模型 |
| `skills/common/hotel_price_scraper/base.py` | 适配器基类 |
| `skills/common/hotel_price_scraper/BookingScraper.py` | Booking 适配器 |
| `skills/common/hotel_price_scraper/JalanScraper.py` | Jalan 适配器 |
| `skills/common/hotel_price_scraper/TripScraper.py` | Trip 适配器（保留不删，不再引用） |
| `skills/common/hotel_price_scraper/scheduler.py` | 调度器 |
| `skills/common/hotel_price_scraper/excel_exporter.py` | Excel 导出 |
| `skills/common/hotel_price_scraper/email_service.py` | 邮件服务 |
| `skills/common/hotel_price_scraper/run.py` | CLI 入口 |
| `skills/common/su-scraper/scripts/` | 旧版脚本（只读参考） |
| `skills/.env` | 邮件配置 |

### 现有约束

- Booking 和 Jalan 适配器通过 `load_legacy_module` 复用旧版 su-scraper 的 URL 构造和 HTML 解析逻辑
- 旧版 `parse_*_hotel` 返回 `(hotel_name, [{"room": ..., "price": ...}, ...])`，新设计依赖此格式
- Cookie 需人工获取填入 config

### 兼容性风险

- `TripScraper.py` 保留但 scheduler 不再引用 → 低风险（不影响运行）
- 旧版 `parse_booking_hotel` / `parse_jalan_hotel` 可能只返回第一个房型 → 需确认或增强

## 3. 方案设计

### 3.1 模块/文件改动

| 文件 | 改动 | 原因 |
|---|---|---|
| `config.yaml` | 完全重写：6 家酒店，去掉 trip 平台 | 需求变更 |
| `models.py` | `HotelPriceRecord` 新增 `room_category: str` | 支持双房型 |
| `base.py` | 新增 `_classify_room_category()`；改造 `build_records()` | 房型分类 + 每类最低价 |
| `excel_exporter.py` | RECORD_COLUMNS 加 `room_category`；Summary 改为 pivot 交叉表；去掉 trip sheet | 双房型对比展示 |
| `scheduler.py` | 去掉 TripScraper 引用 | 平台精简 |
| `run.py` | `--platform` choices 去掉 trip | CLI 一致性 |
| `skills/.env` | EMAIL_RECEIVERS 追加 suxn@hyviewgroup.com | 新收件人 |
| `SKILL.md` | 全面更新 | 文档同步 |
| `tests/` | 更新所有测试 | 覆盖新逻辑 |

### 3.2 数据流/控制流

```text
run.py (CLI)
  └→ HotelPriceScheduler.run()
       ├→ for platform in [jalan, booking]:
       │    └→ for hotel in config.hotels:
       │         └→ for checkin in next_30_days:
       │              └→ Scraper.scrape(hotel_id, checkin, checkout)
       │                   └→ legacy_parse(html) → [(room_name, price), ...]
       │                   └→ build_records(hotel_name, checkin, rooms)
       │                        └→ _classify_room_category() per room
       │                        └→ group by category → min price per category
       │                        └→ [PriceRecord(category=double), PriceRecord(category=twin)]
       │
       ├→ ExcelExporter.export(RunResult)
       │    ├→ Summary sheet: pivot_table(hotel × date → booking/jalan × double/twin)
       │    ├→ Booking sheet: raw records
       │    ├→ Jalan sheet: raw records
       │    ├→ Errors sheet
       │    └→ RunMeta sheet
       │
       └→ EmailService.send_report(excel_path)
```

### 3.3 接口与数据结构

**新增**：
- `HotelPriceRecord.room_category: str`（"double" 或 "twin"）
- `BaseHotelScraper._classify_room_category(room_name: str) -> str | None`

**修改**：
- `BaseHotelScraper.build_records()` → 按 category 分组取最低价
- `ExcelExporter._summary_frame()` → pivot 交叉对比表

**废弃**：
- `scheduler.SCRAPER_CLASSES` 中的 "trip"
- `run.py --platform trip`

### 3.4 UI/原型设计

无（命令行工具 + Excel 输出）。

## 4. 实现计划

- [x] Step 1: 更新 config.yaml（6 家酒店配置）
- [x] Step 2: 更新 models.py（room_category 字段）
- [x] Step 3: 更新 base.py（房型分类 + build_records 改造）
- [x] Step 4: 更新 excel_exporter.py（Summary 交叉表）
- [x] Step 5: 更新 scheduler.py + run.py（去 Trip）
- [x] Step 6: 更新 .env（追加收件人）
- [x] Step 7: 更新测试
- [x] Step 8: 更新 SKILL.md + RFC + 设置 crontab

## 5. 测试策略

- **单元测试**：
  - `test_models.py`: room_category 字段存在且 to_dict() 包含
  - `test_booking_scraper.py`: 房型分类逻辑 + build_records 多房型最低价
  - `test_jalan_scraper.py`: 同上（日语房型名）
  - `test_scheduler.py`: SCRAPER_CLASSES 只含 jalan/booking + 失败隔离
- **集成测试**：
  - Scheduler 跳过空平台 ID 的酒店
- **手工验证**：
  - 填入有效 cookie 后 `run.py --platform booking --days 1`
  - Excel 打开检查 Summary 交叉对比格式
- **回归范围**：hotel_price_scraper 模块内，不影响其他模块

## 6. 风险、降级与回滚

| 风险 | 应对 | 降级/回滚 |
|---|---|---|
| 旧版 parse 只返回首个房型 | 需增强解析提取所有房型 | 如无法增强，降级为只记录首个房型但标注 category |
| Cookie 过期 | 运行时报 "抓取失败" 并记录 error | 人工更新 cookie 后重跑 |
| 酒店页面结构变更 | 解析返回空列表 → status="满房" | 人工检查页面并更新 selector |
| 邮件发送失败 | Excel 已生成不受影响 | 人工从 output/ 目录获取 Excel |

## 7. 交接给实现者

- **必须遵守**：
  - 不修改 su-scraper 旧代码
  - 不硬编码任何凭据
  - 不删除 TripScraper.py
- **可自行判断**：
  - 房型分类的边界 case 处理（如同时含两个关键词）
  - Summary pivot 的具体列顺序
- **遇到以下情况退回 Principal**：
  - 旧版 parse_*_hotel 无法返回所有房型
  - Booking/Jalan 页面结构已变更导致 selector 失效

## 版本记录

| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V1.0 | 2026-06-14 | 初始创建，对应 RFC-02-003 V2.0 + SPEC-02-003 | YQuant |
