"""Offline tests for the 03-016 rollout shared components (common.py).

DESIGN-03-016 V0.4 §3.3 / SPEC-03-016 V0.2 §3.1. All tests run against
mongomock / pure functions with explicit injection — **zero environment
reads and zero real I/O** (CL-5).

本数据为辅助研究数据，不构成交易指令或投资建议。
"""

from __future__ import annotations

import json

import mongomock
import pytest

from scripts.unified_data.sector_ranking_rollout.common import (
    EXIT_CONN,
    EXIT_OK,
    EXIT_PARAM,
    EXIT_STOP,
    EXIT_VERIFY,
    BudgetReader,
    BudgetViolation,
    CompletedSessionPolicy,
    ConnLoader,
    FakeTradeCalendar,
    PolicyUnavailableError,
    REPORT_DIR_DEFAULT,
    SessionStatus,
    TradeCalendar,
    log_jsonl,
    redact,
    resolve_report_dir,
    scan_secrets,
    write_report,
)

# 显式测试环境（CL-5：测试零环境读取，全部显式注入）。
TEST_ENV = {
    "MONGODB_HOST": "mongo-host-1",
    "MONGODB_PORT": "27017",
    "MONGODB_USERNAME": "svc-user",
    "MONGODB_PASSWORD": "svc-pass-123",
    "MONGODB_DATABASE": "tradingagents",
}


# ---------------------------------------------------------------------------
# 退出码常量（SPEC G0-C-004）
# ---------------------------------------------------------------------------


class TestExitCodes:
    def test_exit_code_constants_match_spec(self):
        assert EXIT_OK == 0
        assert EXIT_PARAM == 1
        assert EXIT_STOP == 2
        assert EXIT_CONN == 3
        assert EXIT_VERIFY == 4


# ---------------------------------------------------------------------------
# ConnLoader（SPEC CL-1 ~ CL-6 / DESIGN §3.3.2）
# ---------------------------------------------------------------------------


class TestConnLoader:
    def test_missing_any_required_key_reports_only_key_names(self):
        env = {k: v for k, v in TEST_ENV.items() if k != "MONGODB_PASSWORD"}
        loader = ConnLoader(env=env, client_factory=mongomock.MongoClient)
        missing = loader.describe_missing()
        assert missing == ["MONGODB_PASSWORD"]
        # 值不得出现在任何输出中
        assert "svc-pass-123" not in str(missing)

    def test_missing_port_has_no_default(self):
        env = {k: v for k, v in TEST_ENV.items() if k != "MONGODB_PORT"}
        loader = ConnLoader(env=env, client_factory=mongomock.MongoClient)
        assert loader.describe_missing() == ["MONGODB_PORT"]

    def test_all_keys_present_means_no_missing(self):
        loader = ConnLoader(env=TEST_ENV, client_factory=mongomock.MongoClient)
        assert loader.describe_missing() == []

    def test_load_db_constructs_client_component_style(self):
        captured: dict = {}

        def factory(**kwargs):
            captured.update(kwargs)
            return mongomock.MongoClient()

        loader = ConnLoader(env=TEST_ENV, client_factory=factory)
        db = loader.load_db()
        assert db.name == "tradingagents"
        assert captured["host"] == "mongo-host-1"
        assert captured["port"] == 27017
        assert captured["username"] == "svc-user"
        assert captured["password"] == "svc-pass-123"
        assert captured["authSource"] == "tradingagents"
        assert captured["serverSelectionTimeoutMS"] == 10000
        assert captured["connectTimeoutMS"] == 10000

    def test_fingerprint_contains_only_structural_fields(self):
        loader = ConnLoader(env=TEST_ENV, client_factory=mongomock.MongoClient)
        fp = loader.fingerprint()
        assert fp["source"] == "MONGODB_*"
        assert fp["keys_present"] == [
            "MONGODB_HOST",
            "MONGODB_PORT",
            "MONGODB_USERNAME",
            "MONGODB_PASSWORD",
            "MONGODB_DATABASE",
        ]
        assert fp["auth_configured"] is True
        # 不得含 username 可逆/可识别信息（CL-6）
        assert "svc-user" not in json.dumps(fp)

    def test_secret_entries_never_include_values_in_plain_output(self):
        loader = ConnLoader(env=TEST_ENV, client_factory=mongomock.MongoClient)
        entries = loader.secret_entries()
        kinds = {kind for kind, _ in entries}
        assert "password_value" in kinds
        values = [v for _, v in entries]
        assert "svc-pass-123" in values
        # 序列化后（report 上下文）任何值都不应裸出现——由 redact 处理
        dumped = json.dumps(entries)
        assert "svc-pass-123" in dumped  # 仅测试内部可见；redact 负责掩码


