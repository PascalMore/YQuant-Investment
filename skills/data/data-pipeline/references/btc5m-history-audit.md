# BTC5m 官方历史同步只读审计

适用于 `run_btc5m_history.py` / `btc5m_history` 与 Unified Data 窄历史读取。用当前源码和冻结契约确认字段，不将此流程变成新的生产门禁。

1. **先明确审计与恢复授权。** 排查只读Mongo/原档/契约；报告证据可写主题目录，未经明确授权不启动apply、不修改due/cursor/日state/标签、不新增cron。
2. **程序化枚举全部批次。** 首批可能叫`first-batch`，不以不存在`01/`断言缺批；逐份保SHA、计划日期、实际结果日期、inserted/updated/skipped及已知原生退出。核“先前基线+本轮新增=当前实库”，不能只累计某一段流水。
3. **空results不代表成功。** 核HTTP异常是否只写stderr、summary是否保存退出/错误。缺失原生退出记UNKNOWN，不能根据summary存在补认成功。
4. **按UTC半开窗口核真实槽。** rounds同时报告实际行/唯一名义槽/标签状态/完整日；价格扫描全部时间戳并结合实际唯一索引核每日日槽、秒对齐和首尾。只对部分日枚举缺秒区间，避免把“已有部分行”说成整日全缺。两源联合完整日需另算。
5. **数据、日账、原档三方核对。** 行都在但日conflict、日raw_manifest_ref为空、标签未观察到，分别列出；检查点不是数据真相，行数也不证明已闭合。只读hash/CRC核验不等于所有业务字段已与官方原文语义重放。
6. **核两层回查时钟和闭合条件。** next_retry_at控制日计划，next_check_at控制按ID队列。先查真实日raw_manifest_ref，再看recheck_pending是否会重核日；缺日引用时，即使旧Flat转DRAW也可能仍需正常日枚举/提交来补证。到期日重新采集也可能早于按ID队列提供合法更新，不能把某一时钟变成额外禁令。
7. **追踪真实退避实现。** 分清HTTP内部有限重试与日级冷却；固定一天是本地策略时，不描述为官方封禁。对声称递增的backoff，用纯内存、准时调用探针验证，不从docstring推断。
8. **分别核扫描闭合、枚举水位、连续完整水位。** scan.closed不等于enumerated_through已维护；连续水位从锚点遇缺即停，不可用最大已存时间替代。旧错误码不表示当前仍有同一故障。
9. **daily规划必须与apply参数等价。** 确认是否传stream锚点，默认无窗口plan可能遗漏完全没有日账的日期。固定回填外的最新完整UTC日单列为未接上的增量，不计进原分母。
10. **无人值守先核安全凭据接线。** 人工批次私有文件注入成功，不证明daily wrapper自带加载。只检查环境变量是否存在，永不打印值；裸进程缺变量也不证明gateway环境必缺。正式scheduler环境与真实daily须独立验证。
11. **研究边界单列。** 零预热锚点后追加warmup可能冲突；不得擅改锚点。Binance成交OHLCV不是盘口mid或Predict oracle；observed与event-time-proxy不等于严格历史PIT。冲突日可能抑制整日标签，不能以数据库resolved数量代替reader输出数量。
12. **输出一个收口清单。** 区分确实缺数据、已存待闭合、已证实实现问题、条件恢复风险、未完成验收；明确本轮实际核验范围。保留真实写入幂等、部分资源恢复、daily和独立生产Verify要求，但不复制平台/任务图或以重复只读代替写入幂等。

复现连接优先使用现有CLI `_open_store()`；Python用项目`.venv/bin/python -B`，不使用execute_code或手拼凭据。审计脚本和矩阵存`data/reports/<主题>/evidence/`。全量语义验证较重时复用原verify预算与resume能力，不为快速审计擅自修改验证实现。

## 重型 verify 的预算与续核边界

- 先读当前verify实现的两阶段顺序：逐日内容/原档检查之后，还可能逐分片再次绑定消费前后快照。一次把整个长窗口塞进墙钟预算，可能第一阶段用尽预算，最终复核没有完成。
- 退出10后直接读取summary的`verified_content`、`verified_snapshots`及各分片`complete`；第一阶段`coverage_ok/raw_bytes_verified=true`不等于最终PASS。若verified集合为空，原样resume只会重算，不能称为从已完成日继续；保留原partial报告与真实退出。
- 无需改代码即可按既有verify入口使用更小的互斥半开窗口，每段各自留够最终复核预算。跨窗不要传旧resume-report，因为窗口/预算绑定不一致会被拒绝；只在同窗且存在有效已验证分片时复用resume。
- 只读分段可在核实CPU/内存与无生产摄入后有限并行，生产apply仍按原授权串行。聚合以真实native0、完整分片键集合和最终内容/原档证明为准，程序化核对总窗口无重叠/缺日；不把第一阶段诊断计数累计成PASS，不因预算未完成重新补数或扩建任务图。

