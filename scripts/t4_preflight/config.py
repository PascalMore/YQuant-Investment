"""T4 Preflight configuration constants.

DESIGN-03-014 §15.3 / SPEC-03-014 §14.

All values here are hardcoded; the CLI does not allow overriding them
at runtime (DESIGN §15.6.1 "Max Calls" hardcoding, §15.3.1
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

CANDIDATE_ENV_FILES: tuple[str, ...] = (
    "./.env",
    "~/.hermes/profiles/yquant/.env",
)

CANDIDATE_SECRET_KEYS: tuple[str, ...] = ("MONGO_URI",)

#: Allowed database for MongoDB preflight (SPEC §14.2 / DESIGN §15.5).
ALLOWED_DATABASE: str = "tradingagents"

#: Phase 3 business collections we explicitly check for (DESIGN §15.5.3).
P3_BUSINESS_COLLECTIONS: tuple[str, ...] = (
    "03_data_ud_market_sector_snapshot",
    "03_data_ud_stock_capital_flow",
    "03_data_ud_market_sentiment_snapshot",
)

#: Hard cap on the number of Mongo operations performed in preflight.
PREFLIGHT_MAX_OPERATIONS: int = 4  # parse URI + ping + list_collections + check P3

# ---------------------------------------------------------------------------
# AKShare call caps per capability (DESIGN §15.6.1 "Max Calls" table)
# ---------------------------------------------------------------------------

#: Max AKShare API calls per capability. Hardcoded; not overridable.
AKSHARE_MAX_CALLS: dict[str, int] = {
    "sector.snapshot": 1,
    "sector.ranking": 1,
    "flow.capital_flow_daily": 2,
    "flow.northbound_daily": 1,
    "sentiment.market_snapshot": 1,
    "sentiment.limit_up_pool": 1,
}

#: Default test targets for each smoke capability.
DEFAULT_TEST_TARGETS: dict[str, str] = {
    "sector.snapshot": "BK0489",
    "sector.ranking": "BK0489",
    "flow.capital_flow_daily": "600519",  # + 000001 = 2 calls
    "flow.northbound_daily": "600519",
    "sentiment.market_snapshot": "auto",
    "sentiment.limit_up_pool": "auto",
}

# ---------------------------------------------------------------------------
# Field mapping thresholds (DESIGN §15.6.2 / SPEC §14.4.4)
# ---------------------------------------------------------------------------

#: matched_ratio >= 0.90 → pass
MATCH_RATIO_PASS: float = 0.90

#: 0.70 <= matched_ratio < 0.90 → conditional_pass
MATCH_RATIO_CONDITIONAL: float = 0.70

#: matched_ratio < 0.70 → fail
#: (anything below the conditional floor is a fail)

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
# Exit codes (DESIGN §15.8)
# ---------------------------------------------------------------------------

EXIT_PASS: int = 0
EXIT_CONDITIONAL: int = 1
EXIT_FAIL: int = 2
EXIT_UNAUTHORIZED: int = 3
