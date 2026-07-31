"""03-016 sector.ranking production rollout Gate tools (offline-testable).

Package marker for the 03-016 rollout tool family (DESIGN-03-016 V0.4
§3.1.1). The four Gate CLIs live as sibling modules:

* ``gate1_smoke`` — read-only smoke + authoritative SW L1 universe check
* ``gate2_ddl``   — collection + unique index DDL (idempotent)
* ``gate3_backfill`` — real TA-CN historical backfill (day-atomic)
* ``gate4_activate`` — production read-path activation (binding switch)

Shared components: :mod:`common` (ConnLoader / BudgetReader /
ReportWriter / CompletedSessionPolicy) and :mod:`prod_repository`
(ProdRankingWriter / ProdRankingReader / BindingState).

本数据为辅助研究数据，不构成交易指令或投资建议。
"""

from __future__ import annotations

__all__ = [
    "common",
    "prod_repository",
    "gate1_smoke",
    "gate2_ddl",
    "gate3_backfill",
    "gate4_activate",
]
