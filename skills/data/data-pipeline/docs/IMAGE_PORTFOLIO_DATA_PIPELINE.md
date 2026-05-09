# Image Portfolio Data Pipeline

## 1. 整体流程

### 路径 A：图片 OCR → Excel（MiniMax CLI Vision）

```
Step 1: 图片采集保存
        用户发送多张图片 → 保存到 source/smart-money/YYYY-MM-DD/

Step 2: OCR 识别 → 生成 Excel
        MiniMaxImageExtractor（调用 mmx vision describe）
        → 扁平 DataFrame → 保存 Excel

Step 3: 数据入库
        Excel → PaddleOCRExcelTransformer → normalize → validate → MongoDB
```

### 路径 B：消息直接输入（无 OCR）

```
Step 1: 消息解析 → 保存 Excel
        用户发送 TSV/CSV 消息文本 → parse_text_to_df()
        → Excel → source/smart-money/YYYY-MM-DD/

Step 2: 数据标准化
        Excel → PaddleOCRExcelTransformer → normalize → validate → MongoDB
```

**两条路径在 Step 3 汇合，后续流程完全共用。**

### Step 2 技术选型（路径 A）
- **工具**：MiniMax CLI (`mmx vision describe`)
- **引擎**：MiniMax VLM 图像理解（云端 API，需网络连接）
- **输入**：本地图片（.jpg/.png）
- **输出**：标准 .xlsx Excel 文件，11 列
- **调用方式**：
  ```python
  from extractors import MiniMaxImageExtractor
  extractor = MiniMaxImageExtractor()
  records = await extractor.extract("/path/to/image.jpg")
  # records: [{"df": DataFrame, "source_path": "..."}]
  ```
- **Transformer**：
  ```python
  from transformers import PaddleOCRExcelTransformer
  transformer = PaddleOCRExcelTransformer()
  nested = transformer.transform(records)
  # nested: [{"daily_data": [...]}]
  ```

## 2. 数据流程（详细）

```
图片 (PNG/JPEG)
    ↓ OCR 识别 (Step 2)
Base64 String 或 扁平 DataFrame
    ↓ Base64Codec.decode() [serializers]
Nested JSON (daily_data 结构)
    ↓ Transformer [transformers/portfolio_normalizer.py / image_portfolio_normalizer.py]
标准化 JSON (basic_info / nav / position)
    ↓ Validator [validators/portfolio_validator.py]
校验通过的数据
    ↓ Loader [loaders/mongodb_loader.py]
TradingAgents MongoDB (172.25.240.1:27017)
```

## 3. JSON 数据结构

从图片 OCR 解析后得到的嵌套 JSON 结构：

```json
{
  "metadata": {
    "source": "image_ocr",
    "capture_time": "2026-05-02T10:30:00+08:00",
    "total_days": 1,
    "total_records": 236,
    "total_products": 5,
    "date_range": "2026-04-25"
  },
  "daily_data": [
    {
      "date": "2026-04-25",
      "products": [
        {
          "产品代码": "80PF11234",
          "产品名称": "景顺灵活1号",
          "最新净值": 1.2345,
          "最新份额": 2000000.00,
          "最新规模": 2469000.00,
          "positions": [
            {
              "Wind代码": "002415.SZ",
              "资产名称": "海康威视",
              "持仓比例": 0.1169,
              "数量": 139767,
              "市值(本币)": 26887000
            }
          ]
        }
      ]
    }
  ]
}
```

### 产品级字段（仅这些，不含截止日期/Wind代码）
- `产品名称`, `产品代码`, `最新净值`, `最新份额`, `最新规模`

### 持仓级字段
- `Wind代码`, `资产名称`, `持仓比例`, `数量`, `市值(本币)`

## 4. 模块归属

| 层级 | 模块 | 职责 |
|------|------|------|
| Codec | `serializers/base64_codec.py` | Base64 ↔ JSON 编解码（zlib 压缩） |
| Transformer | `transformers/portfolio_normalizer.py` | DataFrame → nested JSON |
| Transformer | `transformers/image_portfolio_normalizer.py` | nested JSON → 标准化记录 |
| Validator | `validators/portfolio_validator.py` | 数据质量校验 |
| Loader | `loaders/mongodb_loader.py` | MongoDB UPSERT |

## 5. 数据库表设计

### 5.1 portfolio_basic_info (产品基本信息)

产品维表，存储产品基础信息。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PRIMARY KEY | 自增ID |
| product_code | VARCHAR(32) | UNIQUE, NOT NULL | 产品代码 |
| product_name | VARCHAR(128) | NOT NULL | 产品名称 |
| latest_nav | DECIMAL(10,6) | | 最新净值 |
| latest_share | DECIMAL(18,2) | | 最新份额 |
| latest_aum | DECIMAL(18,2) | | 最新规模(元) |
| created_at | DATETIME | DEFAULT NOW | 创建时间 |
| updated_at | DATETIME | ON UPDATE NOW | 更新时间 |

**索引:** `idx_product_code` ON (product_code)

### 5.2 portfolio_nav (产品净值历史)

净值时序表，按日记录每个产品的净值和规模。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PRIMARY KEY | 自增ID |
| nav_date | DATE | NOT NULL | 净值日期 |
| product_code | VARCHAR(32) | NOT NULL | 产品代码 |
| nav | DECIMAL(10,6) | | 单位净值 |
| aum | DECIMAL(18,2) | | 资产管理规模 |
| share | DECIMAL(18,2) | | 最新份额 |
| created_at | DATETIME | DEFAULT NOW | 创建时间 |

