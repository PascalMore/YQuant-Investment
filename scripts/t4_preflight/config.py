"""T4 Preflight configuration constants.

DESIGN-03-014 §15.3 / SPEC-03-014 §14.

P3-B S1 R3 P0 re-implementation (RFC-03-014 V0.33 §R3 /
SPEC-03-014 V0.33 §R3 / DESIGN-03-014 V0.37 §R3.9):

* The P3-B G-CF-LIVE freeze narrows the PR-3 smoke to a single
  capability (``flow.capital_flow_daily``) and a single symbol
  (``600519`` / ``sh``). The previous PR-3 multi-symbol
  (``600519/sh`` + ``000001/sz``) and the dedicated northbound
  slot are removed.
* ``flow.northbound_daily`` is ``intentionally-unavailable`` per
  Pascal C (RFC §13.4.5.2 / DESIGN §R3.1). The capability persists
  in the registry (DataRouter unchanged) but no AKShare call is
  ever made for it via the runner. Registering it here would
  silently re-introduce the ``stock_hsgt_individual_em``
  holding-history endpoint, which is forbidden.
* The unique field-mapping threshold is
  ``MATCH_RATIO_CONDITIONAL=0.70`` — per RFC V0.33 §R3.3 /
  SPEC V0.33 §R3.3 / §R3.10 item6 / DESIGN §R3.3. The
  ``<70% fail-stop / ≥70% 才可通过`` rule is the only public
  threshold input. The legacy PR-3 ``≥90% pass`` ladder is
  retained as frozen historical text in DESIGN §15.6.2 but is
  not exposed here for the G-CF-LIVE path.
* P0 contract scope (DESIGN §R3.9.4): no Gate runner / DDL /
  Mongo / apply / credential branches are introduced here. The
  G-CF-LIVE / G-CF-DDL / G-CF-CANARY / G-CF-POST command surface
  is described in DESIGN §R3.3-§R3.6 and is **not** implemented
  in P0; each Gate stays under Pascal's per-gate manual
  authorisation.

All values here are hardcoded; the CLI does not allow overriding
them at runtime (DESIGN §15.6.1 "Max Calls" hardcoding, §15.3.1
"no --force / --skip-stop" / "no secret/URI arguments").
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Connection / safety defaults
# ---------------------------------------------------------------------------

#: Per-call timeout for MongoDB preflight ping / AKShare fetch.
DEFAULT_TIMEOUT_SECONDS: int = 3

#: AKShare inter-call min interval (DESIGN §15.6.1 / SPEC §14.4.1 "≥1s/call").
MIN_INTERVAL_SECONDS: float = 1.0

#: Default report output directory (DESIGN §15.3.1).
DEFAULT_OUTPUT_DIR: str = "./docs/rfc/03_data/smoke_reports/"

# ---------------------------------------------------------------------------
# Candidate secret sources (SPEC §14.3 / DESIGN §15.4.2)
# ---------------------------------------------------------------------------

#: Path to the canonical Phase-2 skills env file. Used by PR-1
#: ``LegacyConfigResolver`` and the PR-0 secret audit (SPEC §14.3 /
#: DESIGN §15.4.2). Never falls back to ``./.env`` or any Hermes
#: profile ``.env`` — those candidate paths were removed by T1
#: (RFC V0.6 / SPEC V0.5).
SKILLS_ENV_PATH: str = "skills/.env"

#: PR-0 secret-audit candidate env files. Single canonical source:
#: ``skills/.env``. The project-root ``./.env`` and the Hermes
#: profile ``~/.hermes/profiles/yquant/.env`` were marked superseded
#: by T1 and are NOT candidates here (DESIGN §15.4.2 removed-candidates
#: table).
CANDIDATE_ENV_FILES: tuple[str, ...] = (
    SKILLS_ENV_PATH,
)

#: PR-0 secret-audit candidate keys (DESIGN V0.12 §15.4.2).
#: Phase 3 uses the five-component ``MONGODB_*`` keys exclusively.
#: The legacy ``MONGO_URI`` / ``MONGODB_URI`` are explicitly
#: superseded (RFC/SPEC) and are NOT candidates here.
CANDIDATE_SECRET_KEYS: tuple[str, ...] = (
    "MONGODB_HOST",
    "MONGODB_PORT",
    "MONGODB_USERNAME",
    "MONGODB_PASSWORD",
    "MONGODB_DATABASE",
)

#: PR-1 required keys for ``LegacyConfigResolver`` (DESIGN V0.12
#: §15.5.2). All five must be present + non-empty + MONGODB_PORT
#: must parse as int + MONGODB_DATABASE must equal ``tradingagents``.
#: No fallback, no alias.
MONGODB_FIVE_KEYS: tuple[str, ...] = (
    "MONGODB_HOST",
    "MONGODB_PORT",
    "MONGODB_USERNAME",
    "MONGODB_PASSWORD",
    "MONGODB_DATABASE",
)

#: Allowed database value for MongoDB preflight
#: (SPEC §14.2 / DESIGN §15.3 / §15.5.2). ``MONGODB_DATABASE`` must
#: equal this exact string, otherwise the preflight refuses to
#: instantiate any client (NOT_AUTHORIZED → exit 3).
ALLOWED_DATABASE: str = "tradingagents"
ALLOWED_DATABASE_VALUE: str = "tradingagents"

#: Phase 3 business collections we explicitly check for (DESIGN §15.5.3).
P3_BUSINESS_COLLECTIONS: tuple[str, ...] = (
    "03_data_ud_market_sector_snapshot",
    "03_data_ud_stock_capital_flow",
    "03_data_ud_market_sentiment_snapshot",
)

#: Hard cap on the number of Mongo operations performed in preflight.
PREFLIGHT_MAX_OPERATIONS: int = 4  # parse URI + ping + list_collections + check P3

# ---------------------------------------------------------------------------
# AKShare call caps per capability (DESIGN V0.37 §R3.3 / §R3.9 allowlist #3)
# ---------------------------------------------------------------------------

#: Max AKShare API calls per capability. Hardcoded; not overridable
#: (DESIGN V0.37 §R3.3 / §R3.9 allowlist #3).
#:
#: P3-B S1 G-CF-LIVE: ``flow.capital_flow_daily`` is the ONLY real
#: capability this runner exercises. The hard cap is 3 calls so a
#: single ``600519/sh`` × up-to-3 completed-trading-days fan-out
#: stays within the budget. The previous PR-3 budget had two
#: symbols (``600519/sh`` + ``000001/sz``) and a separate
#: northbound slot; both are removed because the P3-B single-symbol
#: / northbound-prohibited contract supersedes the PR-3 multi-symbol
#: shape (R3.9 allowlist #1 — clamp to single 600519/sh).
#:
#: ``flow.northbound_daily`` is intentionally absent:
#: ``flow.northbound_daily`` is ``intentionally-unavailable`` per
#: Pascal C (RFC §13.4.5.2 / DESIGN §R3.1). The capability persists
#: in the registry (DataRouter unchanged) but no AKShare call is
#: ever made for it via the runner. Registering it here would
#: silently re-introduce the ``stock_hsgt_individual_em``
#: holding-history endpoint, which is forbidden.
AKSHARE_MAX_CALLS: dict[str, int] = {
    "sector.snapshot": 1,
    "sector.ranking": 1,
    "flow.capital_flow_daily": 3,
    "sentiment.market_snapshot": 1,
    "sentiment.limit_up_pool": 1,
}

#: Default test targets for each smoke capability
#: (DESIGN V0.37 §R3.3 / §R3.9 allowlist #3).
#:
#: P3-B S1 G-CF-LIVE: single fixed symbol ``600519`` (沪市),
#: paired with ``market='sh'``. The PR-3 second symbol
#: (``000001``/sz) and the dedicated northbound slot are removed
#: per the P3-B freeze.
#:
#: Northbound target is intentionally absent — see
#: :data:`AKSHARE_MAX_CALLS` docstring.
DEFAULT_TEST_TARGETS: dict[str, str] = {
    "sector.snapshot": "BK0489",
    "sector.ranking": "BK0489",
    "flow.capital_flow_daily": "600519",
    "sentiment.market_snapshot": "auto",
    "sentiment.limit_up_pool": "auto",
}

#: Fixed dry-run date range used for the preflight metadata block
#: (DESIGN §15.3.2 / §15.10.2). Smoke dry-runs emit a non-empty range
#: so reviewers can confirm the test envelope without invoking any
#: real call.
DRY_RUN_DATE_RANGE: tuple[str, str] = ("2026-07-20", "2026-07-22")

# ---------------------------------------------------------------------------
# Field mapping thresholds (DESIGN V0.37 §R3.3 / SPEC V0.33 §R3.3 + §R3.10 item6)
# ---------------------------------------------------------------------------

#: matched_ratio >= 0.70 → 通过（唯一公开阈值输入）。
#:
#: P3-B S1 G-CF-LIVE 字段映射停止条件：``<70% fail-stop / ≥70% 才可通过``
#: （RFC-03-014 V0.33 §R3.3 L1573 / SPEC-03-014 V0.33 §R3.3 L2385 /
#: §R3.9 item1 L2448 / §R3.10 item6 L2466；DESIGN V0.37 §R3.3 /
#: §R3.9.3）。这是一个**唯一公开阈值输入**——不允许引入任何替代阈值
#: 替换 0.70（SPEC §R3.10 item6 冻结）。§15.6.2 历史分级
#: （≥90% pass / 70-90% conditional / <70% fail）保留为旧 PR 工具链
#: 历史文本，G-CF-LIVE 场景以本节为准。
MATCH_RATIO_CONDITIONAL: float = 0.70

# ---------------------------------------------------------------------------
# Sanitizer thresholds (DESIGN §15.7.2)
# ---------------------------------------------------------------------------

#: Strings longer than this are truncated to "<prefix>... (N chars truncated)".
SANITIZER_MAX_STRING_LENGTH: int = 500

#: Lists larger than this are truncated to first N entries + "(and M more)".
SANITIZER_MAX_LIST_LENGTH: int = 100

#: Sample row cap on smoke reports.
SAMPLE_ROW_LIMIT: int = 5

# ---------------------------------------------------------------------------
# Reporter ledger (DESIGN §15.14.3)
# ---------------------------------------------------------------------------
#: Reporter ledger fields (DESIGN §15.14.3 最小实现 / T3 X2 scope).
#: Six-field accounting surface every smoke report MUST emit on
#: dry-run and live-read paths. The four ``*_count`` fields are
#: fixed at ``0`` in the current no-retry / no-fallback /
#: zero-write scope (DESIGN §15.5.3 / §15.9). ``worktree_changed``
#: and ``empty_semantics`` were removed by the 2026-07-26 T3
#: Implementer following Pascal's X2 minimum-scope direction —
#: worktree probing stays opt-in (see
#: ``scripts.t4_preflight.reporter.detect_worktree_changed``) and
#: empty-semantics classification is rendered through verdict+memo
#: rather than as a dedicated field.
LEDGER_FIELDS: tuple[str, ...] = (
    "provider_attempts",
    "actual_calls",
    "retry_count",
    "fallback_count",
    "mongo_calls",
    "write_operations",
)

# ---------------------------------------------------------------------------
# Exit codes (DESIGN §15.8)
# ---------------------------------------------------------------------------

EXIT_PASS: int = 0
EXIT_CONDITIONAL: int = 1
EXIT_FAIL: int = 2
EXIT_UNAUTHORIZED: int = 3
