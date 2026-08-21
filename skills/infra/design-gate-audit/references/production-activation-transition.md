# Production Activation Transition

适用于通过 Design Gate 后仍包含生产 DDL/DML、真实 smoke、canary 或外部写入的 Full Flow。

## 放行条件不是上线许可

Design Gate 放行只允许创建离线 Implement。即使 Independent Verify 和 Review 后续均通过，也必须由用户针对具体生产动作、目标对象、影响和停止规则明确授权，才能创建独立 Activation 卡。

## 独立 Activation 卡

- `parents` 只链接到已完成的 Independent Review；不可混入 Implement / Verify / Review。
- 固化唯一 allow-list、禁止对象、最小权限身份、命令顺序、停止条件与非敏感证据。
- 用户授权不等于可以读取或记录凭据；只允许冻结脚本做最小存在性 preflight，禁止环境变量或 `.env` dump。

## 执行顺序

1. 零副作用 dry-run；失败即停止。
2. 最小泄露 preflight（key 存在性和身份边界）。
3. 单次 apply；不得自行扩权或重试。
4. 与 apply 分离的 readonly verify。
5. 单次 writer→reader smoke。
6. 单次 runtime canary；失败时禁用 optional 注入并保持主链 fail-open。
7. reader-only post-canary acceptance：不写新事件、不做 DDL/DML、不走 writer round-trip。

## 失败与报告

任一步失败即停止后续动作；不执行删除、角色轮换或范围外修复。报告仅含阶段、非敏感退出状态、已产生的授权对象类别及 fail-open 动作；不得写入凭据、连接串、原始 payload 或完整审计 params。