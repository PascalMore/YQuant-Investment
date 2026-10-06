# SPEC-10-012：update_submodules install 排除与诊断优化

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Accepted |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-10-06 |
| 最后更新 | 2026-10-06 |
| 来源 RFC | docs/rfc/10_infra/RFC-10-012-update-submodules-install-exclusion-and-diagnostics.md (V1.1) |
| 版本号 | V1.1（t_13d22c5e，既有契约勘误） |
| 关联 Design | docs/design/10_infra/DESIGN-10-012-update-submodules-install-exclusion-and-diagnostics.md |
| 前版文档 | SPEC-10-008-update-submodules-script（V2.0，机制基线） |
| 目标模块 | 10_infra / git submodule 运维自动化 |
| 目标版本 | update_submodules.py v2.2.0 |
| 适配 Agent | YQuant-Developer-Engineer, YQuant-Test-Engineer |
| Full Flow | Quick Flow T1=t_c1e60718（T2=Implement, T3=Verify, T4=Closeout） |

## 1. 需求摘要

本 SPEC 将 RFC-10-012 的三项优化落为可执行契约：(1) opt-in `install_exclude` 包级排除——Phase 3 install 前过滤 requirements 中锚定该包的整行，成功后 audit 记录 degraded；(2) `classify_pip_failure` 的 sample 二次选择——分类与六类集合不变，仅在命中行集合内优先选择含包名+版本约束的诊断行；(3) 确认 `skills/research/daily_stock_analysis/.update_submodules.yaml` 走既有 merge_override 机制（health_check / systemd_service 字段零新机制）。所有行为均为 opt-in 或诊断增强，未配置时脚本行为与 v2.1.0 完全一致。

## 2. 范围

### 2.1 In Scope

- [ ] F-001~F-003：`install_exclude` 的 schema、过滤语义与 audit 语义（v2.2.0 新增）。
- [ ] F-004：`classify_pip_failure` sample 二次选择规则（分类判定不变）。
- [ ] F-005：daily_stock_analysis opt-in yaml 内容与 merge_override 机制确认。
- [ ] A-100 系列验收项与 UT-020+ 测试要求。

### 2.2 Out of Scope

