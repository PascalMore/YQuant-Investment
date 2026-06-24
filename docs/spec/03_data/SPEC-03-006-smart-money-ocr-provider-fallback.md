# SPEC-03-006: Smart Money OCR Provider Fallback（MiniMax → Z.AI/GLM）

## 元数据

| 项 | 值 |
|---|---|
| 状态 | 草稿（Draft） |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-06-25 |
| 最后更新 | 2026-06-25 |
| 来源 RFC | RFC-03-006 |
| 目标模块 | data-pipeline（OCR Provider 层） |
| 适配 Agent | YQuant-Developer-Engineer, YQuant-Test-Engineer |
| 关联 RFC | RFC-03-003、RFC-03-004、RFC-03-005 |
| 关联 SPEC | SPEC-03-004、SPEC-03-005 |

## 1. 需求摘要

本 SPEC 将 RFC-03-006 中描述的"主备 OCR provider 抽象层"落到具体接口签名、数据契约、错误分类、配置项与测试矩阵。核心交付物：

1. 抽象 `VisionProvider` 接口与 `ProviderResult` 数据类；
2. 新增 `MiniMaxVisionProvider`（封装现有 `mmx vision describe` 调用）与 `ZAIVisionProvider`（封装 Z.AI MCP "General Image Analysis tool" 调用），均实现同一接口；
3. 新增 `VisionProviderRouter`，按可配置 provider 顺序尝试，主失败后切到备 provider，并记录每次尝试的 provider、错误摘要、耗时；
4. 重构 `MiniMaxImageExtractor`，内部委托给 Router，对外保持 `BaseExtractor.extract` 接口不变，下游 Transform / Validate / Loader / Review Gate / Batch Closeout 零改动；
5. 复用现有 `review_pending/` 目录，但 `pending.csv` 增加 `provider` 列，`pending.json` 在 `provider_status` 字段记录实际生效 provider。

## 2. 范围

### 2.1 In Scope

- [ ] `VisionProvider` 抽象接口与 `ProviderResult` 数据类（Python 类型签名）。
- [ ] provider 注册表（`dict[str, type[VisionProvider]]`）与 `register_provider()` / `get_provider()` 函数。
- [ ] `MiniMaxVisionProvider` 实现：复用现有 `mmx vision describe` 调用与 3 次重试逻辑，复用 `VISION_PROMPT`。
- [ ] `ZAIVisionProvider` 实现：复用 `VISION_PROMPT`，调用 Z.AI MCP "General Image Analysis tool"，通过 Hermes MCP 客户端完成；含 `extract_json()` 鲁棒解析（处理 markdown 包裹、字段别名）。
- [ ] `VisionProviderRouter` 实现：按可配置 provider 顺序尝试，主失败切备；保留每次 attempt 详情。
- [ ] 重构 `MiniMaxImageExtractor`：内部委托 Router，对外签名不变。
- [ ] `_classify_failure(retryable, error_kind)` 错误关键字分类函数。
- [ ] provider 可用性启动检查（`mmx` CLI 在 PATH、`Z_AI_API_KEY` 已注入）。
- [ ] 调试 JSON 兼容现有命名（`pic_*_vision_raw.json` / `pic_*_vision_error.json`），扩展 `provider_status` 字段。
- [ ] `pending.csv` 增加 `provider` 列；`pending.json` 增加 `provider_status` 字段。
- [ ] 单元测试覆盖：主成功、主失败备成功、主备皆失败、quota 关键字立即切换、字段别名映射、pending.csv 写入 provider 列。
- [ ] config.yaml 新增 `ocr_providers` 段，默认 `[minimax, zai]`，含注释说明不暴露给普通用户。
- [ ] 文档同步：`skills/data/data-pipeline/SKILL.md` 增补 provider fallback 段。

### 2.2 Out of Scope

- [ ] 不在本次更换 `VISION_PROMPT` 模板内容。
- [ ] 不在本次修改 Transform / Validate / Loader / Review Gate / Batch Closeout 任何下游代码。
- [ ] 不在本次引入第三个 provider（Qwen-VL、Doubao 等）或本地 OCR 模型。
- [ ] 不在本次修改 `run_message_pipeline.py`（消息路径不走 OCR）。
- [ ] 不在本次实现"按 provider 自动路由"（按图片类型分流）；本阶段只做"主失败 → 备"的简单顺序策略。
- [ ] 不在本次实现 provider 性能基准测试或成本对比。
- [ ] 不在本次新增 MongoDB 集合、不修改 schema validator 对 OCR 输出的硬约束。
- [ ] 不在本次实现 Z.AI → MiniMax 反向 fallback（单向 fallback，决策 #6）。

