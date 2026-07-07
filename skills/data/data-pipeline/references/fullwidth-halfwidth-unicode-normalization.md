# 全角/半角 Unicode 字符漂移 — OCR 名称匹配坑（2026-07-07 实战）

> **适用**：所有 OCR 解析股票名称 → 主数据匹配的 corrector 流程
> **修复 commit**：`scripts/transformers/a_share_name_corrector.py` `normalize_name_for_match()` 增加 NFKC 归一化

## 现象（用户反复卡 pending_review 的根因）

OCR 输出的中英混合股票名称里，**全角 ASCII 字母 vs 半角 ASCII 字母**是 unicode 不同码点，corrector 比较时不兼容：

| 输入 | 字符 | Unicode 码点 | 来源 |
|---|---|---|---|
| `京东方A` | `A` | U+0041（ASCII）| OCR 输出（半角）|
| `京东方Ａ` | `Ａ` | U+FF21（全角）| 主数据 `stock_basic_info` 的 `name` 字段（全角）|

`.upper()` 对 ASCII 字母保持 U+0041，对全角字母返回**同码点 U+FF21** → 比较时 `0x41 ≠ 0xff21` → `pending_review`。

## 为什么之前 `stock_name_corrections.py` 映射没生效

`stock_name_corrections.py` 之前有 `000725.SZ → 京东方Ａ`（2026-06-29 加）。但：

1. 映射配置正确 ✅
2. `correct_stock_names()` 调用 `names_are_compatible(ocr_name, expected_name)`
3. `names_are_compatible()` 内部调用 `normalize_name_for_match()` 做归一化
4. **`normalize_name_for_match()` 缺 NFKC 归一化** ❌
5. `normalize('京东方A')` 和 `normalize('京东方Ａ')` 结果不同
6. → `names_are_compatible` 返回 `False` → `pending_review`

用户反馈「之前已配为啥还卡」就是这个原因：**配置了映射 ≠ corrector 真的能匹配**。

## 修复（已部署）

```python
# scripts/transformers/a_share_name_corrector.py
import unicodedata

def normalize_name_for_match(name: Any) -> str:
    """Normalize stock names for conservative OCR/master-data comparison."""
    value = str(name or "").strip()
    if not value or value.lower() in {"nan", "none"}:
        return ""
    # NFKC normalization: fullwidth ASCII (e.g. Ａ U+FF21) → ASCII (A U+0041)
    # 必须放在 .upper() 之前，否则全角字母仍保留 U+FF21
    value = unicodedata.normalize("NFKC", value)
    value = _NOISE_CHARS_RE.sub("", value.upper())
    value = _CORPORATE_ACTION_PREFIX_RE.sub("", value)
    return value
```

## NFKC 影响范围

| 字符类型 | NFKC 行为 | 影响 |
|---|---|---|
| 全角 ASCII 字母 `Ａ` `Ｚ` | → ASCII `A` `Z` | ✅ 修复京东方A 类 |
| 全角 ASCII 数字 `１` `９` | → ASCII `1` `9` | ✅ 修复全角数字 |
| 全角空格 `　` | → ASCII 空格 | ✅ 修复全角空格 |
| 全角标点 `（）` `-` `：` | → ASCII `()` `-` `:` | ✅ 与 `_NOISE_CHARS_RE` 协同 |
| CJK 中文 `京东方` | 不变 | ✅ 不影响中文 |
| 形近字（如 `科` vs `利`）| 不变 | ✅ 故意不兼容，避免幻觉匹配 |

## 端到端验证（2026-07-07 实测）

| 场景 | 修复前 | 修复后 |
|---|---|---|
| SM002 portfolio 2026-07-07 pending_review | 1（京东方A）| **0** |
| 京东方A 行状态 | pending_review | **auto_corrected** |
| `names_are_compatible("京东方A", "京东方Ａ")` | False | **True** |
| `names_are_compatible("京东方a", "京东方Ａ")` | False | **True**（小写也兼容）|
| `names_are_compatible("京东方A", "京东方B")` | False | False（保持拒绝无关名）|

## 同类潜在风险（待观察）

未来如果出现以下字符漂移，NFKC 已经覆盖：

- 全角英文字母（`ａ` `Ａ` `Ａ`）
- 全角数字（`０` `１` `９`）
- 全角空格（`　`）
- 全角标点（全角括号、冒号、减号等）

**不覆盖**（必须用别的方法处理）：

- 形近字误读：`科→利`、`联→联`、`浦→湳` 等 OCR 字符级错误
- 完全错误名（如 `京东方` → `京东东方` 多字、少字）
- 这些靠 `stock_name_corrections.py` 静态映射或用户确认，不靠 NFKC

## 修复要点（one-liner 风格）

**任何「OCR 字符串 vs 主数据字符串」比较的 corrector，归一化函数第一行**必须是：

```python
value = unicodedata.normalize("NFKC", value)
```

放在 `.upper()` / `.lower()` / `.strip()` **之前**。否则全角字符仍保持原码点，等于没做归一化。

## Pitfall — 同样的问题在何处还可能存在

`asset_identity_review.py` 的 `standardize_asset_name()` 也用了 `str.maketrans()` 把全角转半角：

```python
"ＷＸＹＺＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶ" → "WXYZABCDEFGHIJKLMNOPQRSTUV"
```

这个 function 是为了**统一显示**（输出侧），方向是"全→半"，对缓存展示一致。但在 corrector 内部被调用时：

- `standardize_asset_name` 先把 `Ａ` 转 `A`
- `correct_stock_names` 再比较 `京东方A` vs 主数据 `京东方Ａ`
- → 比较失败

实际生产中 `standardize_asset_name` 调用在 Excel/CSV 输出阶段，**不**在 corrector 比较阶段。所以现在两者不冲突。**但**未来如果有人在 corrector 里也调用 `standardize_asset_name`，会触发同样问题。**建议**：`standardize_asset_name` 改为 NFKC-only，去掉 ASCII translate 表（让 NFKC 统一处理）。

## 关联资源

- 修复位置：`scripts/transformers/a_share_name_corrector.py::normalize_name_for_match`
- 使用方：`scripts/transformers/asset_identity_review.py::correct_stock_names`
- 调用链：图片入库 → OCR 输出 → `correct_stock_names` → `names_are_compatible` → `normalize_name_for_match` → NFKC + upper + 噪声去除
- 涉及产品：A 股全市场（含港股通的 A 股 + 中概股 + 港股 + 美股 ADR）
