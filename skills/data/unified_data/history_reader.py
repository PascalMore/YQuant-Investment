"""BTC5m 窄历史只读 facade：有界 keyset、三个独立流及消费后内容核验。"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import asdict
from decimal import Decimal
from typing import Any

from bson import BSON, Decimal128
from bson.raw_bson import RawBSONDocument
from pymongo import timeout
from pymongo.collection import Collection

from .history_types import (
    AVAILABILITY_RULES, CONTENT_MANIFEST_VERSION, DATASET_KLINES, DATASET_ROUNDS,
    INTERVAL, MARKET_TYPE, SCHEMA_VERSION, SERIES_SLUG, SOURCE_KLINES, SOURCE_ROUNDS,
    SYMBOL, Coverage, FeatureRow, HistoryError, HistoryRequest, HistoryWindow, LabelRow,
    RoundMetadataRow, canonical_json, ceil_ms_to_us, from_us, parse_utc, sha256_hex, to_us,
)

ROUNDS_COLLECTION = "03_data_ud_predict_btc5m_rounds"
KLINES_COLLECTION = "03_data_ud_binance_spot_klines_1s"
INGESTION_COLLECTION = "03_data_ud_history_ingestion"
MAX_BATCH = 5000
VALID_OUTCOMES = frozenset({"UP", "DOWN", "DRAW"})
ROUND_FIELDS = (
    "schema_version source series_slug round_id round_slug market_id condition_id "
    "published_at_us starts_at_us ends_at_us start_price end_price price_feed_provider "
    "price_feed_symbol category_status market_status trading_status settlement_state "
    "official_outcome resolution_evidence resolved_at_us first_observed_at "
    "start_price_observed_at label_observed_at"
).split()
KLINE_FIELDS = (
    "schema_version source market_type symbol interval open_time_us open high low close "
    "volume close_time_us close_exclusive_us quote_volume number_of_trades "
    "taker_buy_base_volume taker_buy_quote_volume ignore source_timestamp_unit source_row "
    "first_observed_at"
).split()


def _as_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    convert = getattr(value, "to_decimal", None)
    if callable(convert):
        value = convert()
    if not isinstance(value, (str, int, Decimal)) or isinstance(value, bool):
        raise HistoryError("INVALID_DOCUMENT", "expected exact Decimal")
    result = Decimal(value)
    if not result.is_finite():
        raise HistoryError("INVALID_DOCUMENT", "non-finite Decimal")
    return result


def _business(doc: Mapping[str, Any], dataset: str) -> dict[str, Any]:
    fields = ROUND_FIELDS if dataset == DATASET_ROUNDS else KLINE_FIELDS

    def strip_raw(value):
        if isinstance(value, Mapping):
            return {key: strip_raw(item) for key, item in value.items()
                    if key not in ("raw_ref", "raw_sha256")}
        if isinstance(value, list):
            return [strip_raw(item) for item in value]
        return value

    return {field: strip_raw(doc.get(field)) for field in fields}


def _update_digest(digest: Any, payload: Any) -> None:
    digest.update((canonical_json(payload) + "\n").encode("utf-8"))


def _observed(doc: dict[str, Any], field: str) -> int:
    value = ceil_ms_to_us(doc.get(field))
    if value is None:
        raise HistoryError("INVALID_DOCUMENT", f"missing {field}")
    return value


class Btc5mHistoryReader:
    """只读取注入的 UD 库；不连接网络、不写库、不建索引。

    每次查询有 10 秒驱动超时；内存只持有一页原始行、页摘要与日级统计。
    读取阶段扫描计算 manifest，输出阶段重新按页读取并核验实际内容。
    """

    def __init__(self, mongo_db: Any) -> None:
        if mongo_db is None:
            raise HistoryError("HISTORY_NOT_CONFIGURED", "database handle is required")
        self._db = mongo_db

    def read(
        self, start_utc: Any, end_utc: Any, *, warmup_seconds: int = 0,
        as_of_utc: Any, availability_mode: str = "observed", expected_manifest: Any = None,
    ) -> HistoryWindow:
        """返回带预先核算覆盖/manifest及三个延迟流的窗口；完整消费后须核验。"""
        request = HistoryRequest(
            start_utc=parse_utc(start_utc), end_utc=parse_utc(end_utc),
            as_of_utc=parse_utc(as_of_utc), warmup_seconds=warmup_seconds,
            availability_mode=availability_mode, expected_manifest=expected_manifest,
        )
        request.validate()
        states = self._states(request)
        snapshot = self._scan(request, states)

        def verify():
            # Re-read actual pages, but never rebuild coverage/DTOs/output hashes.
            self._assert_states(request, states)
            for dataset in (DATASET_ROUNDS, DATASET_KLINES):
                for page_record in self._pages(request, dataset, states, snapshot["pages"][dataset]):
                    del page_record
            self._assert_states(request, states)

        # End-of-read rescan also catches changes to an already visited page.
        verify()
        manifest = snapshot["manifest"]
        self._check_expected(request, manifest)
        window = HistoryWindow(
            request=request, status=snapshot["status"],
            sources=(SOURCE_ROUNDS, SOURCE_KLINES), kinds=(DATASET_ROUNDS, DATASET_KLINES),
            units={"time": "int64 UTC microseconds", "price": "Decimal"},
            schema_version=SCHEMA_VERSION, coverage=snapshot["coverage"],
            missing=snapshot["missing"], pending=snapshot["pending"],
            conflicts=snapshot["conflicts"],
            availability_assumptions=self._availability_assumptions(request),
            content_manifest=manifest, provenance_manifest=snapshot["provenance"],
            content_sha256=manifest["content_sha256"],
        )

        def stream(name):
            self._assert_states(request, states)
            datasets = (DATASET_ROUNDS, DATASET_KLINES) if name == "features" else (DATASET_ROUNDS,)
            for dataset in datasets:
                for page, _, _ in self._pages(
                    request, dataset, states, snapshot["pages"][dataset], project=True,
                ):
                    for doc in page:
                        for kind, row in self._rows(doc, dataset, request, states, name):
                            if kind == name:
                                yield row
                    del page
            verify()

        window._stream_factories = {
            name: (lambda name=name: stream(name)) for name in ("features", "metadata", "labels")
        }
        window._verify_snapshot = verify
        return window

    def _states(self, request: HistoryRequest, *, provenance: bool = False) -> list[dict[str, Any]]:
        first = from_us(request.read_start_us).date().isoformat()
        last = from_us(request.read_end_us - 1).date().isoformat()
        query = {"kind": "day", "dataset": {"$in": [DATASET_ROUNDS, DATASET_KLINES]},
                 "utc_date": {"$gte": first, "$lte": last}}
        result, after = [], None
        try:
            while True:
                current = query if after is None else {"$and": [query, {"_id": {"$gt": after}}]}
                with timeout(10):
                    page = list(self._db[INGESTION_COLLECTION].find(current).sort(
                        [("_id", 1)]).limit(min(MAX_BATCH, 5000)).batch_size(min(MAX_BATCH, 5000)))
                if not page:
                    return result
                for doc in page:
                    if doc.get("schema_version") != SCHEMA_VERSION:
                        raise HistoryError("UNKNOWN_SCHEMA_VERSION", "ingestion schema")
                    fields = (("_id", "raw_manifest_ref", "gap_manifest_ref") if provenance else (
                        "_id", "schema_version", "dataset", "utc_date", "state", "counts",
                        "window_start_us", "window_end_us", "content_sha256", "error_code",
                    ))
                    item = {key: doc.get(key) for key in fields}
                    if not provenance and isinstance(item.get("counts"), Mapping):
                        item["counts"] = {key: value for key, value in item["counts"].items()
                                          if key not in ("inserted", "matched_unchanged", "updated")}
                    result.append(item)
                # A fully consumed short page already exhausts this query. Later
                # assertions still issue a fresh query, including new boundary IDs.
                if len(page) < min(MAX_BATCH, 5000):
                    return result
                after = page[-1]["_id"]
        except HistoryError:
            raise
        except Exception:
            raise HistoryError("HISTORY_READ_FAILED", "checkpoint read failed") from None

    def _assert_states(self, request, states):
        if self._states(request) != states:
            raise HistoryError("DATASET_CHANGED", "ingestion shard state changed")

    def _pages(self, request, dataset, states, expected=None, *, project=False):
        rounds = dataset == DATASET_ROUNDS
        collection = ROUNDS_COLLECTION if rounds else KLINES_COLLECTION
        time_field = "starts_at_us" if rounds else "open_time_us"
        order = [(time_field, 1)] + ([("round_id", 1)] if rounds else [])
        query = ({"source": SOURCE_ROUNDS, "series_slug": SERIES_SLUG} if rounds else {
            "source": SOURCE_KLINES, "market_type": MARKET_TYPE, "symbol": SYMBOL,
            "interval": INTERVAL,
        })
        query[time_field] = {"$gte": request.read_start_us, "$lt": request.read_end_us}
        after, page_number = None, 0
        source = self._db[collection]
        # PyMongo can retain actual BSON bytes until a field is needed. Validation
        # passes hash every returned byte without decoding/re-encoding every row.
        # Injected mapping stores keep the same bounded, content-checked fallback.
        raw_bson = isinstance(source, Collection)
        decode_options = None
        if raw_bson:
            decode_options = source.codec_options.with_options(document_class=dict)
            source = source.with_options(codec_options=source.codec_options.with_options(
                document_class=RawBSONDocument))
        try:
            while True:
                self._assert_states(request, states)
                current = query
                if after is not None:
                    later = {time_field: {"$gt": after[0]}}
                    if rounds:
                        later = {"$or": [later, {time_field: after[0], "round_id": {"$gt": after[1]}}]}
                    current = {"$and": [query, later]}
                with timeout(10):
                    page = list(source.find(current, projection={"_id": 0}).sort(
                        order).limit(min(MAX_BATCH, 5000)).batch_size(min(MAX_BATCH, 5000)))
                self._assert_states(request, states)
                if not page:
                    if expected is not None and page_number != len(expected):
                        raise HistoryError("DATASET_CHANGED", "page count changed")
                    return
                # Content fingerprints include raw fields, never just identities.
                # Concatenated BSON documents are self-delimiting by their lengths.
                if raw_bson:
                    checksum = hashlib.sha256()
                    for doc in page:
                        checksum.update(doc.raw)
                    fingerprint = checksum.hexdigest()
                else:
                    fingerprint = hashlib.sha256(BSON.encode({"rows": page})).hexdigest()
                encoded = None
                changed = expected is None or (
                    page_number < len(expected) and fingerprint != expected[page_number][0]
                )
                if changed or project:
                    # Decimal128 conversion dominates projections and the same exact
                    # prices/zero volumes recur within a page. Reuse by BSON bytes,
                    # never float/value rounding, and discard the memo at this page.
                    decimals = {}
                    fields = ("start_price", "end_price") if rounds else (
                        "open", "high", "low", "close", "volume",
                        *( ("quote_volume", "taker_buy_base_volume", "taker_buy_quote_volume")
                           if changed else () ),
                    )
                    for index, doc in enumerate(page):
                        if raw_bson:
                            # Use the driver's normal decoder only on projected pages;
                            # RawBSONDocument.items() inflates every field in Python.
                            doc = page[index] = BSON(doc.raw).decode(codec_options=decode_options)
                        if doc.get("schema_version") != SCHEMA_VERSION:
                            raise HistoryError("UNKNOWN_SCHEMA_VERSION", "history row schema")
                        for field in fields:
                            value = doc.get(field)
                            if isinstance(value, Decimal128):
                                key = value.bid
                                if key not in decimals:
                                    decimals[key] = value.to_decimal()
                                doc[field] = decimals[key]
                    del decimals
                if changed:
                    encoded = [canonical_json(_business(doc, dataset)) for doc in page]
                    digest = sha256_hex("[" + ",".join(encoded) + "]")
                else:
                    digest = expected[page_number][1] if page_number < len(expected) else None
                if expected is not None and (
                    page_number >= len(expected) or digest != expected[page_number][1]
                ):
                    raise HistoryError("DATASET_CHANGED", "actual page digest changed")
                last = page[-1]
                next_after = (last[time_field], last.get("round_id") if rounds else None)
                if after is not None and next_after <= after:
                    raise HistoryError("INVALID_DOCUMENT", "keyset did not advance")
                yield page, encoded, (fingerprint, digest)
                # Release this page before the next database query.
                del page, encoded
                after, page_number = next_after, page_number + 1
        except HistoryError:
            raise
        except Exception:
            raise HistoryError("HISTORY_READ_FAILED", "bounded history read failed") from None

    def _rows(self, doc, dataset, request, states, name=None):
        as_of = to_us(request.as_of_utc)
        proxy = request.availability_mode == "event-time-proxy"
        rounds = dataset == DATASET_ROUNDS
        event = doc["starts_at_us" if rounds else "open_time_us"]
        common = dict(kind=dataset, source=SOURCE_ROUNDS if rounds else SOURCE_KLINES,
                      source_event_time_us=event, is_warmup=event < request.main_start_us)
        if not rounds:
            close = doc["close_exclusive_us"]
            available = close if proxy else max(close, _observed(doc, "first_observed_at"))
            if available <= as_of:
                yield "features", FeatureRow(
                    **common, available_at_us=available, open_time_us=event,
                    close_exclusive_us=close,
                    **{field: _as_decimal(doc[field]) for field in ("open", "high", "low", "close", "volume")},
                )
            return
        identity = (_identity_available_at(doc, request))
        if identity <= as_of and name in (None, "metadata"):
            yield "metadata", RoundMetadataRow(
                **common, available_at_us=identity, round_id=doc["round_id"],
                series_slug=doc["series_slug"], market_id=doc.get("market_id", ""),
                condition_id=doc.get("condition_id", ""), starts_at_us=event,
                ends_at_us=doc["ends_at_us"], published_at_us=doc.get("published_at_us"),
            )
        start = _start_price_available_at(doc, request)
        price = _as_decimal(doc.get("start_price"))
        if (name in (None, "features") and price is not None and price > 0
                and start is not None and start <= as_of):
            yield "features", FeatureRow(**common, available_at_us=start,
                                        round_id=doc["round_id"], start_price=price)
        label = _label_available_at(doc, request)
        day_conflict = any(item["dataset"] == DATASET_ROUNDS
                           and item["utc_date"] == from_us(event).date().isoformat()
                           and item["state"] == "conflict" for item in states)
        if (name in (None, "labels") and not day_conflict and self._qualified_label(doc)
                and label is not None and label <= as_of):
            yield "labels", LabelRow(
                **common, available_at_us=label, round_id=doc["round_id"],
                official_outcome=doc["official_outcome"], end_price=_as_decimal(doc["end_price"]),
                starts_at_us=event, ends_at_us=doc["ends_at_us"], resolved_at_us=doc["resolved_at_us"],
            )

    @staticmethod
    def _qualified_label(doc):
        start, end = _as_decimal(doc.get("start_price")), _as_decimal(doc.get("end_price"))
        return (doc.get("settlement_state") == "resolved" and doc.get("official_outcome") in VALID_OUTCOMES
                and doc.get("resolved_at_us") is not None and bool(doc.get("resolution_evidence"))
                and start is not None and start > 0 and end is not None and end > 0)

    def _scan(self, request, states):
        coverage = Coverage()
        missing, pending, conflicts = [], [], []
        pages, days, provenance = {}, {}, {}

        def add_gap(dataset, start, end):
            boundary = request.main_start_us
            if start < boundary < end:
                add_gap(dataset, start, boundary)
                add_gap(dataset, boundary, end)
            else:
                missing.append({"dataset": dataset, "start_us": start, "end_us": end,
                                "is_warmup": start < boundary})

        outputs = {name: hashlib.sha256() for name in ("features", "metadata", "labels")}
        for dataset in (DATASET_ROUNDS, DATASET_KLINES):
            pages[dataset] = []
            raw_digest = hashlib.sha256()
            raw_objects = {}
            previous_raw, raw_json = None, None
            step = 300_000_000 if dataset == DATASET_ROUNDS else 1_000_000
            next_slot = ((request.read_start_us + step - 1) // step) * step
            for page, encoded, identity in self._pages(request, dataset, states):
                pages[dataset].append(identity)
                for doc, business_json in zip(page, encoded):
                    event = doc["starts_at_us" if dataset == DATASET_ROUNDS else "open_time_us"]
                    day = from_us(event).date().isoformat()
                    day_key = dataset + "/" + day
                    day_hash = days.setdefault(day_key, hashlib.sha256())
                    day_hash.update((business_json + "\n").encode("utf-8"))
                    raw = {key: doc.get(key) for key in ("raw_ref", "raw_sha256")}
                    if raw != previous_raw:
                        raw_json = canonical_json(raw)
                        previous_raw = raw
                    raw_digest.update((raw_json + "\n").encode("utf-8"))
                    raw_objects[raw_json] = raw
                    per_day = coverage.per_day.setdefault(day_key, {"stored": 0, "eligible": 0})
                    coverage.stored_rows += 1
                    per_day["stored"] += 1
                    if event > next_slot:
                        add_gap(dataset, next_slot, event)
                    if event < next_slot or event % step:
                        conflicts.append({"dataset": dataset, "event_us": event, "reason": "OVERLAP_OR_OFF_GRID"})
                    next_slot = max(next_slot, event + step)
                    eligible = False
                    for name, row in self._rows(doc, dataset, request, states):
                        # Frozen DTOs contain only scalar fields; avoid deep-copying
                        # every Decimal merely to serialize the same payload.
                        _update_digest(outputs[name], vars(row))
                        eligible = True
                        if name == "features":
                            if row.is_warmup:
                                coverage.warmup_rows += 1
                            else:
                                coverage.main_window_rows += 1
                    coverage.eligible_rows += int(eligible)
                    per_day["eligible"] += int(eligible)
                    if dataset == DATASET_ROUNDS:
                        start_available = _start_price_available_at(doc, request)
                        if (doc.get("start_price") is None or start_available is None
                                or start_available > to_us(request.as_of_utc)):
                            pending.append({"dataset": dataset, "round_id": doc["round_id"],
                                            "reason": "START_PRICE_NOT_AVAILABLE_AT_AS_OF"})
                        label = _label_available_at(doc, request)
                        state = doc.get("settlement_state")
                        if not self._qualified_label(doc) or label is None or label > to_us(request.as_of_utc):
                            reason = "LABEL_NOT_AVAILABLE_AT_AS_OF" if self._qualified_label(doc) else str(state).upper()
                            target = conflicts if state == "conflict" else pending
                            target.append({"dataset": dataset, "round_id": doc["round_id"], "reason": reason})
                del page, encoded
            if next_slot < request.read_end_us:
                add_gap(dataset, next_slot, request.read_end_us)
            provenance[dataset] = {
                "raw_references_sha256": raw_digest.hexdigest(),
                "raw_objects": [raw_objects[key] for key in sorted(raw_objects)],
            }
        provenance["shards"] = self._states(request, provenance=True)
        self._assert_states(request, states)
        # Missing/non-complete checkpoints never certify an otherwise populated window.
        first_day = from_us(request.read_start_us).date()
        last_day = from_us(request.read_end_us - 1).date()
        from datetime import timedelta

        day = first_day
        while day <= last_day:
            for dataset in (DATASET_ROUNDS, DATASET_KLINES):
                state = next((item for item in states if item["dataset"] == dataset
                              and item["utc_date"] == day.isoformat()), None)
                if state is None or state["state"] != "complete" or not state["content_sha256"]:
                    missing.append({"dataset": dataset, "utc_date": day.isoformat(), "reason": "SHARD_UNKNOWN_OR_PARTIAL"})
            day += timedelta(days=1)
        manifest = {
            "manifest_version": CONTENT_MANIFEST_VERSION, "schema_version": SCHEMA_VERSION,
            "projection_version": 1, "datasets": [DATASET_ROUNDS, DATASET_KLINES],
            "window": {"start_us": request.main_start_us, "end_us": request.main_end_us,
                       "read_start_us": request.read_start_us, "read_end_us": request.read_end_us,
                       "warmup_seconds": request.warmup_seconds},
            "as_of_us": to_us(request.as_of_utc), "availability_mode": request.availability_mode,
            "ordering": {DATASET_ROUNDS: ["starts_at_us", "round_id"], DATASET_KLINES: ["open_time_us"]},
            "expected_seconds": (request.read_end_us - 1) // 1_000_000 - (request.read_start_us - 1) // 1_000_000,
            "stored_daily_sha256": {key: value.hexdigest() for key, value in sorted(days.items())},
            "shards": states, "coverage": asdict(coverage),
            "gap": {"missing": missing, "pending": pending, "conflicts": conflicts},
            "output_sha256": sha256_hex(canonical_json({name: digest.hexdigest() for name, digest in outputs.items()})),
        }
        manifest["content_sha256"] = sha256_hex(canonical_json(manifest))
        return dict(manifest=manifest, coverage=coverage, missing=missing, pending=pending,
                    conflicts=conflicts, pages=pages, provenance=provenance,
                    status="partial" if missing or pending or conflicts or coverage.eligible_rows < coverage.stored_rows else "complete")

    @staticmethod
    def _check_expected(request, manifest):
        expected = request.expected_manifest
        if expected is None:
            return
        if isinstance(expected, str):
            same = expected == manifest["content_sha256"]
        else:
            same = all(expected.get(key) == manifest.get(key) for key in (
                "window", "availability_mode", "datasets", "as_of_us", "content_sha256",
            ))
        if not same:
            raise HistoryError("DATASET_CHANGED", "expected content manifest differs")

    @staticmethod
    def _availability_assumptions(request):
        return ["available_at_us <= as_of_utc is enforced per row",
                "warmup window is reported separately from the main window",
                ("event-time-proxy: theoretical availability, NOT strict point-in-time / live parity"
                 if request.availability_mode == "event-time-proxy" else
                 "observed: historical backfill may leave earlier backtest points empty"),
                *[f"{key} -> {value}" for key, value in sorted(AVAILABILITY_RULES.items())]]


def _identity_available_at(doc, request):
    published = doc.get("published_at_us")
    if request.availability_mode == "event-time-proxy" and published is not None:
        return int(published)
    return max(_observed(doc, "first_observed_at"), published or 0)


def _start_price_available_at(doc, request):
    if request.availability_mode == "event-time-proxy":
        return doc["starts_at_us"]
    observed = ceil_ms_to_us(doc.get("start_price_observed_at"))
    return max(doc["starts_at_us"], observed) if observed is not None else None


def _label_available_at(doc, request):
    resolved = doc.get("resolved_at_us")
    if resolved is None:
        return None
    available = max(doc["ends_at_us"], resolved)
    if request.availability_mode == "observed":
        observed = ceil_ms_to_us(doc.get("label_observed_at"))
        if observed is None:
            return None
        available = max(available, observed)
    return available


__all__ = ["Btc5mHistoryReader", "INGESTION_COLLECTION", "KLINES_COLLECTION", "MAX_BATCH",
           "ROUNDS_COLLECTION", "VALID_OUTCOMES"]
