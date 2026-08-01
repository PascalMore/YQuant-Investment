"""03-017 quote metadata governance runner (offline-testable; DESIGN-03-017 V0.1).

Package marker for the 03-017 ``tradingagents.index_daily_quotes`` SW
historical quote metadata governance tool family (RFC-03-017 / SPEC-03-017 /
DESIGN-03-017).  One CLI with four modes (``census`` / ``dry-run`` /
``apply`` / ``verify``) lives in :mod:`govern_quote_metadata`; shared
components live in :mod:`common`.

* ``common`` — exit codes, :class:`ConnLoader`, ReportWriter / JSONL logger /
  :class:`CheckpointStore`, :func:`redact` / :func:`scan_secrets`.
* ``govern_quote_metadata`` — the single four-mode CLI plus
  ``CandidateSelector`` / ``CensusEngine`` / ``MutationPlanner`` /
  ``QuoteMetadataWriter`` / ``Applier`` / ``Verifier``.

本数据为辅助研究数据，不构成交易指令或投资建议。
"""

from __future__ import annotations

__all__ = ["common", "govern_quote_metadata"]
