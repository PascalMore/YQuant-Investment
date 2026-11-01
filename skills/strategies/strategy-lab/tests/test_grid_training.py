"""Synthetic, offline G02-02/03/05/08 checks for DESIGN-06-002 V1.4.

Fixtures are built independently of the backend and adapter. All generated
carriers live in temporary directories; no real training evidence is created.
"""

import contextlib
import copy
import datetime as dt
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import urllib.request


LAB = Path(__file__).resolve().parents[1]
SCRIPT = LAB / "scripts" / "grid_training.py"
SPEC = importlib.util.spec_from_file_location("offline_grid_training", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
gt = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gt)
UTC = dt.timezone.utc
OBSERVED = "2026-11-01T00:00:00Z"
DAY = 86400


def canonical(value):
    """Independent implementation of the frozen JSON byte convention."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def iso(seconds):
    return dt.datetime.fromtimestamp(seconds, UTC).isoformat().replace("+00:00", "Z")


def training_response(cell, *, rows=None, high="94.5"):
    """Construct a wire-shaped synthetic response without using production code."""
    cutoff = int(cell["start_utc"].timestamp())
    base = cell["contract"][:-4]
    identity = {"exchange_id": "gate", "market_type": "swap", "settle": "USDT",
                "contract_type": "direct", "canonical_symbol": f"{base}/USDT:USDT",
                "native_contract": f"{base}_USDT"}
    if rows is None:
        rows = [{"t": cutoff - DAY * index, "o": "92", "h": high, "l": "90",
                 "c": "92", "v": "unverified", "sum": "unverified"}
                for index in range(1, 366)]
    rows = copy.deepcopy(rows)
    metadata_raw = {"name": f"{base}_USDT", "type": "direct", "base": base,
                    "quote": "USDT", "settle": "USDT"}
    metadata = {"raw": metadata_raw, "sha256": digest(metadata_raw),
                "retrieved_at_utc": OBSERVED,
                "source": {"host": "https://api.gateio.ws",
                           "path": "/api/v4/futures/usdt/contracts"},
                "settlement_basis": "endpoint_path", "quote_basis": "contract_name",
                "metadata_scope": "current_snapshot", "historical_identity_validity": "UNKNOWN"}
    valid = []
    invalid = outside = 0
    for row in rows:
        if not cutoff - 365 * DAY <= row["t"] < cutoff:
            outside += 1
            continue
        try:
            prices = {key: float(row[key]) for key in ("o", "h", "l", "c")}
            if (any(isinstance(row[key], bool) or not 0 < prices[key] < float("inf")
                    for key in prices)
                    or prices["l"] > min(prices["o"], prices["c"])
                    or prices["h"] < max(prices["o"], prices["c"])):
                raise ValueError("invalid price")
        except (ValueError, TypeError):
            invalid += 1
            continue
        valid.append({"t": row["t"], **prices})
    unique = {}
    duplicate = conflicting = 0
    for row in sorted(valid, key=lambda row: row["t"]):
        if row["t"] in unique:
            duplicate += 1
            conflicting += row != unique[row["t"]]
        else:
            unique[row["t"]] = row
    ordered = list(unique.values())
    missing = len({cutoff - DAY * index for index in range(1, 366)} - unique.keys())
    misaligned = sum(right["t"] - left["t"] != DAY
                     for left, right in zip(ordered, ordered[1:]))
    unclosed = sum(row["t"] + DAY > cutoff for row in valid)
    count = len(ordered)
    short = None
    if count < 2:
        status, reason = "insufficient_evidence", f"training.unusableSample:count={count},invalid={invalid}"
    elif ordered[-1]["t"] + DAY != cutoff:
        status, reason = "insufficient_evidence", "training.trailingGap:last_close_before_cutoff"
    elif count == 365 and not any((missing, misaligned, duplicate, conflicting, invalid)):
        status, reason, short = "ok", None, False
    elif missing:
        status, reason = "insufficient_evidence", f"training.unprovenReturn:count={count},missing={missing}"
    else:
        status = "insufficient_evidence"
        reason = (f"training.discontinuity:missing={missing},misaligned={misaligned},"
                  f"duplicate={duplicate},conflicting={conflicting},invalid={invalid}")
    bars = [{"open_time_utc": iso(row["t"]), "close_time_utc": iso(row["t"] + DAY),
             "available_at_utc": iso(row["t"] + DAY), "availability_basis": "bar_close_boundary",
             "observed_at_utc": OBSERVED, "open": row["o"], "high": row["h"],
             "low": row["l"], "close": row["c"], "identity": dict(identity)}
            for row in ordered]
    coverage = {"requested_start_utc": iso(cutoff - 365 * DAY), "cutoff_utc": iso(cutoff),
                "requested_limit": 365, "raw_count": len(rows), "actual_count": count,
                "unique_count": count, "first_open_utc": bars[0]["open_time_utc"] if bars else None,
                "last_open_utc": bars[-1]["open_time_utc"] if bars else None,
                "last_close_utc": bars[-1]["close_time_utc"] if bars else None,
                "duplicate_count": duplicate, "conflicting_count": conflicting,
                "missing_count": missing, "misaligned_count": misaligned,
                "excluded_unclosed_count": unclosed, "excluded_out_of_range_count": outside,
                "short_training_history": short,
                "listing_boundary": {"status": "UNKNOWN", "reason": "listing_boundary_unverified"}}
    return {"schema_version": "grid_training_ohlc_v1", "data_mode": "training_ohlc",
            "status": status, "reason": reason, "market": "Crypto", "symbol": cell["contract"],
            "timeframe": "1D", "count": count, "identity": identity,
            "identity_evidence": metadata,
            "source": {"provider": "native_gate", "host": "https://api.gateio.ws",
                       "path": "/api/v4/futures/usdt/candlesticks",
                       "query": {"contract": f"{base}_USDT", "interval": "1d",
                                 "from": cutoff - 365 * DAY, "to": cutoff - 1},
                       "retrieved_at_utc": OBSERVED, "raw_rows": rows,
                       "raw_rows_sha256": digest(rows), "provider_request_count": 2,
                       "request_policy": {"automatic_retries": 0, "pagination": 0, "redirects": 0},
                       "metadata": metadata},
            "klines": bars, "normalized_sha256": digest(bars), "coverage": coverage,
            "synthetic": False, "volume_status": "not_provided", "backtest_eligible": False,
            "historical_volume_validity": "UNKNOWN"}


def confirmed_listing_response(cell, count):
    """Internal synthetic listing receipt, never an API metadata input."""
    cutoff = int(cell["start_utc"].timestamp())
    rows = [{"t": cutoff - DAY * index, "o": "92", "h": "94.5", "l": "90", "c": "92"}
            for index in range(1, count + 1)]
    data = training_response(cell, rows=rows)
    first_full = cutoff - count * DAY
    # A mid-day listing admits its following midnight, not that partial day.
    raw = {"identity": copy.deepcopy(data["identity"]),
           "listed_at_utc": iso(first_full - DAY // 2)}
    data["coverage"]["listing_boundary"] = {
        "status": "VERIFIED", "first_full_open_utc": iso(first_full),
        "source": "internal_synthetic", "raw": raw, "sha256": digest(raw),
        "retrieved_at_utc": OBSERVED,
    }
    data["coverage"]["short_training_history"] = True
    data["status"] = "ok" if count >= 2 else "history_insufficient"
    data["reason"] = None if count >= 2 else f"training.historyInsufficient:count={count}"
    return data


class OfflineTrainingCase(unittest.TestCase):
    def setUp(self):
        for target in ("socket.socket.connect", "socket.socket.connect_ex",
                       "socket.create_connection", "urllib.request.urlopen"):
            guard = mock.patch(target, side_effect=AssertionError("offline test attempted network"))
            guard.start()
            self.addCleanup(guard.stop)
        self.gr = gt.grid_research()
        self.cells = self.gr.build_cells()
        self.cell = self.cells[0]
        self.data = training_response(self.cell)
        self.temporary = tempfile.TemporaryDirectory(prefix="g02-synthetic-")
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name)

    def freeze(self, responses=None):
        if responses is None:
            responses = {cell["cell_id"]: training_response(cell) for cell in self.cells}
        result = gt.freeze_training(self.cells, responses, output_dir=self.output)
        return Path(result["manifest_ref"])

    def save_manifest(self, path, manifest):
        body = {key: value for key, value in manifest.items() if key != "body_sha256"}
        manifest["body_sha256"] = digest(body)
        path.write_bytes(canonical(manifest))


class ValidateTrainingTests(OfflineTrainingCase):
    def test_full_365_response_identity_hashes_raw_order_and_cutoff(self):
        result = gt.validate_training_response(self.data, self.cell)
        self.assertEqual("ok", result["status"])
        self.assertEqual(365, len(result["bars"]))
        self.assertEqual({"L": 90.0, "U": 94.5}, result["training_range"])
        self.assertEqual(iso(int(self.cell["start_utc"].timestamp())), result["last_available"])
        self.assertEqual(digest(self.data["source"]["raw_rows"]), result["evidence"]["raw_rows_sha256"])
        self.assertEqual(digest(self.data["source"]["metadata"]["raw"]), result["evidence"]["metadata_sha256"])
        self.assertEqual(digest(self.data["klines"]), result["evidence"]["normalized_sha256"])
        self.assertGreater(self.data["source"]["raw_rows"][0]["t"],
                           self.data["source"]["raw_rows"][-1]["t"])
        self.assertLess(result["bars"][0]["open_time_utc"], result["bars"][-1]["open_time_utc"])
        for bar in result["bars"]:
            self.assertNotIn("volume", bar)
            self.assertNotIn("base_volume", bar)
            self.assertNotIn("provenance_ok", bar)

    def test_raw_metadata_and_normalized_field_or_order_tampering_rejected(self):
        for kind in ("raw-field", "raw-order", "metadata-field", "normalized-field", "normalized-order"):
            with self.subTest(kind=kind):
                data = copy.deepcopy(self.data)
                if kind == "raw-field":
                    data["source"]["raw_rows"][0]["c"] = "91"
                elif kind == "raw-order":
                    data["source"]["raw_rows"].reverse()
                elif kind == "metadata-field":
                    data["source"]["metadata"]["raw"]["type"] = "inverse"
                elif kind == "normalized-field":
                    data["klines"][0]["close"] = 91.0
                else:
                    data["klines"].reverse()
                with self.assertRaises(gt.TrainingVerificationError):
                    gt.validate_training_response(data, self.cell)

    def test_self_consistent_digest_cannot_hide_wrong_identity_or_price(self):
        for kind in ("price", "identity", "available-at"):
            with self.subTest(kind=kind):
                data = copy.deepcopy(self.data)
                if kind == "price":
                    data["klines"][0]["close"] = 91.0
                elif kind == "identity":
                    data["klines"][0]["identity"]["market_type"] = "spot"
                else:
                    data["klines"][0]["available_at_utc"] = OBSERVED
                data["normalized_sha256"] = digest(data["klines"])
                with self.assertRaises(gt.TrainingVerificationError):
                    gt.validate_training_response(data, self.cell)

    def test_source_query_count_flags_and_external_provenance_are_not_trusted(self):
        mutations = [lambda data: data["source"].update(host="https://invalid.example"),
                     lambda data: data["source"]["query"].update(to=1),
                     lambda data: data.update(count=364),
                     lambda data: data["coverage"].update(missing_count=1),
                     lambda data: data.update(synthetic=True),
                     lambda data: data.update(backtest_eligible=True),
                     lambda data: data.update(provenance_ok=True),
                     lambda data: data["klines"][0].update(provenance_ok=True)]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                data = copy.deepcopy(self.data)
                mutate(data)
                with self.assertRaises(gt.TrainingVerificationError):
                    gt.prepare_training_cell(self.cell, data)

    def test_unproven_short_empty_single_gap_duplicates_and_invalid_prices_not_ready(self):
        original = self.data["source"]["raw_rows"]
        cases = {"short": original[:2], "empty": [], "single": original[:1],
                 "tail-gap": original[1:], "middle-gap": original[:100] + original[101:],
                 "duplicate": original + [original[10]],
                 "conflict": original + [dict(original[10], c="91")],
                 "misaligned": [dict(row, t=row["t"] + (3600 if index == 10 else 0))
                                for index, row in enumerate(original)]}
        for value in ("NaN", "Inf", "0", "-1", "bad", True, None):
            changed = copy.deepcopy(original)
            changed[10]["o"] = value
            cases[f"price-{value}"] = changed
        for name, rows in cases.items():
            with self.subTest(name=name):
                response = training_response(self.cell, rows=rows)
                result = gt.prepare_training_cell(self.cell, response)
                self.assertEqual("insufficient_evidence", result["status"])
                self.assertIsNone(result["parameters"])
                self.assertIsNone(result["geometry"])
                self.assertIsNone(result["validate"]["short_training_history"])
                self.assertEqual("UNKNOWN", result["validate"]["listing_boundary"]["status"])

    def test_confirmed_two_day_listing_reuses_coverage_and_geometry(self):
        data = confirmed_listing_response(self.cell, 2)
        with mock.patch.object(self.gr, "check_coverage", wraps=self.gr.check_coverage) as coverage, \
                mock.patch.object(self.gr, "derive_geometry", wraps=self.gr.derive_geometry) as geometry:
            result = gt.prepare_training_cell(self.cell, data)
        self.assertEqual("ready", result["status"])
        self.assertIs(result["validate"]["short_training_history"], True)
        self.assertEqual("VERIFIED", result["validate"]["listing_boundary"]["status"])
        self.assertEqual(2, len(geometry.call_args.args[0]))
        self.assertEqual(DAY, coverage.call_args.args[4])
        self.assertEqual(data["klines"][0]["open_time_utc"], iso(int(coverage.call_args.args[2].timestamp())))
        self.assertEqual({"L": 90.0, "U": 94.5, "N": 4, "grid_lines": 5},
                         {key: result["geometry"][key] for key in ("L", "U", "N", "grid_lines")})
        self.assertAlmostEqual(100 * ((94.5 / 90) ** (1 / 4) - 1), result["geometry"]["g_pct"])
        self.assertEqual(2, result["parameters"]["training"]["count"])
        self.assertIs(result["parameters"]["training"]["short"], True)

    def test_confirmed_zero_and_one_bar_are_na_without_parameters(self):
        for count in (0, 1):
            with self.subTest(count=count):
                result = gt.prepare_training_cell(self.cell, confirmed_listing_response(self.cell, count))
                self.assertEqual("history_insufficient", result["status"])
                self.assertEqual(count, result["validate"]["count"])
                self.assertEqual("VERIFIED", result["validate"]["listing_boundary"]["status"])
                self.assertIsNone(result["parameters"])
                self.assertIsNone(result["geometry"])

    def test_confirmed_listing_contradictions_cannot_admit_short_samples(self):
        for kind in ("digest", "identity", "partial-day", "first-full", "missing-source",
                     "future-retrieval", "tail-gap", "middle-gap", "duplicate", "invalid-price"):
            with self.subTest(kind=kind):
                data = confirmed_listing_response(self.cell, 3)
                listing = data["coverage"]["listing_boundary"]
                if kind == "digest":
                    listing["sha256"] = "0" * 64
                elif kind == "identity":
                    listing["raw"]["identity"]["market_type"] = "spot"
                    listing["sha256"] = digest(listing["raw"])
                elif kind == "partial-day":
                    listing["raw"]["listed_at_utc"] = listing["first_full_open_utc"].replace("00:00:00", "12:00:00")
                    listing["sha256"] = digest(listing["raw"])
                elif kind == "first-full":
                    listing["first_full_open_utc"] = iso(int(self.cell["start_utc"].timestamp()) - DAY)
                elif kind == "missing-source":
                    del listing["source"]
                elif kind == "future-retrieval":
                    listing["retrieved_at_utc"] = "2099-01-01T00:00:00Z"
                else:
                    rows = copy.deepcopy(data["source"]["raw_rows"])
                    if kind == "tail-gap":
                        rows = rows[1:]
                    elif kind == "middle-gap":
                        rows.pop(1)
                    elif kind == "duplicate":
                        rows.append(rows[-1])
                    else:
                        rows[0]["o"] = "NaN"
                    replacement = training_response(self.cell, rows=rows)
                    replacement["coverage"]["listing_boundary"] = listing
                    replacement["coverage"]["short_training_history"] = True
                    replacement["status"], replacement["reason"] = "ok", None
                    data = replacement
                with self.assertRaises(gt.TrainingVerificationError):
                    gt.prepare_training_cell(self.cell, data)

    def test_numeric_nonfinite_cannot_be_evidenced(self):
        for value in (float("nan"), float("inf")):
            data = copy.deepcopy(self.data)
            data["source"]["raw_rows"][0]["o"] = value
            with self.assertRaises(gt.TrainingVerificationError):
                gt.validate_training_response(data, self.cell)

    def test_out_of_range_window_rows_never_change_training_extrema(self):
        cutoff = int(self.cell["start_utc"].timestamp())
        rows = self.data["source"]["raw_rows"] + [
            {"t": cutoff, "o": "100", "h": "99999", "l": "1", "c": "100"},
            {"t": cutoff - 366 * DAY, "o": "100", "h": "99999", "l": "1", "c": "100"}]
        result = gt.prepare_training_cell(self.cell, training_response(self.cell, rows=rows))
        self.assertEqual("ready", result["status"])
        self.assertEqual(2, result["validate"]["coverage"]["excluded_out_of_range_count"])
        self.assertEqual(90.0, result["geometry"]["L"])
        self.assertEqual(94.5, result["geometry"]["U"])

    def test_no_feasible_geometry_and_flat_range_do_not_invent_parameters(self):
        result = gt.prepare_training_cell(self.cell, training_response(self.cell, high="90.1",
            rows=[dict(row, o="90", c="90", h="90.1") for row in self.data["source"]["raw_rows"]]))
        self.assertEqual("no-feasible-geometry", result["status"])
        self.assertIsNone(result["parameters"])
        flat = [dict(row, o="90", c="90", h="90") for row in self.data["source"]["raw_rows"]]
        with self.assertRaises(ValueError):
            gt.prepare_training_cell(self.cell, training_response(self.cell, rows=flat))


class FreezeTrainingTests(OfflineTrainingCase):
    def test_actual_pure_functions_sixteen_rows_full_parameters_and_locked_code(self):
        with mock.patch.object(self.gr, "build_cells", wraps=self.gr.build_cells) as build, \
                mock.patch.object(self.gr, "check_coverage", wraps=self.gr.check_coverage) as coverage, \
                mock.patch.object(self.gr, "derive_geometry", wraps=self.gr.derive_geometry) as geometry, \
                mock.patch.object(self.gr, "generate_strategy_source",
                                  wraps=self.gr.generate_strategy_source) as generate:
            path = self.freeze()
            build.assert_called()
            self.assertEqual(16, coverage.call_count)
            self.assertEqual(16, geometry.call_count)
            self.assertEqual(16, generate.call_count)
            self.assertTrue(all(call.args[-1] == DAY for call in coverage.call_args_list))
            self.assertTrue(all(call.kwargs["geometry"]["N"] == 4 for call in generate.call_args_list))
        manifest = json.loads(path.read_bytes())
        self.assertEqual("complete", manifest["status"])
        self.assertEqual([cell["cell_id"] for cell in self.cells],
                         [item["cell_id"] for item in manifest["items"]])
        self.assertEqual(16, len({item["cell_id"] for item in manifest["items"]}))
        for item in manifest["items"]:
            self.assertEqual("ready", item["status"])
            self.assertIsNone(item["job_id"])
            self.assertIsNone(item["run_id"])
            self.assertEqual("locked_candidate", item["code_kind"])
            self.assertIs(item["code_execution_eligible"], False)
            parameters = json.loads((self.output / item["parameters_ref"]).read_bytes())
            self.assertEqual(gt.COSTS, parameters["costs"])
            self.assertEqual(365, parameters["training"]["count"])
            self.assertEqual(item["geometry"], parameters["geometry"])
            self.assertEqual({"n_max": 200, "g_lower": 0.45, "g_upper": 1.5,
                              "old_cost_assumption_pct": 0.14, "new_score_cost_pct": 0.20},
                             {key: parameters["geometry"][key] for key in
                              ("n_max", "g_lower", "g_upper", "old_cost_assumption_pct", "new_score_cost_pct")})
            self.assertIn("actual_fill_rule", parameters["geometry"])
            self.assertEqual(3, len(parameters["generator_sources"]))
            self.assertEqual(f"Crypto:{parameters['contract'][:-4]}/USDT@gate:swap", item["instrument"])
            source = (self.output / item["code_ref"]).read_text()
            self.assertIn("EVIDENCE_READY = False", source)
            self.assertIn("offline_example_not_research_evidence", source)
        self.assertEqual("ok", gt.verify_training_freeze(path)["status"])

    def test_evidence_parameters_code_and_manifest_byte_tampering_rejected(self):
        path = self.freeze()
        manifest = json.loads(path.read_bytes())
        item = manifest["items"][0]
        targets = [self.output / item[key] for key in ("evidence_ref", "parameters_ref", "code_ref")] + [path]
        for target in targets:
            with self.subTest(target=target.name):
                original = target.read_bytes()
                target.write_bytes(original + b" ")
                try:
                    # Manifest whitespace is not part of its object-body digest.
                    if target == path:
                        changed = json.loads(original)
                        changed["items"][0]["count"] = 1
                        target.write_bytes(canonical(changed))
                    with self.assertRaises(ValueError):
                        gt.verify_training_freeze(path)
                finally:
                    target.write_bytes(original)
        self.assertEqual("ok", gt.verify_training_freeze(path)["status"])

    def test_rehashed_parameter_cost_tampering_still_rejected_by_rederivation(self):
        path = self.freeze()
        manifest = json.loads(path.read_bytes())
        item = manifest["items"][0]
        parameters_path = self.output / item["parameters_ref"]
        parameters = json.loads(parameters_path.read_bytes())
        parameters["costs"]["leverage"] = 1
        parameters_path.write_bytes(canonical(parameters))
        item["params_sha256"] = hashlib.sha256(parameters_path.read_bytes()).hexdigest()
        self.save_manifest(path, manifest)
        with self.assertRaises(gt.TrainingVerificationError):
            gt.verify_training_freeze(path)

    def test_rehashed_generator_identity_and_reference_escape_rejected(self):
        path = self.freeze()
        original = path.read_bytes()
        for kind in ("digest", "missing-source", "escape"):
            with self.subTest(kind=kind):
                manifest = json.loads(original)
                item = manifest["items"][0]
                if kind == "digest":
                    item["generator_sources"][0]["sha256"] = "0" * 64
                elif kind == "missing-source":
                    item["generator_sources"] = item["generator_sources"][1:]
                else:
                    item["evidence_ref"] = "../outside.json"
                self.save_manifest(path, manifest)
                with self.assertRaises(gt.TrainingVerificationError):
                    gt.verify_training_freeze(path)
        path.write_bytes(original)

    def test_stop_tail_is_incomplete_sixteen_rows_with_null_files_and_no_padding(self):
        path = self.freeze({self.cell["cell_id"]: self.data})
        manifest = json.loads(path.read_bytes())
        self.assertEqual("incomplete", manifest["status"])
        self.assertEqual(16, len(manifest["items"]))
        for item in manifest["items"][1:]:
            self.assertEqual("insufficient_evidence", item["status"])
            self.assertEqual("not_read_due_to_stop", item["reason"])
            for key in ("evidence_ref", "evidence_sha256", "parameters_ref", "params_sha256",
                        "code_ref", "code_sha256", "identity", "geometry", "count"):
                self.assertIsNone(item[key])
        self.assertEqual("incomplete", gt.verify_training_freeze(path)["manifest_status"])
        manifest["status"] = "complete"
        self.save_manifest(path, manifest)
        with self.assertRaises(gt.TrainingVerificationError):
            gt.verify_training_freeze(path)

    def test_not_read_row_cannot_be_forged_ready_even_with_rehashed_manifest(self):
        path = self.freeze({})
        manifest = json.loads(path.read_bytes())
        manifest["items"][-1]["status"] = "ready"
        self.save_manifest(path, manifest)
        with self.assertRaises(gt.TrainingVerificationError):
            gt.verify_training_freeze(path)

    def test_no_feasible_and_unproven_history_keep_evidence_without_code(self):
        rows = [dict(row, o="90", c="90", h="90.1") for row in self.data["source"]["raw_rows"]]
        second = self.cells[1]
        path = self.freeze({self.cell["cell_id"]: training_response(self.cell, rows=rows),
                            second["cell_id"]: training_response(second, rows=[])})
        items = json.loads(path.read_bytes())["items"]
        self.assertEqual("no-feasible-geometry", items[0]["status"])
        self.assertEqual("insufficient_evidence", items[1]["status"])
        for item in items[:2]:
            self.assertTrue((self.output / item["evidence_ref"]).is_file())
            self.assertIsNone(item["parameters_ref"])
            self.assertIsNone(item["code_ref"])
        self.assertEqual("ok", gt.verify_training_freeze(path)["status"])

    def test_short_and_na_rows_keep_listing_evidence_and_reverify_freeze(self):
        responses = {cell["cell_id"]: training_response(cell) for cell in self.cells}
        for count, cell in zip((2, 0, 1), self.cells):
            responses[cell["cell_id"]] = confirmed_listing_response(cell, count)
        path = self.freeze(responses)
        manifest = json.loads(path.read_bytes())
        self.assertEqual(16, len(manifest["items"]))
        self.assertEqual("complete", manifest["status"])
        self.assertEqual("ready", manifest["items"][0]["status"])
        for item, count in zip(manifest["items"][1:3], (0, 1)):
            self.assertEqual("history_insufficient", item["status"])
            self.assertEqual(count, item["count"])
            self.assertEqual("VERIFIED", item["listing"]["status"])
            self.assertTrue((self.output / item["evidence_ref"]).is_file())
            for key in ("parameters_ref", "params_sha256", "code_ref", "code_sha256", "geometry"):
                self.assertIsNone(item[key])
        self.assertEqual("ok", gt.verify_training_freeze(path)["status"])
        item = manifest["items"][1]
        evidence_path = self.output / item["evidence_ref"]
        data = json.loads(evidence_path.read_bytes())
        listing = data["coverage"]["listing_boundary"]
        listing["raw"]["listed_at_utc"] = iso(int(self.cells[1]["start_utc"].timestamp()) - 10 * DAY)
        listing["sha256"] = digest(listing["raw"])
        evidence_path.write_bytes(canonical(data))
        item["evidence_sha256"] = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
        self.save_manifest(path, manifest)
        with self.assertRaises(gt.TrainingVerificationError):
            gt.verify_training_freeze(path)

    def test_wrong_matrix_unknown_response_and_overwrite_refused(self):
        for cells, responses in ((self.cells[:-1], {}),
                                 (self.cells[:-1] + [self.cells[0]], {}),
                                 (self.cells, {"UNKNOWN-W1": self.data})):
            with self.assertRaises(gt.TrainingVerificationError):
                gt.freeze_training(cells, responses, output_dir=self.output)
        path = self.freeze({})
        original = path.read_bytes()
        with self.assertRaises(gt.TrainingVerificationError):
            self.freeze({})
        self.assertEqual(original, path.read_bytes())


class CollectorAndCliTests(OfflineTrainingCase):
    def collect(self, caller, clock=lambda: 0.0):
        return gt.collect_training(base_url="http://offline.invalid", output_dir=self.output,
            agent_call=caller, resolve_agent_token=lambda: "offline-placeholder",
            now_utc=lambda: dt.datetime(2026, 11, 1, tzinfo=UTC), monotonic=clock)

    def test_fake_get_complete_budget_and_no_headers_or_account_material(self):
        calls = []

        def caller(operation, **kwargs):
            calls.append((operation, kwargs))
            if operation == "agent_whoami":
                return {"scopes": ["R"], "markets": ["Crypto"], "exchange": "gate",
                        "product": "swap", "account": "private-account-sentinel"}, {"x": "header-sentinel"}
            cell = self.cells[len(calls) - 2]
            self.assertEqual({"data_mode": "training_ohlc", "market": "Crypto",
                              "symbol": cell["contract"], "timeframe": "1D",
                              "exchange_id": "gate", "market_type": "swap",
                              "before_time": int(cell["start_utc"].timestamp()), "limit": 365},
                             kwargs["params"])
            return training_response(cell), {"x": "header-sentinel"}

        result = self.collect(caller)
        self.assertEqual("complete", result["manifest_status"])
        self.assertEqual(17, len(calls))
        self.assertEqual(1, result["budget"]["whoami_attempts"])
        self.assertEqual(16, result["budget"]["klines_attempts"])
        self.assertEqual(32, result["budget"]["provider_requests_reserved"])
        self.assertEqual(32, result["budget"]["provider_receipts"])
        self.assertTrue(all(operation in ("agent_whoami", "agent_klines") for operation, _ in calls))
        for path in self.output.rglob("*"):
            if path.is_file():
                text = path.read_text()
                for forbidden in ("offline-placeholder", "header-sentinel", "private-account-sentinel"):
                    self.assertNotIn(forbidden, text)

    def test_confirmed_na_is_retained_and_collection_continues(self):
        calls = []

        def caller(operation, **kwargs):
            calls.append(operation)
            if operation == "agent_whoami":
                return {"scopes": ["R"]}, {}
            index = len(calls) - 2
            cell = self.cells[index]
            return (confirmed_listing_response(cell, index) if index < 2
                    else training_response(cell)), {}

        result = self.collect(caller)
        self.assertIsNone(result["stop_reason"])
        self.assertEqual("complete", result["manifest_status"])
        self.assertEqual(17, len(calls))
        self.assertEqual(32, result["budget"]["provider_requests_reserved"])
        manifest = json.loads(Path(result["manifest_ref"]).read_bytes())
        self.assertEqual(["history_insufficient", "history_insufficient"],
                         [item["status"] for item in manifest["items"][:2]])
        self.assertEqual("ready", manifest["items"][2]["status"])
        self.assertEqual("ok", gt.verify_training_freeze(Path(result["manifest_ref"]))["status"])

    def test_failure_stops_without_retry_and_records_persisted_stop_reason(self):
        calls = []

        def caller(operation, **kwargs):
            calls.append(operation)
            if operation == "agent_whoami":
                return {"scopes": ["R"]}, {}
            raise TimeoutError("offline timeout")

        result = self.collect(caller)
        self.assertEqual(["agent_whoami", "agent_klines"], calls)
        self.assertEqual("incomplete", result["manifest_status"])
        self.assertEqual("unexpected:TimeoutError", result["stop_reason"])
        budget = json.loads((self.output / gt.BUDGET_REF).read_bytes())
        self.assertEqual(result["stop_reason"], budget["stop_reason"])
        self.assertEqual(2, budget["provider_requests_reserved"])

    def test_unknown_training_qualification_stops_before_next_cell(self):
        calls = []

        def caller(operation, **kwargs):
            calls.append(operation)
            if operation == "agent_whoami":
                return {"scopes": ["R"]}, {}
            return training_response(self.cell, rows=[]), {}

        result = self.collect(caller)
        self.assertEqual(["agent_whoami", "agent_klines"], calls)
        self.assertEqual("incomplete", result["manifest_status"])
        self.assertIsNotNone(result["stop_reason"])
        manifest = json.loads(Path(result["manifest_ref"]).read_bytes())
        self.assertIsNotNone(manifest["items"][0]["evidence_ref"])
        self.assertEqual("not_read_due_to_stop", manifest["items"][1]["reason"])

    def test_wall_clock_and_provider_budget_reserved_before_kline(self):
        for kind in ("wall-clock", "provider-budget"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory(prefix="g02-budget-") as directory:
                self.output = Path(directory)
                caller = mock.Mock(return_value=({"scopes": ["R"]}, {}))
                clock = iter((0.0, 1800.0, 1800.0)) if kind == "wall-clock" else iter((0.0,) * 3)
                with mock.patch.object(gt, "PROVIDER_REQUEST_LIMIT", 1 if kind == "provider-budget" else 50):
                    result = self.collect(caller, lambda: next(clock))
                self.assertEqual(1, caller.call_count)
                self.assertEqual(0, result["budget"]["klines_attempts"])
                self.assertEqual(0, result["budget"]["provider_requests_reserved"])
                self.assertIsNotNone(result["stop_reason"])

    def test_http_and_billing_stop_matrix_preserves_budget_and_tail(self):
        qd = gt.quantdinger()
        cases = (401, 403, 402, 500, 502, 503, "charged-number", "charged-status")
        for phase in ("whoami", "klines"):
            for failure in cases:
                with self.subTest(phase=phase, failure=failure), \
                        tempfile.TemporaryDirectory(prefix="g02-stop-matrix-") as directory:
                    self.output = Path(directory)
                    calls = []

                    def send(url, method, headers, payload, timeout):
                        self.assertEqual("GET", method)
                        self.assertIsNone(payload)
                        operation = "whoami" if url.endswith("/whoami") else "klines"
                        calls.append(operation)
                        failing = operation == phase and (phase == "whoami" or len(calls) == 3)
                        data = ({"scopes": ["R"], "markets": ["Crypto"],
                                 "exchange": "gate", "product": "swap"}
                                if operation == "whoami" else training_response(self.cells[len(calls) - 2]))
                        status = 200
                        if failing:
                            if isinstance(failure, int):
                                status = failure
                            else:
                                data["billing"] = ({"charged": "0.25", "status": "free"}
                                                   if failure == "charged-number" else {"status": "charged"})
                        body = {"code": 0 if status == 200 else status, "message": "offline", "data": data}
                        return status, canonical(body), {"x-private": "header-sentinel"}

                    with mock.patch.object(qd, "_http_send", side_effect=send):
                        result = self.collect(qd.agent_call)
                    expected_calls = ["whoami"] if phase == "whoami" else ["whoami", "klines", "klines"]
                    self.assertEqual(expected_calls, calls)
                    self.assertEqual("incomplete", result["manifest_status"])
                    expected_reason = ("billing.charged" if failure in (402, "charged-number", "charged-status")
                                       else f"http.{failure}")
                    self.assertIn(expected_reason, result["stop_reason"])
                    budget = json.loads((self.output / gt.BUDGET_REF).read_bytes())
                    self.assertEqual(result["stop_reason"], budget["stop_reason"])
                    self.assertEqual(1, budget["whoami_attempts"])
                    self.assertEqual(0 if phase == "whoami" else 2, budget["klines_attempts"])
                    self.assertEqual(0 if phase == "whoami" else 4, budget["provider_requests_reserved"])
                    self.assertEqual(0 if phase == "whoami" else 2, budget["provider_receipts"])
                    manifest = json.loads(Path(result["manifest_ref"]).read_bytes())
                    self.assertEqual(16, len(manifest["items"]))
                    first_unread = 0 if phase == "whoami" else 1
                    for item in manifest["items"][first_unread:]:
                        self.assertEqual("not_read_due_to_stop", item["reason"])
                        self.assertIsNone(item["evidence_ref"])
                        self.assertIsNone(item["parameters_ref"])
                        self.assertIsNone(item["code_ref"])
                    if phase == "klines":
                        self.assertEqual("ready", manifest["items"][0]["status"])
                        self.assertTrue((self.output / manifest["items"][0]["evidence_ref"]).is_file())
                    self.assertEqual("ok", gt.verify_training_freeze(Path(result["manifest_ref"]))["status"])

    def test_identity_digest_unknown_stop_matrix_has_no_later_calls(self):
        for failure in ("whoami-exchange", "whoami-product", "identity", "raw-digest",
                        "metadata-digest", "normalized-digest", "UNKNOWN"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory(prefix="g02-integrity-") as directory:
                self.output = Path(directory)
                calls = []

                def caller(operation, **kwargs):
                    calls.append(operation)
                    if operation == "agent_whoami":
                        return {"scopes": ["R"], "exchange": "binance" if failure == "whoami-exchange" else "gate",
                                "product": "spot" if failure == "whoami-product" else "swap"}, {}
                    data = training_response(self.cells[len(calls) - 2])
                    if len(calls) == 3:
                        if failure == "identity":
                            data["identity"]["native_contract"] = "OTHER_USDT"
                        elif failure == "raw-digest":
                            data["source"]["raw_rows_sha256"] = "0" * 64
                        elif failure == "metadata-digest":
                            data["source"]["metadata"]["sha256"] = "0" * 64
                        elif failure == "normalized-digest":
                            data["normalized_sha256"] = "0" * 64
                        else:
                            data = training_response(self.cells[1], rows=[])
                    return data, {}

                result = self.collect(caller)
                whoami_failed = failure.startswith("whoami-")
                self.assertEqual(["agent_whoami"] if whoami_failed else
                                 ["agent_whoami", "agent_klines", "agent_klines"], calls)
                self.assertIsNotNone(result["stop_reason"])
                budget = json.loads((self.output / gt.BUDGET_REF).read_bytes())
                self.assertEqual(result["stop_reason"], budget["stop_reason"])
                self.assertEqual(0 if whoami_failed else 4, budget["provider_requests_reserved"])
                manifest = json.loads(Path(result["manifest_ref"]).read_bytes())
                self.assertEqual("incomplete", manifest["status"])
                first_unread = 0 if whoami_failed else (2 if failure == "UNKNOWN" else 1)
                for item in manifest["items"][first_unread:]:
                    self.assertEqual("not_read_due_to_stop", item["reason"])
                    self.assertIsNone(item["evidence_ref"])
                if failure == "UNKNOWN":
                    self.assertEqual("insufficient_evidence", manifest["items"][1]["status"])
                    self.assertIsNotNone(manifest["items"][1]["evidence_ref"])
                    self.assertEqual(4, budget["provider_receipts"])
                self.assertEqual("ok", gt.verify_training_freeze(Path(result["manifest_ref"]))["status"])

    def test_existing_training_directory_refused_before_token_resolution(self):
        (self.output / gt.EVIDENCE_SUBDIR).mkdir(parents=True)
        resolver = mock.Mock(side_effect=AssertionError("must not resolve token"))
        with self.assertRaises(gt.TrainingVerificationError):
            gt.collect_training(base_url="http://offline.invalid", output_dir=self.output,
                agent_call=mock.Mock(), resolve_agent_token=resolver,
                now_utc=lambda: dt.datetime(2026, 11, 1, tzinfo=UTC), monotonic=lambda: 0.0)
        resolver.assert_not_called()

    def test_cli_describe_and_verify_from_non_scripts_cwd_are_offline(self):
        path = self.freeze({})
        with mock.patch.object(gt, "_default_resolve_agent_token", side_effect=AssertionError("no token")), \
                mock.patch.object(gt, "_default_agent_call", side_effect=AssertionError("no GET")):
            for args in (["--describe"], ["--verify-freeze", str(path)]):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(0, gt.main(args))
                data = json.loads(output.getvalue())
                self.assertEqual(16, len(data["cells"]))
        process = subprocess.run([sys.executable, "-B", str(SCRIPT), "--describe"],
                                 cwd=self.output, capture_output=True, text=True, check=False)
        self.assertEqual(0, process.returncode, process.stderr)
        self.assertEqual(16, len(json.loads(process.stdout)["cells"]))

    def test_cli_missing_mode_conflicts_and_execution_or_token_flags_rejected(self):
        for args in ([], ["--describe", "--collect"], ["--collect"],
                     ["--describe", "--token", "offline-placeholder"],
                     ["--execute"], ["--backtest"], ["--compile"], ["--fetch-direct"]):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    gt.main(args)
                self.assertEqual(2, error.exception.code)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(3, gt.main(["--verify-freeze", str(self.output / "missing.json")]))


if __name__ == "__main__":
    unittest.main()