# ---------------------------------------------------------------------------
# BudgetReader（SPEC G1-B-001 ~ G1-B-007 / DESIGN §3.3.3）
# ---------------------------------------------------------------------------


def _budget_db():
    return mongomock.MongoClient().get_database("test_budget")


class TestBudgetReaderFilterEnforcement:
    def test_empty_filter_raises_budget_violation(self):
        reader = BudgetReader(_budget_db())
        with pytest.raises(BudgetViolation):
            reader.find("index_daily_quotes", {})

    def test_non_whitelist_only_filter_raises_budget_violation(self):
        reader = BudgetReader(_budget_db())
        with pytest.raises(BudgetViolation):
            reader.find("index_daily_quotes", {"foo": 1})

    def test_whitelist_sector_code_filter_allowed(self):
        reader = BudgetReader(_budget_db())
        assert reader.find("index_daily_quotes", {"sector_code": "801010"}) == []

    def test_whitelist_trade_date_range_filter_allowed(self):
        reader = BudgetReader(_budget_db())
        assert (
            reader.find(
                "index_daily_quotes",
                {"trade_date": {"$gte": "2026-07-01", "$lte": "2026-07-31"}},
            )
            == []
        )

    def test_whitelist_market_filter_allowed(self):
        reader = BudgetReader(_budget_db())
        assert reader.find("index_basic_info", {"market": "CN"}) == []

    def test_count_requires_filter(self):
        reader = BudgetReader(_budget_db())
        with pytest.raises(BudgetViolation):
            reader.count("index_daily_quotes", {})

    def test_distinct_requires_filter(self):
        reader = BudgetReader(_budget_db())
        with pytest.raises(BudgetViolation):
            reader.distinct("index_daily_quotes", "trade_date", {})

    def test_aggregate_empty_pipeline_raises(self):
        reader = BudgetReader(_budget_db())
        with pytest.raises(BudgetViolation):
            reader.aggregate("index_daily_quotes", [])

    def test_aggregate_first_stage_not_match_raises(self):
        reader = BudgetReader(_budget_db())
        with pytest.raises(BudgetViolation):
            reader.aggregate(
                "index_daily_quotes",
                [{"$group": {"_id": "$trade_date"}}],
            )

    def test_aggregate_match_without_whitelist_field_raises(self):
        reader = BudgetReader(_budget_db())
        with pytest.raises(BudgetViolation):
            reader.aggregate(
                "index_daily_quotes",
                [{"$match": {"foo": 1}}, {"$group": {"_id": "$trade_date"}}],
            )

    def test_aggregate_match_with_whitelist_field_allowed(self):
        reader = BudgetReader(_budget_db())
        assert (
            reader.aggregate(
                "index_daily_quotes",
                [
                    {"$match": {"sector_code": {"$in": ["801010"]}}},
                    {"$group": {"_id": "$trade_date"}},
                ],
            )
            == []
        )

    def test_find_limit_above_budget_raises(self):
        reader = BudgetReader(_budget_db())
        with pytest.raises(BudgetViolation):
            reader.find("index_daily_quotes", {"sector_code": "801010"}, limit=1001)

    def test_find_limit_at_budget_allowed(self):
        reader = BudgetReader(_budget_db())
        assert (
            reader.find("index_daily_quotes", {"sector_code": "801010"}, limit=1000)
            == []
        )

    def test_stats_records_query_kinds(self):
        db = _budget_db()
        db["index_daily_quotes"].insert_one(
            {"sector_code": "801010", "trade_date": "20260713"}
        )
        reader = BudgetReader(db)
        reader.find("index_daily_quotes", {"sector_code": "801010"})
        reader.count("index_daily_quotes", {"sector_code": "801010"})
        stats = reader.stats()
        assert len(stats) >= 2
        by_kind = {s["kind"]: s for s in stats}
        assert by_kind["find"]["count"] == 1
        assert by_kind["find"]["rows"] == 1
        assert by_kind["count"]["count"] == 1
        assert by_kind["count"]["rows"] == 1
        assert all("ms" in s for s in stats)

    def test_cumulative_rows_over_budget_raises_budget_violation(self):
        # G1-B-006（记录上限）：Gate-1 累计命中 > 上限 → BudgetViolation
        db = _budget_db()
        for i in range(12):
            db["index_daily_quotes"].insert_one(
                {"sector_code": "801010", "trade_date": f"2026{i:02d}01"}
            )
        reader = BudgetReader(db, max_rows=10)
        with pytest.raises(BudgetViolation):
            reader.find("index_daily_quotes", {"sector_code": "801010"})

    def test_cumulative_rows_within_budget_allowed(self):
        db = _budget_db()
        for i in range(3):
            db["index_daily_quotes"].insert_one(
                {"sector_code": "801010", "trade_date": f"2026{i:02d}01"}
            )
        reader = BudgetReader(db, max_rows=10)
        rows = reader.find("index_daily_quotes", {"sector_code": "801010"})
        assert len(rows) == 3
        stats = reader.stats()
        assert sum(s["rows"] for s in stats) == 3


