# Fail-fast vs Warn-and-Continue

## Golden rule

```text
Silent wrong output is worse than absent output.
If the user cannot notice the mistake before data write / outbound send / audit boundary, fail-fast.
```

反向表述：如果你不确定该 fail 还是 warn，问自己——"这个错误被忽略后，用户能在多晚才发现？" 越晚发现，越应该 fail-fast。

## Decision table

| 条件 | 决策 | 理由 |
|---|---|---|
| 可能导致数据写入错误位置、错误日期、错误集合 | fail-fast | 数据污染后难回滚 |
| 可能导致外部消息发错对象 | fail-fast | 隐私和审计风险 |
| 用户显式选择危险 flag，但实现无法保证语义 | fail-fast | no-op arg 比没有 arg 更危险 |
| 只读路径缺失，且有明确 fallback 数据源 | warn-and-continue | best-effort 可接受 |
| git dirty/unpushed 只影响审计，不改变当前只读检查 | warn | 可由操作者后续处理 |
| debug / preview 分支失败，不影响生产主路径 | warn 或 fail-fast，取决于该参数是否被用户显式请求 | 显式请求时应 fail-fast |

## P0 / P1 / P2 classification

| 等级 | 定义 | 默认动作 | 典型场景 |
|---|---|---|---|
| P0 | 生产数据、外部发送、交易/风控、安全边界可能被污染 | fail-fast | MongoDB 写入、Telegram/飞书外发、交易指令 |
| P1 | 调试、审计、可观测性、复盘质量受影响 | warn 或显式请求时 fail-fast | git dirty、marker mtime、log 文件缺失 |
| P2 | 风格、提示文案、非关键 best-effort | warn | 格式化提示、可选字段缺失 |

判定流程：

```
错误发生
  │
  ├─ 是否影响数据写入 / 外部发送 / 安全边界?
  │    └─ 是 → P0 → fail-fast
  │
  ├─ 是否影响审计 / 可观测性 / 复盘质量?
  │    └─ 是 → P1 → warn（或用户显式请求时 fail-fast）
  │
  └─ 其他（风格 / 文案 / best-effort）
       └─ P2 → warn
```

## Error message format

所有 fail-fast 错误消息必须包含四要素：

```text
[SanityCheck:<check_name>] <field> invalid.
expected: <期望>
actual: <实际>
next: <修复建议>
```

Warning 必须包含同样字段，但前缀为 `[SanityWarn:<check_name>]`。

**为什么强制四要素**：
- `field` 让用户知道是哪个输入/环境出问题。
- `expected` vs `actual` 让用户一眼看到差异。
- `next` 给出可操作的修复建议，而不是只说 "invalid"。

反例（禁止）：

```text
# 太模糊
ValueError: invalid input

# 缺 next
[SanityCheck:date] position_date invalid. expected YYYY-MM-DD, got 20260708

# 泄露秘密
[SanityCheck:mongo] connection failed: mongodb://user:password@host:27017
```

## Examples

### fail-fast（P0）

```python
# 生产写入 MongoDB，collection 必须在 allowlist 内
mongo_connection_check(
    boundary=MongoBoundary(
        database="tradingagents",
        collection="position_date",  # typo: should be portfolio_position
        allowed_collections={"portfolio_position", "portfolio_trade"},
        operation="write",
    ),
    connection_string=os.environ.get("MONGO_URL"),
)
# → SanityCheckError: [SanityCheck:mongo_connection_check] collection invalid...
```

### warn（P1）

```python
# 只读报告检查 git 状态，dirty 只影响审计
state = git_state_check(repo=".", allow_dirty=True, allow_unpushed=True)
if state.dirty:
    print(f"[SanityWarn:git_state_check] working tree dirty; audit trail may be incomplete")
```

### fail-fast when explicitly requested（P1）

```python
# 用户显式 --debug，但 debug 分支有 bug → 应 fail-fast，不能 no-op
interface_arg_check([
    ArgRule(name="--debug", enabled=args.debug, implemented=debug_branch_works),
])
```

## 与 validation / error handling 的关系

- **Sanity check**（本 skill）：输入形态/环境是否足以安全进入主逻辑。发生在业务逻辑之前。
- **Validation**（业务层）：业务对象是否满足业务规则。发生在业务逻辑内部。
- **Error handling**（运行时）：已进入主逻辑后的异常如何恢复。发生在业务逻辑之后。

如果一个检查同时涉及 sanity 和 validation，先做 sanity（形态闸门），再做 validation（业务规则）。不要把两层混在一个 try/except 里。