## 3. 功能规格

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| F-001 | provider 注册 | `register_provider("zai", ZAIVisionProvider)` | 注册表写入内存 dict | 重复注册抛 `ValueError` |
| F-002 | provider 实例化 | `get_provider("minimax", output_dir=..., date_str=...)` | `MiniMaxVisionProvider` 实例 | 未知 provider 名抛 `KeyError` |
| F-003 | MiniMax provider OCR | `image_path: Path` | `ProviderResult(name="minimax", df=..., source_path=..., fallback_used=False, attempts=[...], errors=[])` | 3 次重试均失败抛 `ProviderError(retryable=False, kind=...)` |
| F-004 | Z.AI provider OCR | `image_path: Path` | `ProviderResult(name="zai", df=..., source_path=..., fallback_used=False, attempts=[...], errors=[])` | 1 次失败即抛 `ProviderError(retryable=False, kind=...)`（不做双向 fallback） |
| F-005 | Router 主备切换 | `Router([("minimax", factory1), ("zai", factory2)])` + `image_path` | 主成功直接返回；主失败后实例化备并尝试 | 主失败 → 备失败抛 `RuntimeError`，附双 provider 错误日志 |
| F-006 | 错误分类 | `stdout: str, stderr: str, returncode: int \| None` | `FailureKind` 枚举 + `retryable: bool` | 未知错误默认 `retryable=False`，落入 fallback |
| F-007 | Z.AI 输出 JSON 提取 | Z.AI MCP 返回的原始文本 | `pd.DataFrame` | markdown 包裹、字段别名、嵌套 JSON 容错 |
| F-008 | provider 可用性检查 | 启动时 | 日志记录 `minimax: ok/fail, zai: ok/fail` | 不抛异常，仅记录 |
| F-009 | Extractor 委托 Router | `MiniMaxImageExtractor.extract(image_path)` | `list[dict[df, source_path, provider_status]]` | 对调用方零改动；`provider_status` 透传 |
| F-010 | pending.csv 增列 | pending 行 + 实际 provider | CSV 多一列 `provider`，值为 `minimax` 或 `zai` | 非 pending 行不写 |
| F-011 | pending.json 增字段 | pending 元数据 | JSON `provider_status` 字段含 name/fallback_used/attempts/errors | 与现有字段并列 |
| F-012 | 审计 debug JSON 扩展 | provider 失败时 | `pic_*_vision_error.json` 增加 `provider_status` 顶层字段 | 命名兼容旧逻辑 |

## 4. 数据与接口契约

### 4.1 类型与异常

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

import pandas as pd


class FailureKind(str, Enum):
    """Failure classification used by providers and Router."""
    QUOTA_EXCEEDED = "quota_exceeded"          # 429 / quota / rate limit
    TIMEOUT = "timeout"                        # subprocess.TimeoutExpired / 上游超时
    NETWORK = "network"                        # 5xx / connection refused
    CLI_NOT_FOUND = "cli_not_found"            # mmx 不在 PATH
    MCP_UNAVAILABLE = "mcp_unavailable"        # Z.AI MCP 连不上
    PARSE_ERROR = "parse_error"                # JSON 解析失败
    SCHEMA_MISMATCH = "schema_mismatch"        # 输出非预期 schema
    UNKNOWN = "unknown"                        # 兜底


@dataclass(frozen=True)
class FailureReason:
    """Classified failure with retry decision."""
    kind: FailureKind
    retryable: bool
    message: str                               # 人类可读、脱敏后


class ProviderError(RuntimeError):
    """Provider raised a classified failure that the Router may choose to handle."""

    def __init__(self, provider: str, failure: FailureReason):
        super().__init__(f"[{provider}] {failure.kind.value}: {failure.message}")
        self.provider = provider
        self.failure = failure


@dataclass
class AttemptRecord:
    """Record of a single provider invocation attempt."""
    provider: str                              # "minimax" 或 "zai"
    success: bool
    duration_ms: int
    error_kind: FailureKind | None = None
    error_message: str | None = None           # 脱敏后


@dataclass
class ProviderResult:
    """Standardised return value for every VisionProvider implementation."""
    df: pd.DataFrame
    source_path: str
    provider_status: dict[str, Any] = field(default_factory=lambda: {
        "name": "",                            # "minimax" or "zai"
        "fallback_used": False,
        "attempts": [],                        # list[AttemptRecord.to_dict()]
        "errors": [],                          # list[str]
    })

    def to_record(self) -> dict[str, Any]:
        """Serialize to the dict shape consumed by the existing pipeline."""
        return {
            "df": self.df,
            "source_path": self.source_path,
            "provider_status": self.provider_status,
        }
```

### 4.2 VisionProvider 抽象接口

```python
class VisionProvider(ABC):
    """Abstract OCR provider. Implementations MUST return ProviderResult or raise ProviderError."""

    name: str  # 类属性；"minimax" 或 "zai"

    @abstractmethod
    async def describe(self, image_path: Path) -> ProviderResult:
        """Run OCR on a single image and return a normalised ProviderResult.

        Contract:
            - MUST return ProviderResult on success with df populated.
            - MUST raise ProviderError (with classified FailureReason) on failure.
            - MUST NOT silently swallow errors.
            - MUST NOT do any cross-provider fallback (that is Router's job).
            - MUST NOT mutate the input file.
        """

    @abstractmethod
    async def health_check(self) -> bool:
        """Lightweight readiness check used at startup. Must not raise."""
```

### 4.3 Provider 注册表

```python
ProviderFactory = Callable[..., VisionProvider]

_REGISTRY: dict[str, type[VisionProvider]] = {}


