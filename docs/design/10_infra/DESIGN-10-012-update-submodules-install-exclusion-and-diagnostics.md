# DESIGN-10-012：update_submodules install 排除与诊断优化

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Accepted |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-10-06 |
| 最后更新 | 2026-10-06 |
| 来源 RFC | docs/rfc/10_infra/RFC-10-012-update-submodules-install-exclusion-and-diagnostics.md (V1.1) |
| 来源 SPEC | docs/spec/10_infra/SPEC-10-012-update-submodules-install-exclusion-and-diagnostics.md (V1.1) |
| 版本号 | V1.1（t_13d22c5e，既有契约勘误） |
| 前版文档 | DESIGN-10-008-update-submodules-script（V2.0，实现基线） |
| 目标脚本 | `scripts/upgrade/update_submodules.py`（v2.1.0 → v2.2.0） |
| Full Flow | Quick Flow T1=t_c1e60718（T2=Implement, T3=Verify, T4=Closeout） |

## 1. 设计摘要

在 10-008 V2.0 既有骨架上做三处增量：`SubmoduleConfig` 增加 `install_exclude` 字段并沿 opt-in 链路（validate_override → merge_override → _replace_config）透传；`phase_install` 在 pip 前生成 requirements 过滤根副本；`classify_pip_failure` 在分类不变的前提下对 sample 做"包名+版本约束优先"二次选择。核心取舍：只改变直接引用根文件中的包排除，保留 pip requirement 选项及嵌套引用解析语义；为迁移根副本必须重定位其中的相对 -r/-c 引用，原 requirements 不动、失败可 fail-fast。P2 采用内容特征优先而非位置启发（首行/末行），因为 pip stderr 无稳定顺序契约。本轮为旧 Closeout t_b5d45087 所指三缺陷与错误示例的勘误，不是新增设计阶段。

## 2. 现状分析

- 相关目录：`scripts/upgrade/`、`tests/scripts/`、`skills/research/daily_stock_analysis/`。
- 相关文件与锚点（v2.1.0 实测行号）：
  - `scripts/upgrade/update_submodules.py:32` — `__version__ = "2.1.0"`
  - `:104-120` — `SubmoduleConfig` frozen dataclass（新增字段须同步全部构造点）
  - `:520-565` — `discover_submodule()`（默认值构造点）
  - `:573-603` — `validate_override()`（opt-in 字段白名单）
  - `:627-682` — `merge_override()` / `_replace_config()`（字段透传）
  - `:855-884` — `phase_install()`（P1 落点）
  - `:890-927` — `_PIP_ERROR_PATTERNS` 六类 + `_PIP_HINTS`（禁改）
  - `:930-951` — `classify_pip_failure()`（P2 落点）
  - `:1219-1265` — `write_audit()`（无需改动，degraded 走 detail 文本）
- 现有约束：5 阶段结构 / merge abort / push 默认 / 分类六类与 pattern 顺序禁改（RFC §3.2）；单文件标准库；`run_cmd` 禁 `shell=True`。
- 兼容性风险：frozen dataclass 加字段会破坏任何未更新的构造点——v2.1.0 构造点仅 `discover_submodule()` 与 `_replace_config()`，全量覆盖；测试文件经 `_load_module()` 动态加载，无序列化兼容问题。

## 3. 方案设计

### 3.1 模块/文件改动

| 文件 | 改动 | 原因 |
|---|---|---|
| `scripts/upgrade/update_submodules.py` | `__version__`→`"2.2.0"`；`SubmoduleConfig` 加 `install_exclude: tuple[str, ...] = ()`；`discover_submodule` 默认 `()`；`validate_override` 白名单加 `install_exclude`（list[str] 校验，非法 warning 丢弃）；`merge_override`/`_replace_config` 透传（tuple 化）；新增内部 helper `_normalize_pkg_name()`、`_filter_requirements()`、`_prefer_constraint_sample()`；`phase_install` 接入过滤与 degraded detail；`classify_pip_failure` sample 二次选择 | F-001~F-004 |
| `tests/scripts/test_update_submodules.py` | 文件头 docstring 用例索引补 UT-020~UT-032；新增 13 个用例（见 §5.1） | A-100~A-115 |
| `skills/research/daily_stock_analysis/.update_submodules.yaml` | 新建，内容为 SPEC §4.4 三行 | F-005/P3 |

不改动：`write_audit`、`_PIP_ERROR_PATTERNS`、`phase_restart`、`phase_push`、merge/push 相关函数、CLI parser。