# ---------------------------------------------------------------------------
# redact / scan_secrets（SPEC G0-C-005 / DESIGN §3.3.4）
# ---------------------------------------------------------------------------


class TestRedactAndScanSecrets:
    def test_redact_masks_known_sensitive_values(self):
        text = "connecting as svc-user with svc-pass-123 to mongo-host-1"
        out = redact(
            text,
            secret_entries=[
                ("password_value", "svc-pass-123"),
                ("secret_value", "svc-user"),
                ("secret_value", "mongo-host-1"),
            ],
        )
        assert "svc-pass-123" not in out
        assert "svc-user" not in out
        assert "mongo-host-1" not in out
        assert "[REDACTED:password_value]" in out

    def test_scan_secrets_detects_uri_with_credentials(self):
        hits = scan_secrets("fallback mongodb://user:pass@host:27017/db")
        assert "uri_with_credentials" in hits

    def test_scan_secrets_detects_password_value(self):
        hits = scan_secrets(
            "wrote password svc-pass-123 into report",
            secret_entries=[("password_value", "svc-pass-123")],
        )
        assert "password_value" in hits

    def test_scan_secrets_detects_token_value(self):
        hits = scan_secrets(
            "token abc-123-token leaked",
            secret_entries=[("token_value", "abc-123-token")],
        )
        assert "token_value" in hits

    def test_scan_secrets_clean_text_returns_empty(self):
        hits = scan_secrets("all clean, no secrets here")
        assert hits == []

    def test_scan_secrets_ignores_short_values(self):
        hits = scan_secrets(
            "a", secret_entries=[("password_value", "ab")]
        )
        assert hits == []


# ---------------------------------------------------------------------------
# ReportWriter / resolve_report_dir / log_jsonl（SPEC G0-C-007/008/010）
# ---------------------------------------------------------------------------


class TestReportWriter:
    def test_resolve_report_dir_creates_directory(self, tmp_path):
        target = tmp_path / "rollout" / "sector-ranking"
        resolved = resolve_report_dir(str(target))
        assert target.is_dir()
        assert resolved == str(target)

    def test_resolve_report_dir_default_constant(self):
        assert REPORT_DIR_DEFAULT == "data/rollout/sector-ranking"

    def test_write_report_writes_json_md_and_archive(self, tmp_path):
        payload = {"tool": "gate1_smoke", "checks": {"G1-C-001": "PASS"}}
        write_report(str(tmp_path), "gate1", payload)
        canonical = tmp_path / "gate1-report.json"
        md = tmp_path / "gate1-report.md"
        assert canonical.exists()
        assert md.exists()
        loaded = json.loads(canonical.read_text())
        assert loaded["tool"] == "gate1_smoke"
        assert loaded["checks"] == {"G1-C-001": "PASS"}
        # 归档副本（G0-C-010：不得覆盖历史 report）
        archives = sorted(tmp_path.glob("gate1-report-*.json"))
        assert len(archives) == 1
        assert json.loads(archives[0].read_text())["tool"] == "gate1_smoke"

    def test_log_jsonl_appends_redacted_records(self, tmp_path):
        log_jsonl(
            str(tmp_path),
            "gate1",
            {"action": "query", "secret": "svc-pass-123"},
            secret_entries=[("password_value", "svc-pass-123")],
        )
        log_dir = tmp_path / "logs"
        logs = list(log_dir.glob("gate1-*.log"))
        assert len(logs) == 1
        line = json.loads(logs[0].read_text())
        assert line["action"] == "query"
        assert "svc-pass-123" not in logs[0].read_text()
        assert "timestamp" in line