def register_provider(name: str, cls: type[VisionProvider]) -> None:
    """Register a VisionProvider implementation under a stable string name.

    Raises:
        ValueError: if name is already registered (caller must explicitly
                    unregister first if intentional override is needed).
    """
    if name in _REGISTRY:
        raise ValueError(f"provider '{name}' already registered; unregister first to override")
    if not issubclass(cls, VisionProvider):
        raise TypeError(f"{cls} is not a VisionProvider subclass")
    _REGISTRY[name] = cls


def unregister_provider(name: str) -> None:
    """Remove a provider from the registry (used in tests / hot reload)."""


def get_provider(
    name: str,
    *,
    output_dir: Path | None = None,
    date_str: str | None = None,
    **kwargs: Any,
) -> VisionProvider:
    """Instantiate a registered provider by name.

    Args:
        name: Registered provider name (e.g. "minimax", "zai").
        output_dir: Debug output directory.
        date_str: Optional date context for the debug path.

    Raises:
        KeyError: if name is not registered.
    """
    if name not in _REGISTRY:
        raise KeyError(f"unknown provider '{name}'; registered={sorted(_REGISTRY)}")
    return _REGISTRY[name](output_dir=output_dir, date_str=date_str, **kwargs)


def list_providers() -> list[str]:
    """Return sorted list of registered provider names."""


# Module-level registration (executed on import of providers package).
def _bootstrap_registry() -> None:
    from .minimax_provider import MiniMaxVisionProvider
    from .zai_provider import ZAIVisionProvider
    register_provider("minimax", MiniMaxVisionProvider)
    register_provider("zai", ZAIVisionProvider)
```

设计依据：决策 #5「provider 用注册表（dict）模式」。避免在 Router 内部维护 `if name == "minimax": ... elif name == "zai": ...` 的硬编码，新增 provider 只需 `register_provider("qwen", QwenVisionProvider)`。

### 4.4 VisionProviderRouter 接口

```python
@dataclass
class RouterConfig:
    """Configuration loaded from config.yaml."""
    provider_order: list[str]                 # e.g. ["minimax", "zai"]
    primary_timeout_seconds: int = 120        # mmx subprocess timeout
    fallback_timeout_seconds: int = 90         # Z.AI MCP request timeout


class VisionProviderRouter:
    """Sequentially tries providers per RouterConfig.provider_order.

    On success: returns ProviderResult with provider_status.fallback_used=False.
    On primary failure: instantiates the fallback provider, retries once.
        - If fallback succeeds, returns ProviderResult with
          provider_status.fallback_used=True and attempts=[primary_failure, fallback_success].
        - If fallback fails, raises RuntimeError containing both providers'
          classified errors (mirrors existing fail-fast semantics).
    """

    def __init__(self, config: RouterConfig, *, factories: dict[str, ProviderFactory] | None = None):
        """
        Args:
            config: Loaded router configuration.
            factories: Optional override for provider factories (used by tests
                       to inject mocks). Defaults to the registered providers.
        """

    async def describe(self, image_path: Path) -> ProviderResult:
        """Run primary → fallback chain for one image.

        Raises:
            RuntimeError: when both providers fail. The message contains
                          both classified failures, joined by ' / '.
            FileNotFoundError: if image_path does not exist.
        """

    async def health_check_all(self) -> dict[str, bool]:
        """Run health_check on every registered provider. Never raises."""
```

**fallback 触发条件**（决策 #2 与 RFC-03-006 §5.3 落地）：

| 触发情形 | 主 provider 是否重试 | 是否切到 fallback |
|---|---|---|
| 网络/超时/5xx（transient） | 是，按现有 3 次指数退避 | 重试全部失败后切 |
| 配额耗尽（quota / 429） | 否，立即识别为不可重试 | 立即切 |
| CLI 启动失败（mmx 不在 PATH） | 否 | 立即切 |
| JSON 解析失败 | 否 | 立即切 |
| Z.AI 也失败 | — | 上抛 RuntimeError（决策 #6：不做双向 fallback） |

### 4.5 错误分类函数

```python
RETRYABLE_MARKERS = (
    "system error", "temporarily", "timeout", "timed out",
    "rate limit", "too many requests",
    "http 429", "http 500", "http 502", "http 503", "http 504",
    "connection reset", "connection refused",
)

QUOTA_MARKERS = (
    "quota exceeded", "insufficient quota", "rate limit",
    "too many requests", "http 429", "额度", "配额",
)

PARSE_MARKERS = (
    "json decode", "expected json array", "no valid json",
)


def classify_failure(
    *,
    stdout: str = "",
    stderr: str = "",
    returncode: int | None = None,
    exception: BaseException | None = None,
) -> FailureReason:
    """Return a classified FailureReason.

    Rules (evaluated in order):
        1. CLI not found (FileNotFoundError)  → CLI_NOT_FOUND, retryable=False
        2. TimeoutExpired                    → TIMEOUT,       retryable=True
        3. QUOTA_MARKERS 命中                  → QUOTA_EXCEEDED, retryable=False
        4. RETRYABLE_MARKERS 命中              → NETWORK,       retryable=True
        5. PARSE_MARKERS 命中                  → PARSE_ERROR,   retryable=False
        6. returncode != 0                    → UNKNOWN,       retryable=False
        7. fallback                           → UNKNOWN,       retryable=False
    """