上述表为初始 T2 历史清单；本轮 Fix-2 代码 allowlist 仅前两项脚本与现有测试，禁止新建/修改 P3 yaml 或任何子模块/生产配置；c27720fa 原样保留。授权与禁止动作以 SPEC §7 为准，§3.6/§6 的历史提交、推送、重启和回滚方案均不是本轮执行许可。

### 3.2 数据流/控制流（P1）

```text
process_submodule
  └─ load_optin_override → validate_override（+install_exclude 校验）
       → merge_override（cfg.install_exclude = tuple(...)）
  └─ phase_install(state)
       ├─ cfg.install_exclude 为空 → 现路径不变
       └─ 非空:
            ├─ 解析 pip cmd 中 -r/--requirement（含等号形式）→ 根 req_paths
            │    └─ 空 → log_warn("install_exclude 无 -r 引用, no-op")
            ├─ for each 根 req: _filter_requirements(req, exclude) → 独立 tempfile 副本
            │    └─ 写失败 → _make_fail("install", ...)
            ├─ 根副本中相对 -r/-c 引用重定位至原文件，嵌套包不递归排除
            ├─ pip cmd 保留 requirement 选项，路径指向副本 → run_cmd
            ├─ 成功: excluded_hit 非空 → detail="install (excluded: a, b): OK (degraded)"
            │        excluded_hit 空 → detail="pip install OK" + 未命中清单行
            └─ 失败: classify_pip_failure(原文) → 既有 fail 路径（sample 走 P2）
       finally: 清理已创建目录，覆盖源缺失/写失败/pip 失败/成功/dry-run
```

P2 控制流（`classify_pip_failure` 内部，签名不变）：

```text
lines = 非空行; head = 末 60 行
for name, pat in _PIP_ERROR_PATTERNS:          # 不变
    if pat.search(head):
        matched = [ln for ln in lines if pat.search(ln)]
        return (name, _prefer_constraint_sample(matched, pat))
                                     # 新增: 优先"包名+版本约束"行, 无则 matched[0]
```

### 3.3 接口与数据结构

- 新增（模块内私有，不进任何 `__all__` 式导出面）：
  - `_normalize_pkg_name(name: str) -> str`：PEP 503 规范化（`re.sub(r"[-_.]+", "-", name.strip().lower())`）。
  - `_filter_requirements(req_path: Path, exclude: tuple[str, ...]) -> tuple[Path, list[str]]`：返回（过滤根副本路径, 实际命中并删除的原始包名列表，去重保序）。现实现的 `tmpdir` 可选参数保持内部接口，不新增公开 API；行处理与必要引用重定位按 SPEC §4.2。
  - `_prefer_constraint_sample(matched_lines: list[str], pattern: re.Pattern) -> str`：在命中行内优先选含包名+版本约束 token 的行（SPEC §4.3 三级规则），实现可用独立正则 `r"[A-Za-z0-9._-]+\s*[<>=!~]"` 或 `r"found for\s+\S+"` 探测，不与分类 pattern 耦合。
- 修改：`SubmoduleConfig`（+1 字段）、`validate_override`/`merge_override`/`_replace_config`/`discover_submodule`（透传）、`phase_install`（P1 编排）、`classify_pip_failure`（sample 选择一行换为 `_prefer_constraint_sample`）。
- 废弃：无。

### 3.4 持久化设计（Persistence Design）

无新增持久化。P1 过滤根副本写入触发点为 `phase_install()` 内 `_filter_requirements()`，使用 `tempfile` 临时目录（可由 TMPDIR 指定），清理生命周期为一次 `phase_install`，不是整个进程。`try/finally` 必须包住目录创建后的所有操作和提前返回；源文件缺失、写副本失败、pip 失败、成功及 dry-run 均清理已创建目录。写入内容仅根文件保留行及必要引用重定位；不写回原文件。错误处理 = 源缺失或 OSError → install fail，不回退为全量安装。按 SPEC A-108 用本地 fixture/异常替身验证完整清理矩阵。

最小实现约束（来源：既有 §1 保留 pip 语义目标、SPEC F-002/§4.2、SPEC §7 清理契约；直接针对根副本迁移、argv 改写与提前 return 的副作用，不新增门禁）：
- 根副本中的相对 `-r`/`--requirement`、`-c`/`--constraint` 引用改为相对于原根目录的绝对引用；保留选项、其余参数及非引用行。嵌套文件仍由 pip 读取原件，后续引用自然以各原文件目录解析；不递归复制或排除嵌套包。
- 多个直接引用的根文件使用独立副本位置，避免同名文件互相覆盖。
- 分离参数只替换路径 token；等号参数保留 `--requirement=`（或既有 `-r=`）前缀。保留 Fix-1 的 pip 前缀索引偏移，不将选项误替换为裸路径。
- 清理作用域必须从临时目录创建后立即覆盖过滤与 pip 执行全路径，不能把源缺失/写失败 return 留在 finally 之外。

