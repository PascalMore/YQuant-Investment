# Timeout 后的产物审计与验证接管

适用于共享 `dir` 工作区的工程卡在实现阶段因 iteration budget / runtime timeout 被 dispatcher 自动重试时。

## 核心规则

1. **Timeout 不等于失败，也不等于通过。**先读取卡片的 run/event，再以当前磁盘为准。
2. **禁止盲重试。**若 dispatcher 已自动重新领取旧卡，先用 `kanban_comment` 记录审计证据，再 `kanban_block(kind="transient")` 冻结旧卡，避免多个 run 在共享树继续叠加修改。
3. **先核验实物范围。**至少检查：
   - `git status --short --untracked-files=all`
   - `git diff --check HEAD`
   - 计划 allowlist 的存在性、mtime 及 allowlist 外生成物（尤其 `__pycache__` / `.pyc` / runtime report）
   - 缺失的文件、缺失的测试与未运行验证。
4. **按产物成熟度路由，不从头重做：**
   - 产物不完整：建立一个最小 recovery implement 卡，先审计继承文件，再只补缺失切片；禁止 `reset/stash/clean`。
   - 产物完整但原实现卡未完成 handoff：建立独立 Verify 卡，明确“开发者自报不作为证据”，由 tester 实跑测试、回归、compile、范围和静态安全审计。
   - 独立 Verify 通过：再进入最终 Review；不得因 timeout 跳过 Verify/Review。
5. **过程证据与功能结论分离。**若 timeout 导致严格 TDD 的 RED→GREEN 时序没有持久日志，必须在 Verify/Review 中标为“不可独立重建的过程限制”；不能伪称已证明，也不应在功能、测试、范围和安全证据充分时自动降格为功能失败。
6. **生成型 pycache 的处理。**测试尽量以 `PYTHONDONTWRITEBYTECODE=1` 运行。`compileall` 仍可能生成 gitignored bytecode；将其作为卫生备注，与源码 allowlist 越界分开判断，且不要用 reset/stash/clean 清理共享树。

## 验证接管最小命令集

```bash
git status --short --untracked-files=all
git diff --check HEAD
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest <target-tests> -q
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest <existing-regression> -q
.venv/bin/python -m compileall -q <new-package>
```

独立 Verify 还应静态检查：默认路径不触发真实 Mongo / Provider / 网络 / DDL/DML / backfill，敏感连接值不写入 report/log，且冻结路径没有被当前 rollout 修改。

## 验证脚本与实现契约的耦合（假 FAIL 防线）

独立 Verify 自带的断言脚本如果把**实现细节写死**（例如断言“守卫读取历史累计字段”），那么一次合法修复之后同一断言会给出**假 FAIL**，并把正确实现推进返修链。

- 断言必须**绑定实际安装文件**：从磁盘上的脚本/配置读出被测谓词或字段再判定，而不是用脚本里另写一份模型。
- 修复前的断言脚本保留为 **RED 对照**时，必须在卡内写明它指向修复前快照、只用于证明断言有区分力，不作为新实现的验收依据。
- 硬编码旧控制流的逻辑模型只能用来复现旧缺陷，不能当新实现的行为证据；新实现要另建绑定实际守卫的模型。
- 返修卡要显式列出“哪些旧产物是历史证据、不可原样重跑”，否则 worker 会反复用旧脚本复跑失败并再次 timeout。

## 看板写入的 payload 形状

`kanban edit --metadata` 携带大 JSON 内联时会撞命令长度上限（命令未执行）。把 payload 写入文件后用短命令引用，或拆成更小的写入；被拦下即视为未执行，记录实际已确认与未确认的部分，不用改写命令形态试探边界。

## Kanban 交接格式

冻结旧卡的 comment 应说明：timeout run id、当前已存在/缺失文件、allowlist 外生成物、已运行与未运行检查、为何不能宣布通过。新的 recovery 或 verify 卡必须引用旧卡，但其 parent 应链接最后一个稳定的已通过 Gate，而不是被 block 的旧卡，避免 dependency 永远不就绪。
