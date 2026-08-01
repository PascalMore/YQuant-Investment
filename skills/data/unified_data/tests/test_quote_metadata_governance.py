"""Offline tests for the 03-017 quote metadata governance runner.

DESIGN-03-017 V0.1 §5 / SPEC-03-017 §8。全部测试运行在 mongomock / tmp_path
之上，**零环境读取、零真实 I/O**（CL-5 同纪律）。覆盖：

* 共享组件：退出码 / ConnLoader（C17-012 CL-1~CL-6）/ redact / scan_secrets /
  CheckpointStore。
* 候选谓词（C17-101）与权威 universe（C17-102/103）。
* fail-closed 门禁（C17-201~207，串行顺序）。
* 合规分类（C17-301~304）与计数恒等式（V17-001/002）。
* dry-run 报告（R17-001~007）与预期 mutation 方程（V17-003）。
* ``QuoteMetadataWriter``（M17-001~007：namespace/字段白名单、无 upsert/
  replace/delete/insert/DDL）。
* apply（M17/B17：幂等、批次分界、stop-on-error、checkpoint 恢复）。
* verify（V17-004~006）。
* DESIGN §5.2 显式零写测试矩阵 **D1~D12**（auditable equivalent）。

关于 D9 的 auditable-equivalent 说明：DESIGN §3.6.2 apply 伪代码明确
``# 已合规 id 不发写（M17-005）``，因此第二次 apply 对已合规候选**不发任何
写**（matched==0, modified==0）；D9 矩阵原文 ``matched>0`` 与设计伪代码
（M17-005 跳过已合规）矛盾，本实现以设计伪代码为准，D9 断言改为
``modified==0`` + ``matched==0``（纯 no-op），并在分类恒等式上验证收敛。

本数据为辅助研究数据，不构成交易指令或投资建议。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import mongomock
import pytest
from pymongo import UpdateOne
from pymongo.errors import AutoReconnect, DuplicateKeyError

from scripts.unified_data.quote_metadata_governance import (
    govern_quote_metadata as gov,
)
from scripts.unified_data.quote_metadata_governance.common import (
    EXIT_CONN,
    EXIT_OK,
    EXIT_PARAM,
    EXIT_STOP,
    EXIT_VERIFY,
    CheckpointStore,
    ConnLoader,
    MissingConnectionKeyError,
    REPORT_DIR_DEFAULT,
    log_jsonl,
    redact,
    redact_payload,
    resolve_report_dir,
    scan_secrets,
    utc_now_iso,
    write_report,
)
from scripts.unified_data.quote_metadata_governance.govern_quote_metadata import (
    COLLECTION,
    InvalidUpdate,
    NamespaceViolation,
    PROTECTED_FIELDS,
    QuoteMetadataWriter,
    build_predicate,
    candidate_matches,
    census_to_report_dict,
    classify_candidate,
    derive_universe,
    name_state,
    normalize_l1_code,
    plan_mutation,
    run_census,
    version_state,
)
from skills.data.unified_data.tests.fixtures.quote_metadata_governance_fixtures import (
    ABSENT,
    MIXED_CLASSIFICATION,
    UNIVERSE_SI,
    make_checkpoint,
    make_code_family_fail_docs,
    make_data_source_fail_docs,
    make_db,
    make_market_fail_docs,
    make_mixed_quote_docs,
    make_observation_docs,
    make_period_fail_docs,
    make_quote_doc,
    make_suffix_fail_docs,
    make_sw_quote_docs,
    make_sw_universe,
)

# 显式测试环境（CL-5：测试零环境读取，全部显式注入）。
TEST_ENV = {
    "MONGODB_HOST": "mongo-host-1",
    "MONGODB_PORT": "27017",
    "MONGODB_USERNAME": "svc-user",
    "MONGODB_PASSWORD": "svc-pass-123",
    "MONGODB_DATABASE": "tradingagents",
}


def make_conn() -> ConnLoader:
    return ConnLoader(env=TEST_ENV, client_factory=mongomock.MongoClient)


def read_report(report_dir: str | Path) -> dict:
    path = Path(report_dir) / "quote-governance-report.json"
    assert path.exists(), f"report missing: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 共享组件
# ---------------------------------------------------------------------------


class TestExitCodes:
    def test_exit_code_constants_match_spec(self):
        assert EXIT_OK == 0
        assert EXIT_PARAM == 1
        assert EXIT_STOP == 2
        assert EXIT_CONN == 3
        assert EXIT_VERIFY == 4


class TestConnLoader:
    def test_missing_any_required_key_reports_only_key_names(self):
        env = {key: value for key, value in TEST_ENV.items() if key != "MONGODB_PASSWORD"}
        loader = ConnLoader(env=env, client_factory=mongomock.MongoClient)
        assert loader.describe_missing() == ["MONGODB_PASSWORD"]
        # 值不得出现在任何输出中
        assert "svc-pass-123" not in str(loader.describe_missing())

    def test_missing_port_has_no_default(self):
        env = {key: value for key, value in TEST_ENV.items() if key != "MONGODB_PORT"}
        loader = ConnLoader(env=env, client_factory=mongomock.MongoClient)
        assert loader.describe_missing() == ["MONGODB_PORT"]

    def test_load_db_constructs_client_component_style_no_uri(self):
        captured: dict = {}

        def factory(**kwargs):
            captured.update(kwargs)
            return mongomock.MongoClient()

        loader = ConnLoader(env=TEST_ENV, client_factory=factory)
        db = loader.load_db()
        assert db.name == "tradingagents"
        # 组件式五键 + 超时；不允许 URI / prefix / alias（CL-1）
        assert set(captured) == {
            "host",
            "port",
            "username",
            "password",
            "authSource",
            "serverSelectionTimeoutMS",
            "connectTimeoutMS",
        }
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
        # 不得含 username/连接值可逆信息（CL-6）
        assert "svc-user" not in json.dumps(fp)
        assert "mongo-host-1" not in json.dumps(fp)

    def test_load_db_usable_with_mongomock(self):
        loader = ConnLoader(env=TEST_ENV, client_factory=mongomock.MongoClient)
        db = loader.load_db()
        db["index_daily_quotes"].insert_one(make_quote_doc(_id="abc"))
        assert db["index_daily_quotes"].count_documents({}) == 1


class TestRedactScanSecrets:
    def test_redact_masks_known_values(self):
        text = "host=mongo-host-1 password=svc-pass-123"
        out = redact(text, secret_entries=ConnLoader(env=TEST_ENV).secret_entries())
        assert "svc-pass-123" not in out
        assert "mongo-host-1" not in out
        assert "[REDACTED:" in out

    def test_scan_secrets_detects_uri_with_credentials(self):
        hits = scan_secrets("use mongodb://user:pass@db.example:27017/admin please")
        assert hits == ["uri_with_credentials"]

    def test_scan_secrets_detects_known_values(self):
        hits = scan_secrets(
            "value svc-pass-123 leaked",
            secret_entries=ConnLoader(env=TEST_ENV).secret_entries(),
        )
        assert "password_value" in hits

    def test_scan_secrets_clean_text_is_empty(self):
        assert scan_secrets("no secrets here") == []

    def test_redact_payload_walks_nested(self):
        payload = {
            "nested": {"pw": "svc-pass-123", "ok": 1},
            "list": ["svc-user", "fine"],
        }
        out = redact_payload(
            payload, secret_entries=ConnLoader(env=TEST_ENV).secret_entries()
        )
        assert "svc-pass-123" not in json.dumps(out)
        assert "svc-user" not in json.dumps(out)
        assert out["nested"]["ok"] == 1
        assert out["list"][1] == "fine"


class TestReportHelpers:
    def test_utc_now_iso_format(self):
        ts = utc_now_iso()
        assert ts.endswith("Z")
        assert "T" in ts

    def test_resolve_report_dir_mkdir(self, tmp_path):
        target = tmp_path / "nested" / "dir"
        resolved = resolve_report_dir(str(target))
        assert Path(resolved).exists()
        assert Path(resolved).is_dir()

    def test_write_report_writes_canonical_archive_md(self, tmp_path):
        payload = {"tool": "quote-metadata-governance", "mode": "census", "stats": {}}
        write_report(str(tmp_path), payload)
        assert (tmp_path / "quote-governance-report.json").exists()
        archives = list(tmp_path.glob("quote-governance-report-*.json"))
        assert len(archives) == 1
        assert (tmp_path / "quote-governance-report.md").exists()
        assert "census" in (tmp_path / "quote-governance-report.md").read_text()

    def test_log_jsonl_appends_redacted(self, tmp_path):
        log_jsonl(
            str(tmp_path),
            {"action": "batch", "secret": "svc-pass-123"},
            secret_entries=ConnLoader(env=TEST_ENV).secret_entries(),
        )
        log_file = next((tmp_path / "logs").glob("quote-governance-*.log"))
        text = log_file.read_text()
        assert "svc-pass-123" not in text
        assert "[REDACTED:password_value]" in text


class TestCheckpointStore:
    def test_load_none_when_missing(self, tmp_path):
        store = CheckpointStore(str(tmp_path), "run-1")
        assert store.load() is None

    def test_save_and_load_last_line(self, tmp_path):
        store = CheckpointStore(str(tmp_path), "run-1")
        store.save({"batch_seq": 1, "batch_start_id": "a", "batch_end_id": "b"})
        store.save({"batch_seq": 2, "batch_start_id": "b", "batch_end_id": "c"})
        loaded = store.load()
        assert loaded is not None
        assert loaded["batch_seq"] == 2
        assert loaded["batch_end_id"] == "c"
        assert "ts_utc" in loaded

    def test_load_ignores_corrupt_lines(self, tmp_path):
        path = tmp_path / "quote-governance-checkpoint-run-1.jsonl"
        path.write_text("{bad json}\n{\"batch_seq\": 1}\n", encoding="utf-8")
        store = CheckpointStore(str(tmp_path), "run-1")
        loaded = store.load()
        assert loaded == {"batch_seq": 1}


# ---------------------------------------------------------------------------
# 谓词 / universe
# ---------------------------------------------------------------------------


class TestPredicate:
    def test_build_predicate_shape(self):
        assert build_predicate() == {
            "data_source": "akshare",
            "full_symbol": {"$regex": "\\.SI$"},
        }

    @pytest.mark.parametrize(
        ("doc", "expected"),
        [
            ({"data_source": "akshare", "full_symbol": "801010.SI"}, True),
            ({"data_source": "akshare", "full_symbol": "801010.SH"}, False),
            ({"data_source": "akshare", "full_symbol": "801010.SZ"}, False),
            ({"data_source": "akshare", "full_symbol": "801010"}, False),
            ({"data_source": "tushare", "full_symbol": "801010.SI"}, False),
            ({"data_source": "akshare"}, False),
            ({"full_symbol": "801010.SI"}, False),
        ],
    )
    def test_candidate_matches(self, doc, expected):
        assert candidate_matches(doc) is expected

    def test_mongo_filter_selects_only_candidates(self):
        docs = [
            {"_id": "1", "data_source": "akshare", "full_symbol": "801010.SI"},
            {"_id": "2", "data_source": "akshare", "full_symbol": "801010.SH"},
            {"_id": "3", "data_source": "tushare", "full_symbol": "801010.SI"},
            {"_id": "4", "data_source": "akshare", "full_symbol": "801010"},
        ]
        db = make_db(quote_docs=docs, universe_docs=[])
        matched = list(db["index_daily_quotes"].find(build_predicate()))
        assert [doc["_id"] for doc in matched] == ["1"]


class TestUniverse:
    def test_normalize_l1_code(self):
        assert normalize_l1_code("801010") == "801010.SI"
        assert normalize_l1_code("801010.SI") == "801010.SI"
        assert normalize_l1_code(" 801080.si ") == "801080.SI"
        assert normalize_l1_code("") == ".SI"  # 空 base 产物（调用方 discard）

    def test_derive_universe_with_and_without_suffix(self):
        db_a = make_db(universe_docs=make_sw_universe(with_suffix=True))
        db_b = make_db(universe_docs=make_sw_universe(with_suffix=False))
        assert derive_universe(db_a) == set(UNIVERSE_SI)
        assert derive_universe(db_b) == set(UNIVERSE_SI)

    def test_derive_universe_empty(self):
        db = make_db(quote_docs=[], universe_docs=[])
        assert derive_universe(db) == set()


# ---------------------------------------------------------------------------
# Census：门禁 / 分类
# ---------------------------------------------------------------------------


class TestGates:
    def test_mixed_fixture_passes_all_gates(self):
        db = make_db(quote_docs=make_mixed_quote_docs())
        census = run_census(db, build_predicate())
        assert census.stop_conditions_hit == []
        for gate_id in ("C17-201", "C17-202", "C17-203", "C17-204", "C17-205"):
            assert census.gates[gate_id]["pass"] is True, gate_id

    def test_market_gate_fail_stops_serial(self):
        db = make_db(quote_docs=make_market_fail_docs())
        census = run_census(db, build_predicate())
        assert census.stop_conditions_hit == ["C17-204"]
        assert census.gates["C17-204"]["pass"] is False
        # C17-207：205 在 204 失败后不得执行
        assert "C17-205" not in census.gates
        assert census.gates["C17-204"]["evidence"]["counts"]["HK"] == 1

    def test_code_family_gate_fail_reports_counterexamples(self):
        db = make_db(quote_docs=make_code_family_fail_docs())
        census = run_census(db, build_predicate())
        assert census.stop_conditions_hit == ["C17-203"]
        evidence = census.gates["C17-203"]["evidence"]
        assert evidence["counterexample_count"] == 1
        assert evidence["counterexamples"][0]["full_symbol"] == "999999.SI"
        assert evidence["counterexamples"][0]["trade_date_count"] >= 1

    def test_period_gate_fail(self):
        db = make_db(quote_docs=make_period_fail_docs())
        census = run_census(db, build_predicate())
        assert census.stop_conditions_hit == ["C17-205"]
        assert census.gates["C17-205"]["evidence"]["counts"]["weekly"] == 1

    def test_suffix_gate_direct(self):
        # C17-201 是对谓词的独立复算：候选选择本身已保证 .SI，直接测 gate 函数
        from scripts.unified_data.quote_metadata_governance.govern_quote_metadata import (
            _gate_suffix,
        )

        assert _gate_suffix([make_quote_doc(full_symbol="801010.SI")])["pass"] is True
        bad = _gate_suffix([make_quote_doc(full_symbol="801010.SH")])
        assert bad["pass"] is False
        assert bad["evidence"]["distinct_suffixes"] == ["<not .SI>"]

    def test_data_source_gate_direct(self):
        from scripts.unified_data.quote_metadata_governance.govern_quote_metadata import (
            _gate_data_source,
        )

        assert _gate_data_source([make_quote_doc()])["pass"] is True
        bad = _gate_data_source([make_quote_doc(data_source="tushare")])
        assert bad["pass"] is False

    def test_empty_universe_stops(self):
        db = make_db(quote_docs=make_mixed_quote_docs(), universe_docs=[])
        census = run_census(db, build_predicate())
        assert census.stop_conditions_hit == ["C17-103"]

    def test_observation_docs_counted_not_mutated(self):
        docs = make_mixed_quote_docs() + make_observation_docs()
        db = make_db(quote_docs=docs)
        census = run_census(db, build_predicate())
        assert census.observations == {"si_non_akshare": 1, "akshare_non_si": 1}
        # 观察项不计入候选
        assert census.total_candidates == len(make_mixed_quote_docs())


class TestClassification:
    def test_version_state_buckets(self):
        assert version_state({}) == "absent"
        assert version_state({"version": 1}) == "int==1"
        assert version_state({"version": 2}) == "int!=1"
        assert version_state({"version": 1.0}) == "float"
        assert version_state({"version": "1"}) == "str"
        assert version_state({"version": [1]}) == "other"
        # bool 是 int 子类，但 BSON bool ≠ int（C17-303）
        assert version_state({"version": True}) == "other"

    def test_name_state_buckets(self):
        assert name_state({}) == "absent"
        assert name_state({"name": "电子"}) == "str"
        assert name_state({"name": 1}) == "non-str"

    def test_classify_candidate(self):
        compliant = classify_candidate(make_quote_doc(version=1, name=ABSENT))
        assert compliant["already_compliant"] is True
        assert compliant["version_fix_needed"] is False
        assert compliant["name_present"] is False

        both = classify_candidate(
            make_quote_doc(version=ABSENT, name="食品饮料")
        )
        assert both["already_compliant"] is False
        assert both["version_fix_needed"] is True
        assert both["name_present"] is True
        assert both["both_needed"] is True

        version_ok_name_present = classify_candidate(
            make_quote_doc(version=1, name="食品饮料")
        )
        assert version_ok_name_present["already_compliant"] is False
        assert version_ok_name_present["version_fix_needed"] is False
        assert version_ok_name_present["name_present"] is True

    def test_mixed_classification_matches_expected(self):
        db = make_db(quote_docs=make_mixed_quote_docs())
        census = run_census(db, build_predicate())
        expected = dict(MIXED_CLASSIFICATION)
        for key, value in expected.items():
            assert census.classification[key] == value, key
        # V17-001 / V17-002 恒等式
        assert census.checks["v17_001"] is True
        assert census.checks["v17_002"] is True

    def test_version_ok_name_present_breaks_v17_001(self):
        # 生产 post-repair 不变式（version==1 且 name 存在）下 V17-001 如实报 False
        docs = [make_quote_doc(version=1, name="食品饮料", _id="edge1")]
        db = make_db(quote_docs=docs)
        census = run_census(db, build_predicate())
        assert census.checks["v17_001"] is False
        assert census.classification["version_ok_name_present"] == 1

    def test_candidate_ids_sorted_ascending(self):
        docs = make_mixed_quote_docs()
        db = make_db(quote_docs=docs)
        census = run_census(db, build_predicate())
        ids = census.candidate_ids
        assert ids == sorted(ids, key=str)
        assert ids[0] == "id000001"

    def test_empty_candidates_noop(self):
        db = make_db(quote_docs=[])
        census = run_census(db, build_predicate())
        assert census.nothing_to_do is True
        assert census.total_candidates == 0
        assert census.stop_conditions_hit == []
        assert census.checks["v17_001"] is True


# ---------------------------------------------------------------------------
# Dry-run 报告（R17-001 ~ R17-007 / V17-003）
# ---------------------------------------------------------------------------


class TestDryRunReport:
    def test_plan_mutation_expected_counts(self):
        db = make_db(quote_docs=make_mixed_quote_docs())
        census = run_census(db, build_predicate())
        report = plan_mutation(census)
        assert report["plan"] == {
            "expected_set_version_ops": 5,
            "expected_unset_name_ops": 3,
            "expected_update_docs": 5,
        }

    def test_report_fields_present(self, tmp_path):
        db = make_db(quote_docs=make_mixed_quote_docs())
        census = run_census(db, build_predicate())
        report = census_to_report_dict(
            census,
            mode="dry-run",
            run_id="r1",
            conn_fingerprint=make_conn().fingerprint(),
        )
        # R17-001
        assert report["run_id"] == "r1"
        assert report["mode"] == "dry-run"
        assert report["ts_utc"].endswith("Z")
        assert report["conn_source"] == "MONGODB_*"
        assert set(report["conn_fingerprint"]) == {
            "source",
            "keys_present",
            "auth_configured",
        }
        assert report["collection"] == "tradingagents.index_daily_quotes"
        assert report["predicate"] == build_predicate()
        # R17-002
        assert report["stats"]["total_candidates"] == 6
        assert report["stats"]["total_docs_scanned"] == 6
        # R17-003
        assert report["classification"]["already_compliant"] == 1
        assert report["classification"]["both_needed"] == 3
        # R17-004
        assert report["distributions"]["version_histogram"]["absent"] == 2
        assert report["distributions"]["version_histogram"]["int==1"] == 1
        assert report["distributions"]["version_histogram"]["float"] == 1
        assert report["distributions"]["name_histogram"]["str"] == 3
        assert report["distributions"]["protected_presence"]["full_symbol"] == 6
        assert report["distributions"]["protected_presence"]["close"] == 6
        # R17-006 / V17-003
        assert report["plan"]["expected_update_docs"] == 5
        assert report["checks"]["v17_003"] is True
        # R17-007
        assert report["gates"]["C17-201"]["pass"] is True

    def test_samples_bounded_redacted(self):
        db = make_db(quote_docs=make_mixed_quote_docs())
        census = run_census(db, build_predicate())
        report = census_to_report_dict(
            census,
            mode="dry-run",
            run_id="r1",
            conn_fingerprint={},
        )
        text = json.dumps(report, ensure_ascii=False)
        for category, entries in report["samples"].items():
            assert len(entries) <= 5
            for entry in entries:
                assert set(entry) == {
                    "id_prefix",
                    "full_symbol",
                    "trade_date",
                    "name_presence",
                    "version_summary",
                }
                assert len(entry["id_prefix"]) == 6
                assert entry["name_presence"] in ("present", "absent")
        # 不输出原始 name 值、完整 _id、凭据
        assert "食品饮料" not in text
        assert "电子" not in text
        assert "银行" not in text
        assert "id000001" not in text  # 完整 _id 不允许
        assert "svc-pass-123" not in text


# ---------------------------------------------------------------------------
# QuoteMetadataWriter（M17-001 ~ M17-007）
# ---------------------------------------------------------------------------


class TestQuoteMetadataWriter:
    def test_no_disallowed_apis(self):
        writer = QuoteMetadataWriter(make_db())
        for name in ("insert_one", "insert_many", "delete_one", "delete_many",
                     "replace_one", "create_index", "drop"):
            assert not hasattr(writer, name), name

    def test_namespace_violation(self):
        writer = QuoteMetadataWriter(make_db())
        with pytest.raises(NamespaceViolation):
            writer._assert_namespace("other_collection")

    def test_update_one_upsert_forbidden(self):
        writer = QuoteMetadataWriter(make_db())
        with pytest.raises(InvalidUpdate):
            writer.update_one({"_id": "x"}, {"$set": {"version": 1}}, upsert=True)

    def test_update_one_field_whitelist(self):
        writer = QuoteMetadataWriter(make_db())
        with pytest.raises(InvalidUpdate):
            writer.update_one({"_id": "x"}, {"$set": {"close": 1.0}})
        with pytest.raises(InvalidUpdate):
            writer.update_one({"_id": "x"}, {"$inc": {"version": 1}})
        with pytest.raises(InvalidUpdate):
            writer.update_one({"_id": "x"}, {"$unset": {"code": ""}})
        with pytest.raises(InvalidUpdate):
            writer.update_one({"_id": "x"}, {"$set": {"version": 2}})

    def test_update_one_valid_on_mongomock(self):
        db = make_db(quote_docs=[make_quote_doc(_id="a", version=ABSENT, name="x")])
        writer = QuoteMetadataWriter(db)
        writer.update_one({"_id": "a"}, {"$set": {"version": 1}, "$unset": {"name": ""}})
        doc = db["index_daily_quotes"].find_one({"_id": "a"})
        assert doc["version"] == 1
        assert "name" not in doc

    def test_bulk_write_rejects_non_updateone(self):
        from pymongo import ReplaceOne

        writer = QuoteMetadataWriter(make_db())
        with pytest.raises(InvalidUpdate):
            writer.bulk_write([ReplaceOne({"_id": "a"}, {"version": 1})])

    def test_bulk_write_rejects_upsert_operation(self):
        writer = QuoteMetadataWriter(make_db())
        op = UpdateOne({"_id": "a"}, {"$set": {"version": 1}}, upsert=True)
        with pytest.raises(InvalidUpdate):
            writer.bulk_write([op])

    def test_bulk_write_ordered_false_forwarded(self):
        captured: dict = {}

        class SpyCollection:
            def __init__(self, coll):
                self._coll = coll

            def bulk_write(self, operations, ordered=False):
                captured["ordered"] = ordered
                captured["ops"] = len(list(operations))
                return None

        class SpyDb:
            def __init__(self, coll):
                self._coll = coll

            def __getitem__(self, name):
                assert name == COLLECTION
                return self._coll

        db = make_db(quote_docs=[make_quote_doc(_id="a", version=ABSENT)])
        writer = QuoteMetadataWriter(db)
        writer._db = SpyDb(SpyCollection(db["index_daily_quotes"]))
        op = UpdateOne({"_id": "a"}, {"$set": {"version": 1}}, upsert=False)
        writer.bulk_write([op])
        assert captured["ordered"] is False


# ---------------------------------------------------------------------------
# Apply（M17 / B17）
# ---------------------------------------------------------------------------


class RecordingWriter(QuoteMetadataWriter):
    """记录 bulk_write 调用次数与 op 数量（测试幂等/跳过语义）。"""

    def __init__(self, db: Any) -> None:
        super().__init__(db)
        self.bulk_calls = 0
        self.ops_total = 0
        self.ordered_flags: list[bool] = []

    def bulk_write(self, operations, *, ordered=False):
        self.bulk_calls += 1
        self.ops_total += len(list(operations))
        self.ordered_flags.append(ordered)
        return super().bulk_write(operations, ordered=ordered)


class FlakyWriter(QuoteMetadataWriter):
    """按目标 _id 注入异常（D12 / stop-on-error）。"""

    def __init__(self, db: Any, fail_ids=(), exc: BaseException = AutoReconnect("boom")):
        super().__init__(db)
        self.fail_ids = set(fail_ids)
        self.exc = exc
        self.attempts = 0
        self.fail_calls = 0  # 仅统计触发异常的次数（重试次数可观测）
        self.failed = False

    def bulk_write(self, operations, *, ordered=False):
        self.attempts += 1
        ids = [op._filter["_id"] for op in operations]  # noqa: SLF001
        if any(cid in self.fail_ids for cid in ids):
            self.failed = True
            self.fail_calls += 1
            raise self.exc
        return super().bulk_write(operations, ordered=ordered)


def mixed_db():
    return make_db(quote_docs=make_mixed_quote_docs())


class TestApplyMutation:
    def _snapshot(self, db):
        return {
            doc["_id"]: {
                key: value for key, value in doc.items() if key != "_id"
            }
            for doc in db["index_daily_quotes"].find({})
        }

    def test_first_apply_only_touches_version_name(self, tmp_path):
        db = mixed_db()
        pre = self._snapshot(db)
        census = run_census(db, build_predicate())
        store = CheckpointStore(str(tmp_path), "r1")
        result = gov.apply_mutation(
            db,
            census.candidate_ids,
            500,
            store,
            census.mutation_plan,
        )
        assert result["cumulative_modified"] == 5
        assert result["cumulative_matched"] == 5
        for doc in db["index_daily_quotes"].find({}):
            cid = doc["_id"]
            if cid == "id000001":
                continue  # already compliant 未发写
            assert doc["version"] == 1
            assert "name" not in doc
            for key, value in pre[cid].items():
                if key in ("version", "name"):
                    continue
                assert doc.get(key) == value, (cid, key)

    def test_second_apply_is_pure_noop_skip_compliant(self, tmp_path):
        db = mixed_db()
        census = run_census(db, build_predicate())
        writer = RecordingWriter(db)
        store = CheckpointStore(str(tmp_path), "r1")
        first = gov.apply_mutation(
            db, census.candidate_ids, 500, store, census.mutation_plan, writer=writer
        )
        assert first["cumulative_modified"] == 5
        assert writer.ops_total == 5

        writer.ops_total = 0
        census2 = run_census(db, build_predicate())
        second = gov.apply_mutation(
            db, census2.candidate_ids, 500, store, census2.mutation_plan, writer=writer
        )
        # DESIGN §3.6.2：已合规 id 不发写（M17-005）→ 纯 no-op
        assert second["cumulative_modified"] == 0
        assert writer.ops_total == 0

    def test_batch_size_boundaries(self, tmp_path):
        db = mixed_db()
        census = run_census(db, build_predicate())
        for batch_size, expected_batches in ((1, 6), (2, 3), (500, 1), (1000, 1)):
            store = CheckpointStore(str(tmp_path), f"b{batch_size}")
            result = gov.apply_mutation(
                db, census.candidate_ids, batch_size, store, census.mutation_plan
            )
            assert result["total_batches"] == expected_batches, batch_size
            assert len(result["batches"]) == expected_batches, batch_size
            # checkpoint 每批一条，batch_seq 连续
            lines = [json.loads(line) for line in store.path.read_text().splitlines()]
            assert [rec["batch_seq"] for rec in lines] == list(range(1, expected_batches + 1))
            assert lines[0]["batch_start_id"] == "id000001"

    def test_stop_on_error_transient_retries_then_stop(self, tmp_path):
        db = mixed_db()
        census = run_census(db, build_predicate())
        # batch1 = id000001..id000004；batch2 = id000005..id000006（batch_size=4）
        fail_ids = {"id000005", "id000006"}
        writer = FlakyWriter(db, fail_ids=fail_ids, exc=AutoReconnect("injected"))
        store = CheckpointStore(str(tmp_path), "d12")
        result = gov.apply_mutation(
            db, census.candidate_ids, 4, store, census.mutation_plan, writer=writer
        )
        assert result["stop_conditions_hit"], "expected stop condition"
        assert "apply_batch_2" in result["stop_conditions_hit"][0]
        # 有界重试 ≤2：batch2 失败后额外重试 2 次（共 3 次失败调用）
        assert writer.fail_calls == 3
        # checkpoint 仅含 batch1
        lines = [json.loads(line) for line in store.path.read_text().splitlines()]
        assert [rec["batch_seq"] for rec in lines] == [1]
        assert lines[0]["batch_end_id"] == "id000004"
        # batch1 已生效，batch2 未动
        assert db["index_daily_quotes"].find_one({"_id": "id000004"})["version"] == 1
        doc6 = db["index_daily_quotes"].find_one({"_id": "id000006"})
        assert doc6.get("version") is None  # missing_version 未被写入

    def test_stop_on_error_permanent_no_retry(self, tmp_path):
        db = mixed_db()
        census = run_census(db, build_predicate())
        writer = FlakyWriter(
            db, fail_ids={"id000005"}, exc=DuplicateKeyError("dup")
        )
        store = CheckpointStore(str(tmp_path), "perm")
        result = gov.apply_mutation(
            db, census.candidate_ids, 4, store, census.mutation_plan, writer=writer
        )
        assert result["stop_conditions_hit"]
        assert writer.fail_calls == 1  # 永久错误不重试（B17-005）

    def test_resume_from_checkpoint(self, tmp_path):
        db = mixed_db()
        census = run_census(db, build_predicate())
        store = CheckpointStore(str(tmp_path), "resume")
        # 预置中断现场：batch1 已成功 checkpoint（batch_end_id=id000004）
        store.save(
            {
                "batch_seq": 1,
                "batch_start_id": "id000001",
                "batch_end_id": "id000004",
                "matched": 4,
                "modified": 4,
                "ts_utc": utc_now_iso(),
            }
        )
        result = gov.apply_mutation(
            db, census.candidate_ids, 4, store, census.mutation_plan
        )
        assert result["resumed"] is True
        assert result["resumed_from"] == "id000004"
        # 只处理 batch2（id000005, id000006 均需 mutation），batch1 跳过
        assert result["cumulative_modified"] == 2
        assert result["total_batches"] == 2
        assert [rec["batch_seq"] for rec in result["batches"]] == [2]


# ---------------------------------------------------------------------------
# Verify（V17-004 ~ V17-006）
# ---------------------------------------------------------------------------


class TestVerify:
    def test_verify_equations_pass_after_apply(self, tmp_path):
        db = mixed_db()
        census = run_census(db, build_predicate())
        pre_payload = census_to_report_dict(
            census, mode="apply", run_id="pre", conn_fingerprint={}
        )
        pre_payload["apply"] = {
            "cumulative_matched": 5,
            "cumulative_modified": 5,
        }
        # 先实际 apply，使 db 处于 post 状态
        store = CheckpointStore(str(tmp_path), "v")
        gov.apply_mutation(
            db, census.candidate_ids, 500, store, census.mutation_plan
        )
        report = gov.verify(db, build_predicate(), pre_payload, run_id="v1")
        for key in ("v17_001", "v17_002", "v17_003", "v17_004", "v17_005", "v17_006"):
            assert report["checks"][key] is True, key
        assert report["verify"]["differences"] == []
        assert report["verify"]["post_total_candidates"] == 6
        assert report["verify"]["post_protected_presence"] == report["verify"]["pre_protected_presence"]

    def test_verify_detects_injected_name(self, tmp_path):
        db = mixed_db()
        census = run_census(db, build_predicate())
        pre_payload = census_to_report_dict(
            census, mode="apply", run_id="pre", conn_fingerprint={}
        )
        pre_payload["apply"] = {
            "cumulative_matched": 5,
            "cumulative_modified": 5,
        }
        store = CheckpointStore(str(tmp_path), "v")
        gov.apply_mutation(db, census.candidate_ids, 500, store, census.mutation_plan)
        # 人为破坏：给一条已合规记录注入 name
        db["index_daily_quotes"].update_one(
            {"_id": "id000001"}, {"$set": {"name": "食品饮料"}}
        )
        report = gov.verify(db, build_predicate(), pre_payload, run_id="v2")
        assert report["checks"]["v17_005"] is False
        assert report["checks"]["v17_001"] is False
        assert "v17_005" in report["verify"]["differences"]


# ---------------------------------------------------------------------------
# CLI main
# ---------------------------------------------------------------------------


class TestMainCLI:
    def test_help_returns_zero_without_client(self, tmp_path):
        rc = gov.main(["--help"], conn=make_conn())
        assert rc == 0

    def test_default_mode_is_census(self, tmp_path):
        db = mixed_db()
        rc = gov.main(
            ["--report-dir", str(tmp_path)],
            conn=ConnLoader(env=TEST_ENV, client_factory=lambda **kw: db.client),
        )
        assert rc == EXIT_OK
        report = read_report(tmp_path)
        assert report["mode"] == "census"
        assert report["stats"]["total_candidates"] == 6

    def test_invalid_mode_returns_param(self, tmp_path):
        assert gov.main(["--mode", "bogus"], conn=make_conn()) == EXIT_PARAM

    @pytest.mark.parametrize("value", ["0", "1001", "abc", "-5"])
    def test_invalid_batch_size_returns_param(self, tmp_path, value):
        rc = gov.main(
            ["--mode", "census", "--batch-size", value, "--report-dir", str(tmp_path)],
            conn=make_conn(),
        )
        assert rc == EXIT_PARAM

    def test_missing_conn_key_failfast(self, tmp_path):
        env = {key: value for key, value in TEST_ENV.items() if key != "MONGODB_PASSWORD"}
        loader = ConnLoader(env=env, client_factory=mongomock.MongoClient)
        rc = gov.main(["--mode", "census", "--report-dir", str(tmp_path)], conn=loader)
        assert rc == EXIT_CONN

    def test_apply_without_yes_treated_as_dryrun_zero_write(self, tmp_path):
        db = mixed_db()
        loader = ConnLoader(env=TEST_ENV, client_factory=lambda **kw: db.client)
        before = [
            dict(doc)
            for doc in db["index_daily_quotes"].find({}).sort("_id", 1)
        ]
        rc = gov.main(["--mode", "apply", "--report-dir", str(tmp_path)], conn=loader)
        assert rc == EXIT_OK
        after = list(db["index_daily_quotes"].find({}).sort("_id", 1))
        assert after == before  # 零写（C17-004）

    def test_verify_requires_previous_report(self, tmp_path):
        rc = gov.main(["--mode", "verify", "--report-dir", str(tmp_path)], conn=make_conn())
        assert rc == EXIT_PARAM


# ---------------------------------------------------------------------------
# DESIGN §5.2 显式零写测试矩阵 D1 ~ D12（auditable equivalent）
# ---------------------------------------------------------------------------


class TestDMatrix:
    """D1~D12：全部 main() 级端到端，mongomock + tmp_path，零真实 I/O。"""

    def _loader(self, db):
        return ConnLoader(env=TEST_ENV, client_factory=lambda **kw: db.client)

    def _docs_snapshot(self, db):
        return [dict(doc) for doc in db["index_daily_quotes"].find({}).sort("_id", 1)]

    def test_d1_census_all_compliant(self, tmp_path):
        db = make_db(quote_docs=make_sw_quote_docs(version=1, name=ABSENT))
        before = self._docs_snapshot(db)
        rc = gov.main(["--mode", "census", "--report-dir", str(tmp_path)], conn=self._loader(db))
        assert rc == EXIT_OK
        assert self._docs_snapshot(db) == before  # 零写
        report = read_report(tmp_path)
        assert report["classification"]["already_compliant"] == report["stats"]["total_candidates"]

    def test_d2_census_gate_fail_market(self, tmp_path):
        db = make_db(quote_docs=make_market_fail_docs())
        before = self._docs_snapshot(db)
        rc = gov.main(["--mode", "census", "--report-dir", str(tmp_path)], conn=self._loader(db))
        assert rc == EXIT_STOP
        assert self._docs_snapshot(db) == before  # 零写
        report = read_report(tmp_path)
        assert report["gates"]["C17-204"]["pass"] is False
        assert report["gates"]["C17-204"]["evidence"]["counts"]["HK"] == 1
        assert "C17-204" in report["stop_conditions_hit"]

    def test_d3_census_gate_fail_code_family(self, tmp_path):
        db = make_db(quote_docs=make_code_family_fail_docs())
        before = self._docs_snapshot(db)
        rc = gov.main(["--mode", "census", "--report-dir", str(tmp_path)], conn=self._loader(db))
        assert rc == EXIT_STOP
        assert self._docs_snapshot(db) == before  # 零写
        report = read_report(tmp_path)
        assert report["gates"]["C17-203"]["evidence"]["counterexample_count"] == 1

    def test_d4_census_empty_candidates(self, tmp_path):
        db = make_db(quote_docs=[])
        rc = gov.main(["--mode", "census", "--report-dir", str(tmp_path)], conn=self._loader(db))
        assert rc == EXIT_OK
        report = read_report(tmp_path)
        assert report["nothing_to_do"] is True
        assert report["stats"]["total_candidates"] == 0

    def test_d5_dry_run_mixed_equations(self, tmp_path):
        db = mixed_db()
        before = self._docs_snapshot(db)
        rc = gov.main(["--mode", "dry-run", "--report-dir", str(tmp_path)], conn=self._loader(db))
        assert rc == EXIT_OK
        assert self._docs_snapshot(db) == before  # 零写
        report = read_report(tmp_path)
        # V17-001~003
        assert report["checks"]["v17_001"] is True
        assert report["checks"]["v17_002"] is True
        assert report["checks"]["v17_003"] is True
        assert report["plan"] == {
            "expected_set_version_ops": 5,
            "expected_unset_name_ops": 3,
            "expected_update_docs": 5,
        }
        # 样本合规
        for category, entries in report["samples"].items():
            assert len(entries) <= 5
        text = json.dumps(report, ensure_ascii=False)
        assert "食品饮料" not in text and "svc-pass-123" not in text

    def test_d6_dry_run_gate_fail(self, tmp_path):
        db = make_db(quote_docs=make_code_family_fail_docs())
        before = self._docs_snapshot(db)
        rc = gov.main(["--mode", "dry-run", "--report-dir", str(tmp_path)], conn=self._loader(db))
        assert rc == EXIT_STOP
        assert self._docs_snapshot(db) == before  # 零写

    def test_d7_apply_without_yes_dryrun_zero_write(self, tmp_path):
        db = mixed_db()
        before = self._docs_snapshot(db)
        rc = gov.main(["--mode", "apply", "--report-dir", str(tmp_path)], conn=self._loader(db))
        assert rc == EXIT_OK
        assert self._docs_snapshot(db) == before  # 零写（C17-004）
        report = read_report(tmp_path)
        assert report["mode"] == "dry-run"

    def test_d8_apply_first_idempotent(self, tmp_path):
        db = mixed_db()
        rc = gov.main(
            ["--mode", "apply", "--yes", "--batch-size", "500", "--report-dir", str(tmp_path)],
            conn=self._loader(db),
        )
        assert rc == EXIT_OK
        report = read_report(tmp_path)
        assert report["apply"]["cumulative_modified"] == 5
        assert report["apply"]["cumulative_matched"] == 5
        for doc in db["index_daily_quotes"].find({}):
            if doc["_id"] == "id000001":
                continue
            assert doc["version"] == 1
            assert "name" not in doc
            # 受保护字段存在性不变（V17-006 由 verify 复核）

    def test_d9_apply_second_noop(self, tmp_path):
        db = mixed_db()
        args = ["--mode", "apply", "--yes", "--batch-size", "500", "--report-dir", str(tmp_path)]
        assert gov.main(args, conn=self._loader(db)) == EXIT_OK
        rc = gov.main(args, conn=self._loader(db))
        assert rc == EXIT_OK
        report = read_report(tmp_path)
        # auditable equivalent：M17-005 已合规 id 不发写 → matched==0, modified==0
        assert report["apply"]["cumulative_modified"] == 0
        assert report["apply"]["cumulative_matched"] == 0
        # 幂等收敛：全部候选已合规
        census = run_census(db, build_predicate())
        assert census.classification["already_compliant"] == census.total_candidates

    def test_d10_verify_post_pass(self, tmp_path):
        db = mixed_db()
        args = ["--mode", "apply", "--yes", "--report-dir", str(tmp_path)]
        assert gov.main(args, conn=self._loader(db)) == EXIT_OK
        rc = gov.main(["--mode", "verify", "--report-dir", str(tmp_path)], conn=self._loader(db))
        assert rc == EXIT_OK
        report = read_report(tmp_path)
        assert report["mode"] == "verify"
        for key in ("v17_001", "v17_002", "v17_003", "v17_004", "v17_005", "v17_006"):
            assert report["checks"][key] is True, key
        assert report["verify"]["differences"] == []

    def test_d11_verify_fail_on_injected_name(self, tmp_path):
        db = mixed_db()
        args = ["--mode", "apply", "--yes", "--report-dir", str(tmp_path)]
        assert gov.main(args, conn=self._loader(db)) == EXIT_OK
        # 人为破坏一条 name
        db["index_daily_quotes"].update_one(
            {"_id": "id000001"}, {"$set": {"name": "食品饮料"}}
        )
        rc = gov.main(["--mode", "verify", "--report-dir", str(tmp_path)], conn=self._loader(db))
        assert rc == EXIT_VERIFY
        report = read_report(tmp_path)
        assert "v17_005" in report["verify"]["differences"]

    def test_d12_apply_mid_failure_then_resume(self, tmp_path, monkeypatch):
        db = mixed_db()
        run_id = "d12"

        def flaky_factory(target):
            def factory(db_obj):
                return FlakyWriter(db_obj, fail_ids=target, exc=AutoReconnect("injected"))
            return factory

        # 首次：batch2 注入瞬态异常 → 有界重试耗尽 → 停止（EXIT_STOP=2）
        monkeypatch.setattr(gov, "QuoteMetadataWriter", flaky_factory({"id000005", "id000006"}))
        rc = gov.main(
            [
                "--mode", "apply", "--yes", "--batch-size", "4",
                "--report-dir", str(tmp_path), "--run-id", run_id,
            ],
            conn=self._loader(db),
        )
        assert rc == EXIT_STOP
        ckpt_path = tmp_path / f"quote-governance-checkpoint-{run_id}.jsonl"
        assert ckpt_path.exists()
        lines = [json.loads(line) for line in ckpt_path.read_text().splitlines()]
        assert [rec["batch_seq"] for rec in lines] == [1]  # checkpoint 保留
        assert lines[0]["batch_end_id"] == "id000004"
        # batch1 已生效，batch2 未动
        assert db["index_daily_quotes"].find_one({"_id": "id000004"})["version"] == 1
        doc6 = db["index_daily_quotes"].find_one({"_id": "id000006"})
        assert doc6.get("version") is None  # missing_version 未被写入

        # 修复后重跑同一 run-id → 从 checkpoint 恢复 → 收敛（EXIT_OK=0）
        monkeypatch.setattr(gov, "QuoteMetadataWriter", QuoteMetadataWriter)
        rc2 = gov.main(
            [
                "--mode", "apply", "--yes", "--batch-size", "4",
                "--report-dir", str(tmp_path), "--run-id", run_id,
            ],
            conn=self._loader(db),
        )
        assert rc2 == EXIT_OK
        report = read_report(tmp_path)
        assert report["apply"]["resumed"] is True
        # 只补 batch2（id000005, id000006 均需 mutation）
        assert report["apply"]["cumulative_modified"] == 2
        census = run_census(db, build_predicate())
        assert census.classification["already_compliant"] == census.total_candidates
        assert census.classification["name_absent"] == census.total_candidates
