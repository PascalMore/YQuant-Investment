# 设计复审预算耗尽：可审计恢复模式

适用于 Full Flow T2 Design Review：审查目标（长设计文档 + 多份基线代码）超过单 reviewer 卡的预算，导致 `blocked`、timeout 或无 verdict。

## 不可替代的证据

`blocked`、budget 耗尽、timeout、worker/dispatcher 状态、clean exit 均不是审查结论。放行或退回只能依据明确的 `APPROVE` / `REVISE` / `BLOCK`，并且有 task run、summary/metadata、评论和父卡证据支持。

## 恢复链

1. 保留原 blocked 卡并 comment 记录“范围/预算不足”的精确原因；不要原样盲重试。
2. 将 review 按可独立验收面拆成 2–3 张 reviewer 卡：
   - 架构、query-read-only、注入、文件矩阵；
   - schema、provenance、freshness、Provider 事实；
   - explicit refresh 写语义、授权 Gate、安全边界、文档闭合。
3. 每张分段卡要求 `PASS` / `FAIL`，每项包含 `severity + file:line + 是否阻断 + 最小修正验收`；仅运行 scoped `git diff --check` 与最小静态检索。
4. 创建 synthesis reviewer 卡，parents 指向所有分段卡：任一 blocker FAIL → `REVISE`；任一无明确 PASS/FAIL → `BLOCK`；仅全 PASS 且三层文档一致 → `APPROVE`。
5. `REVISE` 后仅创建 scope-locked principal Design Correction；修订后必须重新独立复审，绝不复用旧 verdict。

## 高价值事实交叉检查

- “query 只读”是否与 Router materialize/cache 写分支冲突；
- adapter 的实际存在性、key model 与业务集合/多记录写入是否兼容；
- provider fetch success 是否与 persistence success 错误混同；
- cache materialization 是否单独 Gate；
- dataclass 字段数、序列化、fixture 与 provenance 字段是否闭合；
- TTL/capability/依赖注入是否把计划项错误写成已存在；
- OQ 若改变 schema、唯一键、粒度或路由，必须在 Design 冻结或保持 stub，不能推给 T3。

## 安全下界

Review 和 Design Correction 均不得读取凭据、触网、调用真实 Provider/API、连接 Mongo、执行 DDL/DML、安装依赖、commit/push。Design Review PASS 也不授予任何 Activation 或生产权限。