# ---------------------------------------------------------------------------
# CompletedSessionPolicy（SPEC G4-P-001~010 / DESIGN §3.3.5）
# ---------------------------------------------------------------------------


class TestCompletedSessionPolicy:
    def test_future_date_raises_value_error(self):
        calendar = FakeTradeCalendar({"2026-08-01"})
        policy = CompletedSessionPolicy(
            calendar, now_fn=lambda: _utc(2026, 8, 1, 0, 0, 0)
        )
        with pytest.raises(ValueError, match="ERR_FUTURE_DATE"):
            policy.classify("2026-08-02")

    def test_future_date_becomes_past_when_clock_advances(self):
        calendar = FakeTradeCalendar({"2026-08-01"})
        policy = CompletedSessionPolicy(
            calendar, now_fn=lambda: _utc(2026, 8, 3, 0, 0, 0)
        )
        # 2026-08-02 在 clock 前进后变为历史日；非交易日 → PAST_NON_TRADING_DAY
        assert policy.classify("2026-08-02") == SessionStatus.PAST_NON_TRADING_DAY

    def test_today_unclosed_raises_value_error(self):
        # 2026-08-01 为交易日；04:00 UTC = 12:00 CST < 15:00 → TODAY_UNCLOSED
        calendar = FakeTradeCalendar({"2026-08-01"})
        policy = CompletedSessionPolicy(
            calendar, now_fn=lambda: _utc(2026, 8, 1, 4, 0, 0)
        )
        with pytest.raises(ValueError, match="ERR_TODAY_UNCLOSED"):
            policy.classify("2026-08-01")

    def test_today_closed_after_cutoff(self):
        # 07:30 UTC = 15:30 CST >= 15:00 → TODAY_CLOSED，不抛错
        calendar = FakeTradeCalendar({"2026-08-01"})
        policy = CompletedSessionPolicy(
            calendar, now_fn=lambda: _utc(2026, 8, 1, 7, 30, 0)
        )
        assert policy.classify("2026-08-01") == SessionStatus.TODAY_CLOSED

    def test_today_exactly_at_cutoff_is_closed(self):
        # 07:00 UTC = 15:00 CST，15:00 整视为已收盘（G4-P-003）
        calendar = FakeTradeCalendar({"2026-08-01"})
        policy = CompletedSessionPolicy(
            calendar, now_fn=lambda: _utc(2026, 8, 1, 7, 0, 0)
        )
        assert policy.classify("2026-08-01") == SessionStatus.TODAY_CLOSED

    def test_today_non_trading_day_is_closed(self):
        # 2026-08-02 为周日非交易日；即使 04:00 UTC 也未收盘，仍 TODAY_CLOSED
        calendar = FakeTradeCalendar(set())
        policy = CompletedSessionPolicy(
            calendar, now_fn=lambda: _utc(2026, 8, 2, 4, 0, 0)
        )
        assert policy.classify("2026-08-02") == SessionStatus.TODAY_CLOSED

    def test_past_trading_day_no_error(self):
        calendar = FakeTradeCalendar({"2026-07-30", "2026-08-01"})
        policy = CompletedSessionPolicy(
            calendar, now_fn=lambda: _utc(2026, 8, 1, 7, 30, 0)
        )
        assert policy.classify("2026-07-30") == SessionStatus.PAST_TRADING_DAY

    def test_past_non_trading_day_no_error(self):
        calendar = FakeTradeCalendar({"2026-08-01"})
        policy = CompletedSessionPolicy(
            calendar, now_fn=lambda: _utc(2026, 8, 3, 7, 30, 0)
        )
        assert policy.classify("2026-08-01") == SessionStatus.PAST_TRADING_DAY
        assert policy.classify("2026-08-02") == SessionStatus.PAST_NON_TRADING_DAY

    def test_invalid_trade_date_format_raises(self):
        calendar = FakeTradeCalendar(set())
        policy = CompletedSessionPolicy(
            calendar, now_fn=lambda: _utc(2026, 8, 1, 7, 30, 0)
        )
        with pytest.raises(ValueError):
            policy.classify("2026-13-45")

    def test_calendar_none_fail_closed(self):
        with pytest.raises(PolicyUnavailableError):
            CompletedSessionPolicy(None)


def _utc(year, month, day, hour, minute, second):
    from datetime import datetime, timezone

    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
