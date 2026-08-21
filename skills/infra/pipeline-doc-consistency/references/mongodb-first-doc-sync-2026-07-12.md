# MongoDB-first 文档同步复盘（2026-07-12）

## 场景
YQuant 同时规划三条主线：`unified_data`、`task_center`、`stock framework`，各自产出 RFC / SPEC / Design 共 9 份文档。Design 阶段用户明确要求：

- `unified_data` 新增持久化使用 MongoDB，集合前缀 `03_data_ud_*`；DSA SQLite 只读 legacy adapter。
- `task_center` MVP / 默认 / 生产持久化使用 MongoDB，集合前缀 `10_infra_tc_*`；SQLite 仅本地测试 / 离线降级。
- `stock framework` 持久化使用 MongoDB，集合前缀 `08_research_stock_*`；禁止 SQLite 作为 MVP / 默认 / 生产存储。

## 教训
用户在 RFC/SPEC 完成后补充的“数据库选择 / 集合前缀 / 禁止 SQLite 主路径”是设计类决策，不是实现细节。只在 Design 或下一阶段 task body 写入不足够；必须回头同步 RFC / SPEC，否则 developer 同时读三层文档时会被旧的 SQLite-first 语义误导。

## 推荐 SOP
1. 用户确认持久化策略后，立即判断是否影响已完成 RFC/SPEC/Design 的准确性。
2. 若影响：
   - 在 RFC/SPEC 顶部或 Changelog 后加入“Design 阶段修订说明”；
   - 清理正文中的旧主路径描述，例如 `SQLite 优先`、`SQLite MVP`、`SQLite 默认`、`SQLite 表结构（MVP）`、`MongoDB 可选 Phase N`；
   - 保留 SQLite 时必须明确是“本地测试 / 离线降级 / 外部 legacy source adapter”，不是生产或 MVP 主路径。
3. 用 grep/脚本做残留检查，至少覆盖：
   - `SQLite 优先`
   - `SQLite 为默认`
   - `SQLite 默认`
   - `SQLite 表结构（MVP）`
   - `SQLite 文件`
   - `MVP 实现 SQLite`
   - `MongoDB 后端切换`
   - `SQLite → MongoDB`
4. 对跨模块命名决策同步所有相关文档：
   - unified_data: `03_data_ud_*`
   - task_center: `10_infra_tc_*`
   - stock framework: `08_research_stock_*`
5. 正式进入 Implement 前，派 reviewer 做“9 份文档一致性审查”；若 verdict 是 `PASS_WITH_FIXES`，orchestrator 先修 blocking，再创建首个 Implement task。

## 低成本修复清单示例

- `10-008` → `10-009`：修正新文档对 task_center 的编号引用。
- `ud_cache_*` → `03_data_ud_cache_*`：统一 unified_data 新增集合前缀。
- `task_centr` → `task_center`：修正 callable path typo。
- `MongoDB 后端切换` → `SQLite 离线降级完善`：当 MongoDB 已是主路径时，不能把 MongoDB 描述成未来切换项。

## 实现顺序建议
当三条线互相依赖时，优先实现数据底座：

1. `unified_data Phase 0` — skeleton + core abstractions。
2. `unified_data Phase 1` — read-only adapters / canonical service。
3. `task_center Phase 0` — core entities + state machine。
4. `task_center Phase 1` — MongoDBBackend。
5. `stock framework Phase 0` — core entities + mongo schema。
6. `stock framework Phase 1` — profile builder + first models。

原因：stock framework 消费 unified_data；task_center 负责调度但不能替代 canonical data service。过早实现 stock 会造成大量 mock 和返工。

## Review task shape

For a 9-doc review, ask reviewer to return:

- `verdict`: PASS / PASS_WITH_FIXES / REVISE
- blocking issues with file path and locatable text
- non-blocking suggestions
- first recommended Implement task
- residual risks

If `PASS_WITH_FIXES`, orchestrator may directly fix document blockers, then create the first Implement task without a second review if the fixes are mechanical and verified by search.