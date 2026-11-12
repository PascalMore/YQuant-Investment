"""BTC5m facade-only, bounded history consumption with isolated official labels."""
from __future__ import annotations

from dataclasses import dataclass, field
import pickle
import sqlite3
import tempfile
from typing import Any, Iterator

from skills.data.unified_data.history_types import DATASET_ROUNDS, HistoryError, HistoryRequest

KIND_TRADE_KLINE_OHLC = "trade_kline_ohlc"
SOURCE_BINANCE_VISION = "binance-vision"
SOURCE_PREDICT = "predict.fun"
NUMERIC_CONVERSION = "decimal_to_float_single_pass"


@dataclass
class HistoryInput:
    """One research event; Decimal payload and availability remain unchanged."""

    kind: str
    source: str
    source_event_time_us: int
    available_at_us: int
    is_warmup: bool
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class HistoryInputBundle:
    """Single-pass lazy streams; verification is explicit and never inferred from creation."""

    _window: Any = field(repr=False)
    content_manifest: dict[str, Any] = field(default_factory=dict)
    content_sha256: str | None = None
    numeric_conversion: str | None = None
    numeric_precision_note: str | None = None
    availability_assumptions: list[str] = field(default_factory=list)
    verified: bool = False
    features: Iterator[HistoryInput] = field(init=False)
    metadata: Iterator[HistoryInput] = field(init=False)
    labels: Iterator[HistoryInput] = field(init=False)
    _completed: set[str] = field(default_factory=set, init=False, repr=False)
    _schedule_incomplete: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        self.features = self._iterate("features", self._window.iter_features())
        self.metadata = self._iterate("metadata", self._window.iter_round_metadata())
        self.labels = self._iterate("labels", self._window.iter_labels())

    def _iterate(self, name: str, rows: Iterator[Any]) -> Iterator[HistoryInput]:
        for row in rows:
            if name == "features":
                payload = {key: getattr(row, key) for key in (
                    "open_time_us", "open", "high", "low", "close", "volume",
                    "close_exclusive_us",
                )}
                payload["dataset"] = row.kind
                if row.round_id is not None:
                    payload.update(round_id=row.round_id, start_price=row.start_price)
                kind = KIND_TRADE_KLINE_OHLC
            elif name == "metadata":
                payload = {key: getattr(row, key) for key in (
                    "round_id", "series_slug", "market_id", "condition_id",
                    "starts_at_us", "ends_at_us", "published_at_us",
                )}
                payload["dataset"] = DATASET_ROUNDS
                kind = "round_identity"
            else:
                payload = {key: getattr(row, key) for key in (
                    "round_id", "official_outcome", "end_price", "starts_at_us",
                    "ends_at_us", "resolved_at_us",
                )}
                payload["dataset"] = DATASET_ROUNDS
                kind = "official_outcome"
            yield HistoryInput(kind, row.source, row.source_event_time_us,
                               row.available_at_us, row.is_warmup, payload)
        self._completed.add(name)

    def iter_features(self) -> Iterator[HistoryInput]:
        """Return the single-pass feature stream, without labels."""
        return self.features

    def iter_metadata(self) -> Iterator[HistoryInput]:
        """Return the single-pass identity stream."""
        return self.metadata

    def iter_labels(self) -> Iterator[HistoryInput]:
        """Return the independent single-pass official label stream."""
        return self.labels

    def iter_scheduled(self) -> Iterator[HistoryInput]:
        """Merge feature/metadata by availability, using bounded local disk sorting.

        Facade streams are ordered by event keys, not observation times. Sorting
        in a temporary SQLite file avoids a whole-window Python list and remains
        correct when a late observation reverses event order. Labels never enter
        this schedule. Pickles are exclusively written/read here, never imported
        from raw files or caller-controlled paths. Closing the iterator cleans up.
        """
        self._schedule_incomplete = True
        with tempfile.TemporaryDirectory(prefix="btc5m-schedule-") as directory:
            with sqlite3.connect(f"{directory}/schedule.sqlite") as connection:
                connection.execute("PRAGMA temp_store=FILE")
                connection.execute("PRAGMA cache_size=-2048")
                connection.execute(
                    "CREATE TABLE events (available INTEGER, sequence INTEGER, payload BLOB)"
                )
                sequence = 0
                for stream in (self.features, self.metadata):
                    for row in stream:
                        connection.execute("INSERT INTO events VALUES (?, ?, ?)", (
                            row.available_at_us, sequence, pickle.dumps(row),
                        ))
                        sequence += 1
                        if sequence % 5000 == 0:
                            connection.commit()
                connection.commit()
                for (payload,) in connection.execute(
                    "SELECT payload FROM events ORDER BY available, sequence"
                ):
                    yield pickle.loads(payload)
        self._schedule_incomplete = False

    def verify_consumed(self) -> str:
        """Verify all exhausted streams and the final facade snapshot; propagate errors."""
        self.verified = False
        if self._schedule_incomplete or self._completed != {"features", "metadata", "labels"}:
            raise HistoryError("INCOMPLETE_CONSUMPTION", "consume all three streams first")
        digest = self._window.verify_consumed()
        self.content_sha256 = digest
        self.verified = True
        return digest


def iter_history_input(client: Any, request: HistoryRequest) -> HistoryInputBundle:
    """Open the facade window without consuming or materializing any output stream."""
    window = client.read_btc5m_history(
        request.start_utc, request.end_utc, warmup_seconds=request.warmup_seconds,
        as_of_utc=request.as_of_utc, availability_mode=request.availability_mode,
        expected_manifest=request.expected_manifest,
    )
    return HistoryInputBundle(
        _window=window, content_manifest=dict(window.content_manifest),
        content_sha256=window.content_sha256,
        availability_assumptions=list(window.availability_assumptions),
    )


__all__ = [
    "KIND_TRADE_KLINE_OHLC", "NUMERIC_CONVERSION", "SOURCE_BINANCE_VISION",
    "SOURCE_PREDICT", "HistoryInput", "HistoryInputBundle", "iter_history_input",
]
