# SPEC-02-003: 酒店价格抓取系统工程规格

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Accepted |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-06-14 |
| 最后更新 | 2026-06-14 |
| 来源 RFC | RFC-02-003-hotel-price-scraper.md |
| 目标模块 | common/hotel_price_scraper |
| 适配 Agent | YQuant-Developer-Engineer, YQuant-Test-Engineer |

## 1. 需求摘要

系统每周一 06:10 CST 自动从 Booking 和 Jalan 两个平台抓取 6 家京都酒店未来 30 天的大床房（double）和双床房（twin）最低价（JPY），合并输出 Excel 报表并通过邮件发送。④⑤⑥ 三家酒店仅在 Booking 平台抓取。单平台/单酒店失败不阻断其他抓取。

## 2. 范围

### 2.1 In Scope

- [x] 6 家酒店配置（替换旧 3 家）
- [x] 双房型抓取：大床房（double）+ 双床房（twin），每种取最低价
- [x] Booking + Jalan 两平台
- [x] `room_category` 字段新增到数据模型
- [x] Excel 交叉对比 summary + 平台明细 sheet
- [x] 邮件发送到 `EMAIL_RECEIVERS`（含 `suxn@hyviewgroup.com`）
- [x] 每周一 06:10 CST crontab 调度

### 2.2 Out of Scope

- [ ] Trip.com 平台接入（后续版本）
- [ ] 自动 Cookie 刷新
- [ ] MongoDB/数据库持久化
- [ ] 历史价格趋势分析

## 3. 功能规格

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| F-001 | 读取 config.yaml 加载酒店配置 | config.yaml 路径 | 酒店列表 + 查询参数 | 配置缺失或格式错误时抛异常终止 |
| F-002 | 为每个酒店×日期×平台组合发起抓取 | hotel_id, checkin, checkout | PriceRecord 列表 | 网络超时/HTTP 错误 → 记录到 errors，继续下一组 |
| F-003 | 解析页面房型并分类为 double/twin | BeautifulSoup/Jalan HTML 解析结果 | 分类后的房型列表 | 房型名不匹配 double/twin → 跳过 |
| F-004 | 每个酒店×日期×平台×房型类别取最低价 | 同一 (hotel, date, platform, category) 的多条报价 | 每组 1 条最低价记录 | 无匹配房型 → status="满房" |
| F-005 | 跳过酒店缺少的平台 ID | hotel.platforms[platform] 为空 | 跳过该平台 | 正常流程，非错误 |
| F-006 | Cookie 失效检测 | 页面无标题/登录提示 | status="抓取失败" + error 记录 | 该平台可继续尝试其他酒店 |
| F-007 | Excel 导出 | RunResult(records, errors) | hotel_price_report_YYYY-MM-DD.xlsx | 空数据也能生成 Excel |
| F-008 | 邮件发送 | Excel 附件路径 | 发送到 EMAIL_RECEIVERS | 邮件失败不删除已生成的 Excel |

## 4. 数据与接口契约

### 4.1 HotelPriceRecord

| 字段 | 类型 | 说明 | 约束 |
|---|---|---|---|
| hotel_name | str | 酒店名称 | 非空 |
| platform | str | jalan / booking | 非空，枚举 |
| checkin_date | date | 入住日期 | 非空 |
| room_category | str | double / twin | 非空，枚举 |
| room_type | str | 具体房型名称 | 可空 |
| price | Decimal \| None | 最低价格 | 可空 |
| currency | str | JPY | 非空 |
| status | str | 正常 / 满房 / 抓取失败 | 非空 |
| created_at | datetime | 记录时间 | 非空 |

### 4.2 房型分类规则

```
if "ツイン" in room_name.lower() or "twin" in room_name.lower():
    → "twin"
elif "ダブル" in room_name.lower() or "double" in room_name.lower():
    → "double"
else:
    → None (跳过)
```

优先级：twin > double（因为"ツインベッドルーム"同时含"ベッド"但主要属性是 twin）

### 4.3 config.yaml 契约

```yaml
query:
  days_ahead: 30
  nights: 1
  adults: 2
  children: 0
  rooms: 1
  currency: JPY
platforms:
  jalan:
    cookie: ""
  booking:
    cookie: ""
hotels:
  - hotel_key: str
    name: str
    platforms:
      jalan: str      # yadNo, 空字符串表示无此平台
      booking: str    # slug, 空字符串表示无此平台
```

### 4.4 Excel 输出契约

**Sheet 1 — Summary（交叉对比表）**

| hotel_name | checkin_date | booking_double | booking_twin | jalan_double | jalan_twin |
|---|---|---|---|---|---|
| ホテルレガスタ… | 2026-06-16 | 15000 | 18000 | 14000 | 17000 |

**Sheet 2 — Booking / Sheet 3 — Jalan**

| hotel_name | platform | checkin_date | room_category | room_type | price | currency | status | created_at |
|---|---|---|---|---|---|---|---|---|

**Sheet 4 — Errors**

| platform | hotel_id | checkin_date | error | created_at |
|---|---|---|---|---|

**Sheet 5 — RunMeta**

运行统计：platforms, hotel_count, record_count, error_count

### 4.5 CLI 接口

```bash
python3 run.py \
  --config config.yaml \
  --env /path/to/.env \
  --output-dir output \
  --platform {all|jalan|booking} \
  --days {N} \
  --send-email
```

## 5. 验收标准

| 编号 | 验收项 | 验证方式 |
|---|---|---|
| A-001 | config.yaml 包含 6 家酒店正确配置 | 读取并验证 hotel_count=6 |
| A-002 | HotelPriceRecord 包含 room_category 字段 | 单元测试 |
| A-003 | 房型"ツインベッドルーム"分类为 twin | 单元测试 |
| A-004 | 房型"ダブルルーム"分类为 double | 单元测试 |
| A-005 | ④⑤⑥ 酒店跳过 Jalan 平台 | 集成测试 |
| A-006 | SCRAPER_CLASSES 只含 jalan 和 booking | 单元测试 |
| A-007 | Excel Summary 为交叉对比格式 | 手动验证 |
| A-008 | EMAIL_RECEIVERS 包含两个收件人 | .env 验证 |
| A-009 | python3 -m pytest tests/ 全部通过 | CI |
| A-010 | crontab 配置每周一 06:10 | crontab -l 验证 |

## 6. 测试要求

- **单元测试**：
  - 房型分类逻辑（double/twin/None）
  - build_records 多房型最低价选取
  - HotelPriceRecord.to_dict() 包含 room_category
  - SCRAPER_CLASSES 不含 trip
- **集成测试**：
  - Scheduler 跳过空平台 ID 的酒店
  - 单平台失败隔离
- **手工验证**：
  - 填入有效 cookie 后 `run.py --platform booking --days 1` 正常出报告
  - Excel 打开检查 Summary 格式

## 7. 实现约束

- **禁止事项**：
  - 不修改 `skills/common/su-scraper/` 旧代码
  - 不硬编码邮箱密码或 cookie
  - 不安装新 pip 包
  - 不删除 `TripScraper.py`（保留但不再引用）
- **依赖限制**：使用已有 pandas, openpyxl, requests, beautifulsoup4, pyyaml
- **性能约束**：请求间隔 ≥ 3 秒，并发 ≤ 2

## 8. 开放问题

- [ ] Cookie 获取方式仍需人工操作，后续可考虑自动化
- [ ] Trip.com 接入时间待定

## 版本记录

| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V1.0 | 2026-06-14 | 从 RFC-02-003 V2.0 派生，覆盖 6 酒店双房型重构 | YQuant |