```

### 4.6 Z.AI provider 输出解析（决策 #4）

```python
def extract_json(raw: str) -> str | None:
    """鲁棒提取 JSON，处理以下模式：
        - Markdown ```json ... ``` 包裹
        - Markdown ``` ... ``` 包裹（无语言标签）
        - 前后文夹杂 JSON 数组 [...] 或对象 {...}
        - 全角括号混入
        - 字段别名（见 _alias_mapping）
    """
    # 1. 优先匹配 ```json / ``` 代码块
    # 2. 否则匹配最外层 [...] 或 {...}
    # 3. 全部失败返回 None（由 Router 标记为 PARSE_ERROR）
```

`ZAIVisionProvider` 复用现有 `VISION_PROMPT` 字符串常量（从 `minimax_image_extractor.py` 提到 `providers/prompts.py` 共享）。`extract_json()` 内部完成 markdown 剥离后，调用 `json.loads()` 解析为 `list[dict]`，再走 `_normalize_columns()` / `_clean_data()` 收敛到与 MiniMax 一致的列名。

**字段别名映射**（决策 #4 — 处理 Z.AI 输出的列名差异）：

| Z.AI 可能输出 | 标准化为 |
|---|---|
| `assetName` / `asset_name` / `holding_name` | `资产名称` |
| `windCode` / `wind_code` | `Wind代码` |
| `ratio` / `positionRatio` | `持仓比例` |
| `marketValue` / `value` | `市值(本币)` |
| `date` / `asOfDate` | `截止日期` |

映射规则**只在 Z.AI provider 内部**应用（与现有 `_normalize_columns` 共用一张映射表）；Router 不感知列名差异。

### 4.7 统一 schema 契约（透传至 pipeline result）

```python
# record dict 与现有 MiniMaxImageExtractor 完全兼容
record = {
    "df": pd.DataFrame,
    "source_path": str,
    "provider_status": {
        "name": "minimax" | "zai",
        "fallback_used": bool,
        "attempts": [
            {"provider": "minimax", "success": False, "duration_ms": 2400,
             "error_kind": "quota_exceeded", "error_message": "rate limit"},
            {"provider": "zai", "success": True, "duration_ms": 3400,
             "error_kind": None, "error_message": None},
        ],
        "errors": ["[minimax] quota_exceeded: rate limit"],
    },
}
```

下游消费者契约：

- `apply_asset_identity_review(df)`、`detect_format(df)`、所有 Transformer / Validator / Loader **只读 `record["df"]` 与 `record["source_path"]`**，与现有实现 0 改动兼容。
- `record["provider_status"]` 作为审计字段，向 batch summary 与 closeout 透传，**不参与入库决策**。

### 4.8 pending.csv / pending.json 新增字段（决策 #3）

```python
# pending.csv 追加列（与现有列并列，不重排）：
#   provider: "minimax" | "zai"
#
# 写入逻辑：
#   在 save_pending_review() 内部，新参数 provider_status: dict | None = None
#   - 若 provider_status 非空：pending_df["provider"] = provider_status["name"]
#   - 否则（理论上不会发生）：pending_df["provider"] = "unknown"
#
# pending.json payload 追加：
#   "provider_status": <来自 Router 的完整 provider_status dict>

# 兼容旧 pending.csv（无 provider 列）：
#   load_pending_confirmed.py 读 CSV 时，若无 provider 列则视为 "minimax"（默认），
#   并记录 warning。该兼容逻辑属于 load_pending_confirmed 的范畴，本 SPEC 仅约束
#   writer 端；reader 端的兼容策略留给 SPEC-03-004 的后续 patch 负责。
```

### 4.9 调试 JSON 兼容

- 现有 `pic_*_vision_raw.json` / `pic_*_vision_error.json` 命名保持不变。
- `pic_*_vision_error.json` 顶层 payload 增加可选字段 `provider_status`，由 Router 失败时写入。
- 现有 `_write_vision_debug` 工具保留，签名兼容；可接受 `provider_status: dict | None = None` 额外 kwarg。

## 5. 配置契约

### 5.1 config.yaml 新增字段

位置：`~/.hermes/profiles/yquant/config.yaml` 顶层，与 `mcp_servers` 平级。

```yaml
# Smart Money OCR Provider Fallback 配置（决策 #1、#6）
# ⚠️ 仅 Orchestrator / Developer 修改；普通用户不应触碰。
ocr_providers:
  # provider 优先级顺序；首项为主 provider，后续为 fallback 链。
  # 默认 ["minimax", "zai"]；保持单向 fallback（决策 #6）。
  order:
    - minimax
    - zai

  # 主 provider 子进程超时（秒）
  primary_timeout_seconds: 120
  # 备 provider 请求超时（秒）
  fallback_timeout_seconds: 90

  # 启动时是否做 health_check（默认 true）；失败仅日志，不阻塞
  health_check_on_start: true

  # 调试 JSON 是否携带 provider_status（默认 true）
  include_provider_status_in_debug: true