**索引:** 
- `UNIQUE idx_date_product` ON (nav_date, product_code) — 日期在前
- `idx_product_code` ON (product_code)

### 5.3 portfolio_position (持仓明细)

持仓明细表，按产品+日期+资产存储持仓快照。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PRIMARY KEY | 自增ID |
| position_date | DATE | NOT NULL | 持仓日期 |
| product_code | VARCHAR(32) | NOT NULL | 产品代码 |
| asset_wind_code | VARCHAR(32) | NOT NULL | 资产Wind代码 |
| asset_name | VARCHAR(128) | | 资产名称 |
| holding_ratio | DECIMAL(10,4) | | 持仓比例(%) |
| shares | BIGINT | | 持仓数量 |
| market_value | DECIMAL(18,2) | | 市值(本币) |
| created_at | DATETIME | DEFAULT NOW | 创建时间 |

**索引:**
- `UNIQUE idx_date_product_asset` ON (position_date, product_code, asset_wind_code) — 日期在前
- `idx_product_code` ON (product_code)

## 6. 核心字段映射

| JSON字段 | portfolio_basic_info | portfolio_nav | portfolio_position |
|----------|---------------------|--------------|---------------------|
| 产品代码 | product_code | product_code | product_code |
| 产品名称 | product_name | - | - |
| 最新净值 | latest_nav | nav | - |
| 最新份额 | latest_share | share | - |
| 最新规模 | latest_aum | aum | - |
| 截止日期 | - | nav_date | position_date |
| positions[].Wind代码 | - | - | asset_wind_code |
| positions[].资产名称 | - | - | asset_name |
| positions[].持仓比例 | - | - | holding_ratio |
| positions[].数量 | - | - | shares |
| positions[].市值(本币) | - | - | market_value |

## 7. 增量更新策略 (UPSERT)

```
对于每条 daily_data:
1. UPSERT portfolio_basic_info (product_code 为 UK)
2. UPSERT portfolio_nav (nav_date + product_code 为 UK)
3. UPSERT portfolio_position (position_date + product_code + asset_wind_code 为 UK)
```

所有表均采用 **UPSERT** 策略：
- `INSERT ... ON CONFLICT (uk_fields) DO UPDATE SET ...`
- 保证幂等性，可重复执行

## 8. 当前状态

| 步骤 | 模块 | 状态 | 输出 |
|------|------|------|------|
| Step 1 | 图片保存 | ✅ | 7张图片在 `source/smart-money/2026-05-02/` |
| Step 2 | OCR → Excel | ❌ 待实现 | Excel 保存到同日期目录 |
| Step 3 | Excel → MongoDB | ✅ | 已有模块 |

## 9. Step 2 OCR 模块设计

**目标:** 图片 → 扁平 Excel → 保存到 `source/smart-money/YYYY-MM-DD/YYYY-MM-DD_portfolio.xlsx`

### 9.1 OCR 方案选择

| 方案 | 工具 | 评分 | 优点 | 缺点 |
|------|------|------|------|------|
| A | ClawHub `screenshot-ocr` | 3.458 | 即装即用，官方维护 | 通用场景，非金融表格优化 |
| B | PaddleOCR 自建 | - | 中文表格识别好，本地无API成本 | 需安装 |
| C | 第三方 API | - | 精度高 | 有成本 |

### 9.2 输出文件命名

```
source/smart-money/YYYY-MM-DD/YYYY-MM-DD_portfolio.xlsx
```

示例: `source/smart-money/2026-05-02/2026-05-02_portfolio.xlsx`

### 9.3 Excel 表头（扁平 DataFrame）

| 列名 | 说明 |
|------|------|
| 截止日期 | 持仓日期 |
| 产品名称 | 产品全称 |
| 产品代码 | 产品编码 |
| Wind代码 | 持仓资产代码 |
| 资产名称 | 持仓资产名称 |
| 持仓比例 | 占比(%) |
| 数量 | 持股数量 |
| 市值(本币) | 市值金额 |
| 最新净值 | 产品净值 |
| 最新份额 | 产品份额 |
| 最新规模 | 产品规模 |

### 9.3 文件结构

```
scripts/
├── extractors/
│   ├── base.py
│   ├── image_ocr.py      # NEW: 图片→DataFrame (PaddleOCR)
│   └── portfolio_ocr.py  # NEW: 调用 image_ocr，输出标准化 DataFrame
├── transformers/
│   ├── portfolio_normalizer.py    # DataFrame → nested JSON
│   └── image_portfolio_normalizer.py  # nested JSON → 标准记录
├── validators/
│   └── portfolio_validator.py
└── loaders/
    └── mongodb_loader.py
```

## 10. 示例数据

```
source/smart-money/2026-05-02/
├── portfolio_001.jpg
├── portfolio_002.jpg
├── portfolio_003.jpg
├── portfolio_004.jpg
├── portfolio_005.jpg
├── portfolio_006.jpg
└── portfolio_007.jpg
共 7 张图片，等待 OCR 解析
```

## 11. 待办事项

- [ ] 确定 OCR 方案（ClawHub skill 或 PaddleOCR）
- [ ] 实现 Step 2: 图片 → Excel（保存到 `source/smart-money/YYYY-MM-DD/YYYY-MM-DD_portfolio.xlsx`）
- [ ] 验证 7 张图片的 OCR → Excel 输出
- [ ] Step 3: Excel → MongoDB（复用已有模块）
- [ ] 更新 SKILL.md