### 3.5 UI/原型设计

无。

### 3.6 P3 yaml 落盘与 dirty_worktree 规避（初始 T2 历史方案）

本轮不执行本节：只读核对 DSA HEAD 为 c27720fa68d6f56dfc882b2795dc16c47ccf05d8、子模块内部工作树干净；保留该历史状态，待 Pascal 确认，不修改 yaml、exclude、提交或推送。下文是初始 T2 对首次落盘的约束，不代表当前 yaml 仍 untracked。

`.update_submodules.yaml` 位于 submodule 工作树内。`process_submodule` 的 dirty 检测用 `git status --porcelain`（update_submodules.py:1079），**untracked 文件会命中**，untracked yaml 将导致 `--apply` 直接 `dirty_worktree` abort。因此 T2 必须二选一（推荐 a）：

- a. 提交该 yaml 到 submodule 的 **origin fork**（`git@github.com:PascalMore/daily_stock_analysis.git`）并 push——它是 Pascal fork 的运维配置，与 upstream 无冲突面；由用户日常 fork 维护流承载。
- b. 临时方案：`git -C skills/research/daily_stock_analysis` 执行 `echo .update_submodules.yaml >> .git/info/exclude`（本地排除，不污染 upstream merge）。

禁止留 untracked。submodule 提交属生产 fork 变更：T2 落盘文件后，提交动作须由用户确认（Quick Flow T2 卡片 body 已含此交接项）。

## 4. 实现计划

以下为初始 T2 历史计划；本轮仅执行 §3.4 的三项最小修复与 §5.2 的限定回归，不重做 P3 落盘或新增设计阶段。

- [ ] Step 1：`SubmoduleConfig` + `install_exclude` 字段与全部构造点/透传链（含默认值），`__version__=2.2.0`。
- [ ] Step 2：`_normalize_pkg_name` + `_filter_requirements`（纯函数，先行 TDD）。
- [ ] Step 3：`phase_install` 接入过滤、degraded detail、临时文件 fail 路径。
- [ ] Step 4：`_prefer_constraint_sample` + `classify_pip_failure` 接入（分类断言不变）。
- [ ] Step 5：UT-020~UT-032 全绿；既有 UT-001~UT-019 回归全绿。
- [ ] Step 6：落盘 P3 yaml（按 §3.6 策略 a 或 b），dry-run 冒烟确认 merge 生效。

## 5. 测试策略

### 5.1 新增用例（`tests/scripts/test_update_submodules.py`）

| 用例 | 覆盖验收项 |
|---|---|
| `test_install_exclude_field_default` | A-100（默认空 tuple，heuristic 构造点） |
| `test_optin_install_exclude_applies` | A-100（yaml 声明 → merge 后 tuple） |
| `test_optin_install_exclude_invalid_type` | A-101（非 list / 元素非 str → 丢弃 + 空 tuple） |
| `test_filter_requirements_anchored_line` | A-102（命中整行删除，注释/选项/其他行保留） |
| `test_filter_requirements_no_substring_match` | A-103 |
| `test_filter_requirements_pkg_name_normalized` | A-104 |
| `test_phase_install_degraded_detail` | A-105（mock run_cmd exit 0） |
| `test_phase_install_exclude_miss_listing` | A-106 |
| `test_phase_install_no_r_ref_warning_noop` | A-107 |
| `test_phase_install_tempfile_fail_is_fail` | A-108（patch tempfile 抛 OSError） |
| `test_classify_sample_prefers_constraint_line` | A-109（fixture = §5.2 冻结文本） |
| `test_classify_sample_fallback_first_match` | A-110（仅 yanked 行时回落） |
| `test_daily_stock_analysis_optin_merge` | A-111 + A-112（合法生效 + 破损回落；参数化） |
| `test_version_bump_and_help_unchanged` | A-114 |

### 5.2 fixture（冻结文本，逐字取自 2026-10-06 audit 实录）

```python
REAL_PIP_STDERR_20261006 = (
    "ERROR: Ignored the following yanked versions: 0.2.2, 0.2.3, 0.2.4, 0.2.5, 0.2.6\n"
    "ERROR: No matching distribution found for longbridge<5,>=4.0.5\n"
)
# 断言: classify -> ("missing_dependency", "ERROR: No matching distribution found for longbridge<5,>=4.0.5")
# 注: v2.1.0 实测 sample 为 yanked 行（audit 20261006_121344 实录）; v2.2.0 起必须选第二行。
```