```

### 5.2 默认值与不暴露原则

| 字段 | 默认值 | 暴露给普通用户 | 说明 |
|---|---|---|---|
| `order` | `[minimax, zai]` | ❌ | 决策 #1：仅运维/Developer 改；普通用户通过 `--provider-override` CLI 参数临时切换的场景由后续 RFC 处理 |
| `primary_timeout_seconds` | `120` | ❌ | 与现有 `subprocess.run(timeout=120)` 保持一致 |
| `fallback_timeout_seconds` | `90` | ❌ | Z.AI MCP 经验值，留待压测 |
| `health_check_on_start` | `true` | ❌ | 关闭会降低可观测性，运维自行决定 |
| `include_provider_status_in_debug` | `true` | ❌ | 仅影响审计 JSON 大小，业务无影响 |

**不暴露原则的落地**：

- `run_unified_image_pipeline.py` 不新增 `--provider-order` / `--ocr-fallback` CLI 参数。
- batch_report / closeout 不在 `message_text` 中暴露 `provider_status` 全文，仅在 `mongodb_counts` 之外可选地打印一行「provider=<name> fallback=<bool>」用于人工追溯。
- `pending.json` 中的 `provider_status` 是合规审计需要的，但 `message_text` 不全文复制。

### 5.3 .env 约定

- `Z_AI_API_KEY` 已在 `~/.hermes/profiles/yquant/.env`；`ZAIVisionProvider` 通过 `os.environ["Z_AI_API_KEY"]` 读取。
- 禁止把 `Z_AI_API_KEY` 写入代码、pending CSV/JSON、debug JSON、stdout。
- 错误信息中如出现 key，必须脱敏为 `***`。

## 6. 行为契约（6 个开放问题 → 代码层映射）

| 决策 | SPEC 落地点 | 章节 |
|---|---|---|
| 1. fallback 优先级可配置，不暴露给普通用户 | `config.yaml` 的 `ocr_providers.order`；CLI 不暴露；运行时由 `RouterConfig` 读取 | 5.1, 5.2, 4.4 |
| 2. provider 层不做格式 sanity check | Z.AI provider 解析失败仅抛 `PARSE_ERROR`；`detect_format` 仍在 pipeline 层按列名判断 | 3 F-006, 4.5 |
| 3. fallback pending 同目录 + 加字段 | `save_pending_review(provider_status=...)` 接受新参数；CSV 追加 `provider` 列；JSON 追加 `provider_status` | 4.8 |
| 4. Z.AI 用同 prompt + robust 容错 | `VISION_PROMPT` 提到 `providers/prompts.py`；新增 `extract_json()` 处理 markdown / 别名；`_normalize_columns` / `_clean_data` 共用 | 4.6 |
| 5. provider 用注册表模式 | `_REGISTRY: dict[str, type[VisionProvider]]` + `register_provider()` / `get_provider()`；Router 不硬编码 if-elif | 4.3 |
| 6. 不做双向 fallback | Router 仅顺序遍历 `provider_order`；Z.AI 失败直接抛 `RuntimeError`；不重新尝试 minimax | 4.4, 3 F-005 |

## 7. 错误契约

### 7.1 Fallback 触发判定（与 RFC §5.3 对齐）

| 情形 | 重试 | fallback |
|---|---|---|
| 主超时 | 是（3 次指数退避） | 重试全失败后切 |
| 主 quota / 429 | 否 | 立即切 |
| 主 mmx 不在 PATH | 否 | 立即切 |
| 主 JSON 解析失败 | 否 | 立即切 |
| 主网络 5xx | 是 | 重试全失败后切 |
| 主 UNKNOWN（兜底） | 否 | 立即切 |
| 备失败 | — | 抛 RuntimeError（**不切回主**，决策 #6） |

### 7.2 终态失败语义

- **主失败 + 备成功**：`ProviderResult.provider_status.fallback_used=true`，返回 success 或 partial_success（取决于是否有 pending），pipeline 状态不变；batch closeout 仅在审计侧记录 provider。
- **主失败 + 备失败**：`VisionProviderRouter.describe` 抛 `RuntimeError`，message 含主备双 provider 的 `FailureReason.message`，用 ` / ` 连接。Pipeline 顶层 catch 后整图返回 `failed` 状态，与 RFC §5.5 一致。
- **provider 不可用（health_check fail）**：仅记录 warning，不阻止 pipeline 运行；运行时的失败由 fallback 链兜底。
- **pending 写入失败（磁盘满等）**：保留现有 `save_pending_review` 的 IO 错误语义，不在 provider fallback 范围处理。

### 7.3 错误信息脱敏

- stdout / stderr 在写入 `provider_status.errors` 与 debug JSON 前，必须经过 `_sanitize_error(text)` 处理：
  - 替换 `sk-...`、`AIza...`、`Bearer ...` 等 token 模式为 `***`；
  - 替换绝对路径中的 home 目录为 `<HOME>`；
  - 限制单条 message 长度 ≤ 500 字符。

## 8. 文件改动清单

### 8.1 新增

| 路径 | 用途 |
|---|---|
| `skills/data/data-pipeline/scripts/providers/__init__.py` | 包导出；触发 `_bootstrap_registry()` |
| `skills/data/data-pipeline/scripts/providers/base.py` | `VisionProvider` 抽象类、`ProviderResult`、`ProviderError`、`FailureKind`、`FailureReason`、`AttemptRecord` |
| `skills/data/data-pipeline/scripts/providers/registry.py` | `_REGISTRY`、`register_provider`、`unregister_provider`、`get_provider`、`list_providers` |
| `skills/data/data-pipeline/scripts/providers/router.py` | `VisionProviderRouter`、`RouterConfig` |
| `skills/data/data-pipeline/scripts/providers/prompts.py` | `VISION_PROMPT` 常量（从 minimax_image_extractor 迁出） |
| `skills/data/data-pipeline/scripts/providers/extract_json.py` | `extract_json()` 鲁棒解析 + 字段别名映射 |
| `skills/data/data-pipeline/scripts/providers/minimax_provider.py` | `MiniMaxVisionProvider`（封装现有 mmx 调用与重试逻辑） |
| `skills/data/data-pipeline/scripts/providers/zai_provider.py` | `ZAIVisionProvider`（封装 Z.AI MCP 调用与 extract_json） |
| `skills/data/data-pipeline/scripts/providers/classify.py` | `classify_failure()`、`_sanitize_error()` |
| `skills/data/data-pipeline/scripts/providers/health_check.py` | `health_check_all()`、`check_minimax_cli()`、`check_zai_mcp()` |
| `skills/data/data-pipeline/scripts/tests/test_ocr_provider_fallback.py` | 单元测试（见第 9 节） |

### 8.2 修改

| 路径 | 改动 |
|---|---|
| `skills/data/data-pipeline/scripts/extractors/minimax_image_extractor.py` | 移除 `VISION_PROMPT` 常量（迁到 `providers/prompts.py`）；移除 `_run_vision_extraction` / `_is_retryable_failure` / `_write_vision_debug` / `_parse_vision_output` / `_unwrap_mmx_response` / `_extract_json` / `_normalize_columns` / `_clean_data` / `_parse_date` / `_parse_percentage` / `_parse_number`；`extract()` 改为构造 `VisionProviderRouter([minimax, zai])` 并委托；保留对外签名不变 |
| `skills/data/data-pipeline/scripts/run_unified_image_pipeline.py` | `extract` 调用返回新增 `provider_status` 字段透传至 `save_pending_review(provider_status=...)`；其余流程不变 |
| `skills/data/data-pipeline/scripts/run_image_pipeline.py` | 同上（如仍使用） |
| `skills/data/data-pipeline/scripts/run_trade_image_pipeline.py` | 同上（如仍使用） |
| `skills/data/data-pipeline/scripts/transformers/asset_identity_review.py` | `save_pending_review()` 新增 `provider_status: dict \| None = None` kwarg；写入 CSV 时追加 `provider` 列；写入 JSON 时追加 `provider_status` 字段；向后兼容（无 provider_status 时不写新列/字段） |
| `skills/data/data-pipeline/scripts/batch_report.py` | `summarize_batch_results` / `format_batch_summary` / `build_batch_closeout` 在 items[] 中允许携带 `provider_status` 字段（仅透传，不聚合） |
| `~/.hermes/profiles/yquant/config.yaml` | 新增 `ocr_providers` 段（见 5.1） |
| `skills/data/data-pipeline/SKILL.md` | 新增"OCR Provider Fallback"段落，引用本 SPEC |
| `docs/rfc/03_data/RFC-03-006-smart-money-ocr-provider-fallback.md` | 不修改 RFC 内容（约束）。SPEC 完成后，由 Principal 在 RFC 的 Changelog 增补一行"SPEC-03-006 已发布"即可 |

### 8.3 不改动（明确列出）

- `skills/data/data-pipeline/scripts/transformers/portfolio_excel_transformer.py`
- `skills/data/data-pipeline/scripts/transformers/trade_excel_transformer.py`
- `skills/data/data-pipeline/scripts/transformers/image_portfolio_normalizer.py`
- `skills/data/data-pipeline/scripts/transformers/trade_normalizer.py`
- `skills/data/data-pipeline/scripts/transformers/a_share_name_corrector.py`
- `skills/data/data-pipeline/scripts/validators/*.py`
- `skills/data/data-pipeline/scripts/loaders/mongodb_loader.py`
- `skills/data/data-pipeline/scripts/run_unified_message_pipeline.py`（消息路径不走 OCR）
- `skills/data/data-pipeline/scripts/run_message_pipeline.py`（同上）

## 9. 测试要求

### 9.1 单元测试矩阵（test_ocr_provider_fallback.py）

| 用例 | 描述 | Mock 策略 |
|---|---|---|
| UT-01 | MiniMax 成功路径 | mock `MiniMaxVisionProvider.describe` 返回正常 `ProviderResult`；断言 `result.provider_status.fallback_used=False`、`name="minimax"`、`attempts` 长度=1 |
| UT-02 | MiniMax quota 触发 fallback 到 Z.AI | mock minimax 抛 `ProviderError(provider="minimax", failure=QUOTA_EXCEEDED)`；mock zai 成功；断言 `fallback_used=True`、`attempts` 长度=2、errors 含 minimax 摘要 |
| UT-03 | MiniMax 超时 3 次后切 Z.AI | mock minimax 连续抛 3 次 `TIMEOUT`；mock zai 成功；断言 minimax 的 3 次 attempt 都被记录 |
| UT-04 | MiniMax 解析失败立即切 Z.AI（不重试） | mock minimax 抛 `PARSE_ERROR`；断言 minimax 只有 1 次 attempt（不重试） |
| UT-05 | 双 provider 都失败 → RuntimeError | mock minimax 与 zai 均抛 `ProviderError`；断言 RuntimeError 的 message 含双 provider 错误摘要 |
| UT-06 | Z.AI markdown 包裹 JSON 解析 | 给 `extract_json` 喂 ``` ```json [...] ``` ```；断言返回 DataFrame 行数正确 |
| UT-07 | Z.AI 字段别名映射 | 给 extract_json 喂 `assetName/windCode/ratio`；断言列被标准化为 `资产名称/Wind代码/持仓比例` |
| UT-08 | Z.AI 输出夹杂前后文 | 喂一段「以下是提取结果：[...] 请审核」；断言仍能提取 |
| UT-09 | register_provider 拒绝重复 | 注册同 name 两次；断言抛 `ValueError` |
| UT-10 | get_provider 未知 name | 查 "qwen"；断言抛 `KeyError` |
| UT-11 | Router 不做双向 fallback | mock minimax 失败 → zai 失败；断言 Router 抛 RuntimeError 后**未**再次尝试 minimax（attempts 总数=2） |
| UT-12 | health_check_all 不抛异常 | mock minimax health 抛异常；断言 health_check_all 返回 `{minimax: False, zai: True}` 而不向上抛 |
| UT-13 | classify_failure 各关键字命中 | 喂 quota/timeout/parse/network/cli_not_found 各一例；断言 kind 与 retryable 正确 |
| UT-14 | pending.csv 写入 provider 列 | mock `save_pending_review(provider_status={"name":"zai",...})`；断言 CSV 含 `provider` 列且值="zai" |
| UT-15 | pending.json 写入 provider_status 字段 | 同上；断言 JSON payload 含 `provider_status.name="zai"` |
| UT-16 | pending.csv 兼容旧调用（无 provider_status） | 调用 `save_pending_review(provider_status=None)`；断言 CSV **不**含 `provider` 列（向后兼容） |
| UT-17 | 错误信息脱敏 | 喂含 `sk-abc123` 的 stderr；断言 `provider_status.errors` 中 key 被替换为 `***` |
| UT-18 | debug JSON 扩展字段 | 模拟 Router 失败；断言 `pic_*_vision_error.json` 含 `provider_status` 顶层字段 |
| UT-19 | config.yaml order 覆盖默认 | 用临时 yaml `order: [zai, minimax]` 构造 RouterConfig；断言 Router 第一个尝试 zai |
| UT-20 | 主成功路径零开销 | mock minimax 成功；断言 Router **未实例化** zai provider（`zai.__init__` 调用次数=0） |

### 9.2 集成测试

- IT-01：dry-run 跑通 `run_unified_image_pipeline.py --dry-run --image fixture.png`，mock `MiniMaxVisionProvider` 与 `ZAIVisionProvider` 不实际调用 mmx/MCP；断言返回 dict 含 `provider_status` 字段且与 RFC §9.1 兼容。
- IT-02：人工构造一张 500x500 测试图片，run pipeline 走通 minimax 路径（mock minimax），断言 pending.csv / pending.json 落盘格式正确。

### 9.3 回归测试

- 现有 `test_load_pending_confirmed.py` 不修改即可通过（因为 pending.csv 向后兼容 — 无 provider_status 时不写新列）。
- 现有 `test_codec_pipeline.py` 不受影响（message pipeline 不走 OCR）。

### 9.4 不可自动化验证项

- Z.AI MCP 实际响应延迟与配额耗尽阈值：依赖真实 MCP 服务，需在生产环境观察。
- 两 provider 对同一张图的识别一致率：留作后续 RFC（RFC-03-006 §8 方案 B）。

## 10. 验收标准

| 编号 | 验收项 | 验证方式 |
|---|---|---|
| A-001 | 主 provider 正常时，pipeline 结果与 RFC-03-006 §9.1 一致 | UT-01 + 回归 |
| A-002 | 主 provider 因 quota/timeout/network/parse-error 失败时，备 provider 接管并产出可用 DataFrame | UT-02/03/04 |
| A-003 | 双 provider 失败时，pipeline 返回 `failed` 状态并保留双方错误日志 | UT-05 |
| A-004 | `provider_status.name/fallback_used/attempts/errors` 在 record dict 与 debug JSON 中可见 | UT-01/02/18 |
| A-005 | 现有所有测试在不动测试用例的前提下保持通过 | 回归 |
| A-006 | 主 provider 成功路径不增加可见延迟（UT-20 断言 zai 未实例化） | UT-20 |
| A-007 | `Z_AI_API_KEY` 不出现在 debug JSON / pending CSV/JSON / stdout | 代码审查 + UT-17 |
| A-008 | `pending.csv` 包含 `provider` 列；`pending.json` 包含 `provider_status` | UT-14/15 |
| A-009 | 任何 provider 调用失败都在日志与审计文件中留下痕迹 | 集成测试 |
| A-010 | 启动时 `health_check_all` 记录每个 provider 状态，不阻塞 | UT-12 |
| A-011 | 普通用户无法通过 CLI 修改 provider 顺序（不新增 `--provider-order` 参数） | 代码审查 |
| A-012 | config.yaml 的 `ocr_providers.order` 默认 `[minimax, zai]` | 单元测试 |

## 11. 实现约束

### 11.1 禁止事项

- 禁止在 provider 内部静默重试到无上限；MiniMax 最多 3 次（与现状一致），Z.AI 不重试（决策 #6）。
- 禁止把 `Z_AI_API_KEY` 写入代码、配置文件、debug JSON、pending CSV/JSON、stdout。
- 禁止把 fallback 行为从 provider 层搬到 pipeline 层（必须是 Router 内部事件）。
- 禁止在 provider 层做 `detect_format` 之类的格式判断（决策 #2）。
- 禁止反向 fallback（Z.AI → MiniMax，决策 #6）。
- 禁止暴露 `--provider-order` / `--ocr-fallback` CLI 参数给普通用户（决策 #1）。
- 禁止修改 Transform / Validate / Loader / Review Gate / Batch Closeout 的入参签名。

### 11.2 依赖限制

- 允许新增：`Hermes MCP 客户端`（用于 Z.AI provider，决策 #4 与 RFC §12 一致）。
- 允许新增：`pytest-asyncio`（如果现有测试未覆盖异步场景）。
- 不允许新增：除上述以外的第三方依赖。
- 共享代码：`VISION_PROMPT` / `_normalize_columns` / `_clean_data` 提到 `providers/prompts.py` 与 `providers/extract_json.py`，由 minimax 与 zai provider 共用。

### 11.3 性能/安全/风控约束

- 主 provider 成功路径零开销（UT-20 保证）。
- 备 provider 调用延迟预算：`fallback_timeout_seconds` 默认 90s；超时即抛 PARSE_ERROR / TIMEOUT，由上层决定。
- 错误信息必须脱敏（UT-17 保证）。
- pending CSV/JSON 不含密钥或数据库凭证（与 RFC §3.2 一致）。

## 12. 风险与未解决问题

### 12.1 风险

| 风险 | 概率 | 影响 | 应对 |
|---|---|---|---|
| Z.AI 输出 schema 与 MiniMax 差异大 | 中 | 高 | 共用 `_normalize_columns` / `_clean_data`；`extract_json` 字段别名映射；provider 出口处 schema 校验 |
| Z.AI MCP 占用主对话 token 预算 | 中 | 中 | Z.AI MCP 仅在 OCR 路径按需调用；provider 路由仅在 data-pipeline 进程内启用 |
| Z.AI 配额独立耗尽 | 低 | 中 | 双 provider 同时耗尽时回到现有失败语义；Router 内可接入"配额预算计数器"（留待后续 RFC） |
| fallback 路径产生的 pending 数据被人工误判为 MiniMax 误识 | 低 | 低 | pending.json 与 provider_status 中记录实际 provider；人工补录时显式提示 provider 来源 |
| 两个 provider 对同一图识别不一致 → 重复入库 | 低 | 高 | OCR 阶段不写库；写入由 Transform/Loader 单点控制；MongoDB unique key 兜底（已有） |
| 主备切换引入额外延迟（每图多一次 ~10s 调用） | 中 | 中 | 仅在主 provider 失败时切；正常路径无开销；可加超时预算 |
| mmx CLI 与 Z.AI MCP 安装/配置状态不一致 | 中 | 中 | 启动时 health_check；不让"静默缺失"成为隐式 bug；仅在两个 provider 都不可用时失败 |
| provider 注册表被第三方扩展污染 | 低 | 中 | `register_provider` 默认拒绝重名；测试中 unregister 必须显式调用 |

### 12.2 未解决问题（移交 Design 阶段）

- [ ] Z.AI MCP client 选型最终落地：Hermes MCP SDK vs stdio 子进程 vs HTTP。RFC §12 提到此为 SPEC 待决项；建议在 design 阶段先做 spike（`mmx` 与 `@z_ai/mcp-server` 已在 `~/.hermes/profiles/yquant/config.yaml` 注册，client 复用现成通道即可）。
- [ ] `VisionProviderRouter` 是否需要状态计数器（观察 fallback 频率）以及持久化位置。RFC §12 提到；本 SPEC 建议先用 stderr 日志 + batch summary 透传，不立即持久化。
- [ ] `minimax_image_extractor.py` 公开签名是否扩展 `**kwargs`（RFC §6.2 列为先询问项）。本 SPEC 默认保持 `BaseExtractor.extract` 不变；若 design 阶段发现需要扩展 `dry_run` / `provider_status` 透传，由 Developer 先确认再改。
- [ ] 后续 RFC：双向 fallback、按图片类型智能路由、provider 性能基准。