- [ ] 5 阶段流水线结构、merge abort 逻辑、push 默认行为（禁改，RFC §3.2）。
- [ ] 失败分类六类集合与 pattern 顺序（missing_dependency / platform_incompatible / resolution_conflict / network_error / source_build_error / other）。
- [ ] requirements 行续行（反斜杠折行）语法。
- [ ] CLI 参数面（不新增参数）。
- [ ] 文档模板（docs/*-00-000-*.md）。

## 3. 功能规格

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| F-001 | `install_exclude` 声明与校验 | opt-in `.update_submodules.yaml` 中 `install_exclude: list[str]` | `SubmoduleConfig.install_exclude: tuple[str, ...]`（默认空 tuple） | 元素非字符串或整体非 list → warning 丢弃该字段，回落空 tuple；空 list 视同未声明 |
| F-002 | requirements 过滤精确语义 | `pip_install_cmd` 中 `-r`/`--requirement`（含等号形式）直接引用的根 requirements 文件 + `install_exclude` | 过滤根副本；命令保留 requirement 选项；返回去重保序的原始命中包名；嵌套相对引用保持原解析目标（§4.2） | 无 `-r` 引用 → warning 且排除 no-op；源缺失/副本写失败 → install fail；过滤后为空仍执行；已创建的临时目录在所有退出路径清理 |
| F-003 | degraded audit 语义 | pip 成功且被排除包集合非空 | PhaseResult.detail 首段为 `install (excluded: <pkgs>): OK (degraded)`，`<pkgs>` 为 requirements 中实际命中的包名逗号列表；阶段 status=pass | 命中集合为空（声明的包都不在 requirements）→ 普通 `pip install OK`，detail 另起行列出未命中的声明包 |
| F-004 | classify_pip_failure sample 二次选择 | pip stderr/stdout 全文 | `(classification, sample)` 不变签名 | 分类 pattern 首匹配规则不变；sample 在该分类命中的行集合内按 §4.3 规则选取；无更优行时回落首个命中行（v2.1.0 行为） |
| F-005 | daily_stock_analysis opt-in 配置 | `.update_submodules.yaml`（内容见 §4.4） | merge_override 后 `systemd_service="daily-stock-analysis"`、`health_check="curl -fsS --max-time 5 http://127.0.0.1:8888/health"` | yaml 破损/schema 非法 → warning 回落启发式（既有语义，RFC-10-008 §6.3/A-019） |

## 4. 数据与接口契约

### 4.1 数据实体

```python
@dataclass(frozen=True)
class SubmoduleConfig:
    ...
    install_exclude: tuple[str, ...] = ()   # v2.2.0 新增，默认空
```

### 4.2 包名规范化与匹配语义（F-002 核心）

- 匹配单位：requirements **行**。一行至多被一个排除包命中（首包名锚定）。
- 行首包名提取规则：跳过空行、`#` 注释行、以 `-` 开头的选项行（如 `-r`、`--index-url`）；其余行取行首到首个空白/`<>=!~;#[]` 之一的子串为包名，经 PEP 503 规范化（lower + `[-_.]+` → `-`）后与规范化后的 `install_exclude` 元素比对。
- 仅当规范化后相等才删整行；**禁止子串包含匹配**（排除 `bridge` 不得命中 `longbridge`）。
- 保留语义：注释行、未命中包的行（含行内注释与 environment marker）原样保留；选项行不参与包排除。唯一允许的选项行改写是为保持原解析目标，将过滤根副本中的相对 `-r`/`--requirement`、`-c`/`--constraint` 引用（含等号形式）重定位至相对于原根文件目录的绝对路径；选项种类与其余参数不变，原文件不写回。
- 排除范围仅限 pip 命令直接引用的根 requirements 文件；嵌套 requirements/constraints 仍交由 pip 读取原文件，后续相对引用仍按各原文件目录解析，不递归复制或排除嵌套包。多根副本不得因同名文件而互相覆盖。
- pip argv 的分离形式 `-r <path>`/`--requirement <path>` 保留选项，仅替换路径；等号形式 `--requirement=<path>`（以及既有解析支持的 `-r=<path>`）保留选项前缀，不得退化成裸路径；保留 Fix-1 的 pip 前缀索引偏移。
- 命中列表按根文件/行首次出现顺序，对提取出的原始包名去重；规范化仅用于匹配，不把原始命中名称改写成规范化名称。
- 规范化示例：`Long_Bridge`、`long-bridge`、`long.bridge` → `long-bridge`；`longbridge`、`LONGBRIDGE` → `longbridge`。两组不等价，不能互相命中。
- 声明的包均未命中任何根文件行：不报错，如实进入 F-003 的未命中清单。混合 hit+miss 的附加审计文本尚未定义，见 §8，不因本轮勘误新增要求。

### 4.3 classify_pip_failure sample 二次选择规则（F-004）

- 第一步（不变）：`_PIP_ERROR_PATTERNS` 依序首匹配确定 `classification`；取窗口（末 60 非空行）内该 pattern 命中的行集合。
- 第二步（新增）：在命中行集合内按优先级选 sample：
  1. 优先：同时含**包名形态 token**（`[A-Za-z0-9._-]+` 且后随版本约束运算符 `<,>,=,~,!` 或直接位于 `found for` 之后）与**版本约束**（如 `longbridge<5,>=4.0.5`）的行；多条命中取第一条。
  2. 次选：含 `Could not find a version that satisfies the requirement <pkg>` 形态的行。
  3. 回落：无 1/2 命中 → 首个命中行（v2.1.0 行为）。
- 覆盖案例（fixture 取自 2026-10-06 audit 实录）：stderr 同时含 `ERROR: Ignored the following yanked versions: 0.2.2, ...` 与 `No matching distribution found for longbridge<5,>=4.0.5` → 分类 `missing_dependency`，sample 必须为后者。

### 4.4 P3 opt-in 文件精确内容

```yaml
# skills/research/daily_stock_analysis/.update_submodules.yaml
schema_version: 1
systemd_service: daily-stock-analysis
health_check: "curl -fsS --max-time 5 http://127.0.0.1:8888/health"
```

- 机制确认：`systemd_service` 与 `health_check` 均为 RFC-10-008 §3.2/§3.3 既有 opt-in 字段，经 `validate_override` → `merge_override` 生效（update_submodules.py:573/627），**零新机制**。Phase 4 语义不变：restart → `_wait_for_active_state` → health_check shell 执行，非零 exit → abort push。
- 落盘策略与 dirty_worktree 规避见 DESIGN §3.6。

### 4.5 接口/函数

- 新增：无公开函数。内部 helper（命名可由实现者定，语义须符合 §4.2/§4.3）：requirements 行过滤、行首包名提取、sample 二次选择。
- 修改：`validate_override`、`merge_override`、`_replace_config` 透传 `install_exclude`；`phase_install` 消费之。
- 兼容性约束：`classify_pip_failure` 签名 `(str) -> tuple[str, str]` 不变；不配置时 dry-run 输出与 v2.1.0 逐字节一致。

### 4.6 兼容性与幂等性

- `install_exclude` 为纯声明侧配置，不落库、不修改 submodule 内任何文件；重复运行幂等。
- audit 日志格式仅新增 detail 文本，不改变 Markdown 结构（Summary 表与 Details 行格式不变）。

## 4.bis 持久化契约

无持久化需求（数据库/TTL/隐私分级均不涉及）。落盘物仅两类，均为既有机制：audit Markdown 日志（`--audit-dir`，L0）；P1 过滤根副本临时文件（`tempfile` 所选临时目录，可由 TMPDIR 指定；仅 requirements 保留行及必要引用重定位，无敏感字段）。创建后的临时目录在本次 `phase_install` 所有退出路径清理（§7），而非等进程退出。opt-in yaml 持久化于 submodule 仓库内，随仓库生命周期，L0。

## 5. 验收标准

| 编号 | 验收项 | 验证方式 |
|---|---|---|
| A-100 | `install_exclude` list[str] 合法声明 → config 字段为 tuple，merge 后生效 | 单元测试（tmp_path 写 yaml + merge_override） |
| A-101 | install_exclude 非 list 或元素非 str → warning 丢弃字段，config 为空 tuple | 单元测试 |
| A-102 | 排除 `longbridge` 命中 `longbridge>=4.0.5,<5; marker` 整行（含行内注释），保留相邻注释与其他包行；`-r`/`-c` 不参与排除，仅按 §4.2 必要重定位 | 单元测试逐行断言 + 本地 pip parser 实际解析嵌套引用，无网络/安装 |
| A-103 | 排除 `bridge` 不命中 `longbridge` 行（PEP 503 相等锚定，非子串） | 单元测试 |
| A-104 | `Long_Bridge` / `long-bridge` / `long.bridge` 规范化为 `long-bridge`；`longbridge` / `LONGBRIDGE` 规范化为 `longbridge`；组内等价、组间不命中 | 保留既有正确规范化代码/测试；分别断言等价与不等价 |
| A-105 | pip 成功且有命中 → detail=`install (excluded: longbridge): OK (degraded)`，status=pass | 单元测试（mock run_cmd exit 0） |
| A-106 | 声明包未命中 requirements → detail 为普通 OK + 未命中清单，无 degraded 字样 | 单元测试 |
| A-107 | pip_install_cmd 无 `-r` → warning，排除 no-op，audit 如实 | 单元测试 |
| A-108 | 源缺失/临时副本写失败 → install fail，不静默回退；目录创建后所有退出均清理 | 单元测试覆盖源缺失、写失败、pip 失败、成功、dry-run；严格捕获 argv 覆盖分离/等号形式及多根同名副本（§4.2） |
| A-109 | 2026-10-06 真实 stderr 文本：分类 `missing_dependency` 不变，sample 含 `longbridge` 且含版本约束 token，不含 `yanked` 行 | 回归测试（fixture 内嵌真实文本） |
| A-110 | 六类分类 pattern 全量回归：既有分类测试（如有）结果不变；sample 回落路径（仅 yanked 行）输出首个命中行 | 单元测试 |
| A-111 | P3 yaml 三字段经 merge_override 后值精确等于 §4.4；config_source=`heuristic+opt-in` | 单元测试 |
| A-112 | 破损 yaml → 回落启发式（health_check=None, systemd 来自启发式） | 单元测试（既有 A-019 语义复核） |
| A-113 | 未配置 install_exclude 的 submodule：dry-run 输出与 v2.1.0 一致（新增字段不打印） | 回归测试（既有 UT-016 复跑） |
| A-114 | `--help`/版本号显示 v2.2.0；CLI 参数面与 v2.1.0 相同 | CLI 测试 |
| A-115 | 既有 UT-001~UT-019 全量通过 | pytest 全量 |

## 6. 测试要求

- 单元测试：UT-020 起，覆盖 A-100~A-114；文件 `tests/scripts/test_update_submodules.py`，沿用既有 fixture 风格（`_make_worktree`、mock `run_cmd`）。用例名与 fixture 设计见 DESIGN §5。
- 集成测试：不做（脚本面向本机 systemd/venv，既有测试体系即为 mock 级）。
- 回归测试：A-109/A-110/A-113/A-115 为强制回归；A-109 fixture 文本必须逐字取自 2026-10-06 audit（设计冻结文本见 DESIGN §5.2）。
- 不可自动化验证项：真实 WSL 环境下 daily-stock-analysis 的 health check 端点可达性（127.0.0.1:8888 依赖服务在跑）；由 T3 Verify 在目标机做一次 `--dry-run` 冒烟并人工确认 detail。

## 7. 实现约束

- 禁止事项：改 5 阶段结构 / merge abort / push 默认 / 六类分类集合与顺序 / 文档模板；过滤用子串匹配；临时文件失败时静默降级为不过滤执行。
- 依赖限制：不新增第三方依赖（保持标准库 + PyYAML optional）。
- 性能/安全/风控约束：过滤副本经 `tempfile` 创建；清理作用域必须覆盖目录创建后的全部操作/return/异常，包括源缺失、写失败、pip 失败、成功及 dry-run。`run_cmd` 保持 `shell=False`；health_check 命令串来自仓库内 opt-in 文件，与既有 opt-in 信任边界一致，不扩大。
- 本轮授权（t_13d22c5e → t_c4fc6a2a → t_743f1d89 → t_7e416326）只闭合旧 Closeout t_b5d45087 的三缺陷和文档错误；不是新设计阶段。代码 allowlist 仅 `scripts/upgrade/update_submodules.py`、`tests/scripts/test_update_submodules.py`。不改子模块/生产配置，不执行 commit/push/reset/stash/clean、真实依赖安装、升级 apply、服务重启、数据库或调度变更；保留 c27720fa 与其他共享树差异。P3 历史方案（§4.4 / DESIGN §3.6）不是本轮执行授权。

## 8. 开放问题

- [ ] requirements 反斜杠折行（line continuation）内的包是否参与过滤：本版不处理（每日_stock_analysis requirements 无折行）；如未来命中，需扩展行拼接逻辑。
- [ ] `install_exclude` 未命中声明包是否应升级为 warning：当前仅 audit 如实列出（A-106），避免每日噪音。
- [ ] 混合 hit+miss 的未命中附加审计文本：旧 Closeout 记录现实现只输出 degraded 命中列表；本轮仅记录该未定义项，不新增契约、不扩大修复范围。