过滤用 requirements fixture：

```text
# requirements_fixture.txt
tushare>=1.4.0              # Priority 2
-r extra-reqs.txt
# Longbridge 4.x Linux wheels currently require manylinux_2_39.
longbridge>=4.0.5,<5; platform_system != "Linux" or python_version >= "3.12"
longbridge==0.2.74; platform_system == "Linux" and python_version < "3.12"
tickflow>=0.1.24
```

排除 `longbridge` 期望：两个 longbridge 行删除，注释/tushare/tickflow 行逐字保留；`-r extra-reqs.txt` 在迁移根副本中只做必要路径重定位，仍由 pip 读取原目录的 extra-reqs.txt；其中的包不参与递归排除。`excluded` 命中列表 = `["longbridge"]`（原始包名去重保序，F-003 detail 同步）。包名规范化案例按 SPEC A-104：`Long_Bridge` → `long-bridge`，不等价于 `longbridge`，保留既有正确代码/测试。

Fix-2 回归补充限定在现有测试文件：分离 `-r`/`--requirement`、等号参数的完整 argv 断言；多根同名副本不覆盖；本地 fixture 通过已安装 pip parser 实际解析嵌套相对 -r/-c（含后续层级），验证仍指向原文件且未递归排除；源缺失/写失败/pip 失败/成功/dry-run 的目录清理；无排除默认命令、degraded、P2 冻结 fixture 与 P3 解析不回归。测试禁止网络与真实依赖安装，不能只 mock pip 成功代替引用解析验证。

### 5.3 验证命令与手工验证

- 单元/回归：`python -m pytest tests/scripts/test_update_submodules.py -v`（A-115）。
- 手工验证（T3）：目标机 `python3 scripts/upgrade/update_submodules.py --only daily_stock_analysis --skip-restart` dry-run，确认 config 输出含 opt-in 的 systemd_service/health_check、无 install_exclude 时输出与 v2.1.0 格式一致（A-113/A-111 人工复核）。
- 回归范围：仅本测试文件 + `python -m py_compile scripts/upgrade/update_submodules.py`。

## 6. 风险、降级与回滚

| 风险 | 应对 | 降级/回滚 |
|---|---|---|
| 过滤误删依赖行 | SPEC §4.2 锚定语义 + A-102/103/104 逐例测试；detail 回显 excluded 清单 | 移除 yaml 中 install_exclude 即恢复全量安装 |
| 被排除包为运行必需 → health check 失败 | Phase 4 health_check 门禁兜底（P3 配置后生效） | 同上；服务可 `systemctl --user restart` 手动恢复 |
| yaml untracked 触发 dirty abort | §3.6 落盘策略 a/b，禁止 untracked | `--force-dirty` 仅应急 |
| P2 选行规则误选 | 三级回落保底（无更优行 = v2.1.0 行为）；仅影响诊断文本不影响分类 | git revert（见下） |
| 回归破坏既有行为 | A-113/A-115 强制回归 | git revert 单提交 |

**历史回滚方案**：初始 T2 的提交后回滚可用 `git revert <commit>`；P3 yaml 可删除该文件（或移除 `.git/info/exclude` 条目）。本轮仅交付未提交的受限修复，禁止 commit、revert、reset、stash、clean 和 P3 变更，不能执行该历史方案或清理共享树差异。

## 7. 交接给实现者

- 必须遵守：本轮仅脚本与现有测试 allowlist（§3.1）；SPEC §7 禁止事项；保持 `__version__=2.2.0` 和 Fix-1 偏移；不 commit、不修改 P3 或 c27720fa；fixture 冻结文本逐字使用；按 §3.4 最小修复与 §5.2 回归要求交付。
- 可自行判断：内部 helper 命名与文件内摆放位置；`_prefer_constraint_sample` 的探测正则实现（语义须过 A-109/110）；临时文件用 `TemporaryDirectory` 或 `NamedTemporaryFile+finally`。
- 混合 hit+miss 附加审计文本仅作为 SPEC §8 未定义项记录，本轮不扩展、不调整现有分支。
- 遇到以下情况退回 Principal：
  - 发现 `SubmoduleConfig` 存在本 DESIGN 未列出的第 3 个构造点；
  - 过滤语义无法在不动 5 阶段结构的前提下接入 `phase_install`；
  - P2 优先规则与分类 pattern 顺序产生耦合冲突；
  - 需要改动约束清单外文件（视为设计缺陷）。
