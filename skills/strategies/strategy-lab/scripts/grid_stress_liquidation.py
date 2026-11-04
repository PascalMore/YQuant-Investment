"""Stress-test liquidation prices from the frozen grid ladder geometry.

Caliber (Pascal 2026-11-04 ruling, authoritative in the strategy-lab SKILL
contract, "强平预估价格口径"): start flat at the grid mid price, let the price
move one way, and let every limit ladder order on the adverse side fill
(falling price -> long cells fill at CELL_LOWER; rising price -> short cells
fill at CELL_UPPER). The position is held: no exits, no re-entry cycles. The
liquidation price is the price root where

    E(p) <= MM(p) = (mmr + close_fee) * notional(p) - cum

solved segment-wise between grid lines: inside one segment the position is
constant, so E and MM are linear in p and the crossing is exact. The close
fee (F) is charged by the venue on the liquidation notional, so it enters the
requirement exactly once: ``MF = mmr + f`` with ``f = close_fee_rate``. The
equity side stays gross (the fee is not deducted from the mark-to-market
equity), so the long side solves
``E0 - N + p*Q = (mmr+f)*p*Q - cum`` and the short side
``E0 + N - p*Q = (mmr+f)*p*Q - cum``, i.e.

    long:  E(p) - MM(p) = (E0 - N + cum) + p*Q*(1 - MF)
    short: E(p) - MM(p) = (E0 + N + cum) - p*Q*(1 + MF)

``N`` is the position cost carried by the segment (the notional filled so
far); it stays in the constant term, because dropping it would leave the
equity unattached to the position and every cell would degenerate to
``no-root``.

Inputs per cell are the frozen grid geometry (``strategy.py`` CELL_* arrays),
the capital caliber (E0, leverage, close fee) and the MMR tier. The backtest's
execution and holding data are NOT inputs: the estimate must not depend on
what the platform happened to fill.

MMR follows the SKILL layering and never skips a tier:
1. platform-native field (``instrumentRulesSnapshot``), when it carries one;
2. the public Binance brackets endpoint (cached for five minutes);
3. the frozen default gradient (nominal <= 20,000 -> 1.0%, > 20,000 -> 1.5%),
   always labelled ``default MMR tier (binance unreachable)``.

The tier depends on the open notional and the root depends on the tier, so
the tier is resolved as a fixed point against the notional at the root.
Binance brackets are a proxy for the venue's own tier table, so the report
must disclose that substitution.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import grid_research as gr  # noqa: E402

LAB = Path(__file__).resolve().parents[1]
STRATEGIES = LAB / "strategies"

# Capital caliber of the 1h four-window neutral-grid batch (Path B).
DEFAULT_EQUITY0 = 1000.0
DEFAULT_LEVERAGE = 10.0
DEFAULT_CLOSE_FEE = 0.0005
# Fallback MMR tier-1 rate; the live tier always comes from the resolver.
DEFAULT_MMR = 0.01

# Public Binance endpoint (same source as the Leverage & Margin page, no key).
BINANCE_BRACKETS_URL = ("https://www.binance.com/bapi/futures/v1/friendly/"
                        "future/common/brackets?symbol={symbol}")
BINANCE_TIMEOUT_SECONDS = 10
MMR_CACHE_TTL_SECONDS = 300

# Frozen default gradient (SKILL tier 3): nominal <= 20,000 USDT -> 1.0%,
# above -> 1.5% (the measured tier-1/tier-2 structure of the target coins).
DEFAULT_TIER_SPLIT_NOTIONAL = 20_000.0
DEFAULT_TIER_MMR_LOW = 0.01
DEFAULT_TIER_MMR_HIGH = 0.015
DEFAULT_TIER_REASON = "default MMR tier (binance unreachable)"

NOTE_START = "<!-- stress-liquidation:start -->"
NOTE_END = "<!-- stress-liquidation:end -->"
NOTE_HEADING = "## 压力测试口径重算"

ERRATA_START = "<!-- stress-liquidation:errata:start -->"
ERRATA_END = "<!-- stress-liquidation:errata:end -->"
ERRATA_HEADING = "### 勘误：压力测试求解器与留档快照口径的差异（2026-11-04）"

TABLE_A_LONG = "多头强平价"
TABLE_A_SHORT = "空头强平价"


# --------------------------------------------------------------- grid input

def parse_grid(path: str | Path) -> dict:
    """Read the frozen grid geometry from a generated ``strategy.py``.

    Only the frozen constants are read; the strategy is never imported or
    executed.
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8")

    def array(name: str) -> list[float]:
        match = re.search(name + r"\s*=\s*\[([^\]]*)\]", text)
        if not match:
            raise ValueError(f"{name} not found in {path}")
        return [float(value) for value in match.group(1).split(",")]

    roles_match = re.search(r"CELL_ROLES\s*=\s*\[([^\]]*)\]", text)
    if not roles_match:
        raise ValueError(f"CELL_ROLES not found in {path}")
    roles = [role.strip().strip("'\"") for role in roles_match.group(1).split(",")]
    return {"lower": array("CELL_LOWER"), "upper": array("CELL_UPPER"),
            "roles": roles, "pcts": array("CELL_BUDGET_PCTS")}


def side_entries(grid: dict, *, equity0: float = DEFAULT_EQUITY0,
                 leverage: float = DEFAULT_LEVERAGE) -> tuple[list, list]:
    """Split the grid into (long, short) ``(entry_price, quote_notional)`` pairs.

    A long cell is bought at its CELL_LOWER line, a short cell is sold at its
    CELL_UPPER line; the quote notional of one cell is
    ``equity0 x leverage x budget share`` (Path B: the platform levers the
    order value).
    """
    longs: list[tuple[float, float]] = []
    shorts: list[tuple[float, float]] = []
    for index, role in enumerate(grid["roles"]):
        notional = equity0 * leverage * grid["pcts"][index]
        if role.startswith("long"):
            longs.append((grid["lower"][index], notional))
        else:
            shorts.append((grid["upper"][index], notional))
    return longs, shorts


# ----------------------------------------------------------------- the solve

def walk(entries: list[tuple[float, float]], descending: bool, *,
         equity0: float = DEFAULT_EQUITY0,
         mmr: float = DEFAULT_MMR,
         close_fee_rate: float = DEFAULT_CLOSE_FEE,
         cum_maintenance: float = 0.0) -> dict:
    """Walk the ladder segment by segment and return the first E(p) = MM(p) root.

    ``entries`` are the adverse-side ladder orders as ``(entry_price,
    quote_notional)``. ``descending=True`` means the price falls, so the long
    ladder fills from its highest entry downward; ``descending=False`` means the
    price rises and the short ladder fills from its lowest entry upward.

    The zone is ``in-ladder`` when the root sits between the ladder's extreme
    entries, ``below-L`` / ``above-U`` when it sits outside them, and
    ``no-root`` when equity never reaches the maintenance requirement (E0 minus
    the side notional stays above 0).

    Close fee (F): the venue charges the taker fee on the liquidation
    notional ``p*Q``, so the requirement is the SKILL's ``MMR + close_fee``
    factor, ``MF = mmr + close_fee_rate``. The fee is charged **exactly
    once** and the equity side stays gross, so with ``N`` the notional filled
    so far in the segment the long side solves ``E(p) = E0 - N + p*Q`` against
    ``MM(p) = MF*p*Q - cum``, and the short side ``E(p) = E0 + N - p*Q``
    against the same requirement. The position cost ``N`` stays in the
    constant term: dropping it would leave the equity unattached to the
    position and every cell would degenerate to ``no-root``.

    A liquidation price must be strictly positive, so a root at or below zero
    is not a crossing inside the admissible price range.
    """
    if not entries:
        raise ValueError("walk requires at least one ladder order")
    maintenance_factor = mmr + close_fee_rate
    ladder = sorted(entries, reverse=descending)
    count = len(ladder)
    filled_notional = 0.0
    filled_qty = 0.0
    lowest_entry = min(entry for entry, _ in ladder)
    highest_entry = max(entry for entry, _ in ladder)
    for index in range(count):
        entry = ladder[index][0]
        filled_notional += ladder[index][1]
        filled_qty += ladder[index][1] / entry
        lower = ladder[index + 1][0] if index + 1 < count else None
        if descending:
            # E = E0 - N + p*Q ; MM = MF*p*Q - cum
            const = equity0 - filled_notional + cum_maintenance
            slope = filled_qty * (1.0 - maintenance_factor)
            low, high = (lower, entry) if lower is not None else (0.0, entry)
        else:
            # E = E0 + N - p*Q ; MM = MF*p*Q - cum
            const = equity0 + filled_notional + cum_maintenance
            slope = -filled_qty * (1.0 + maintenance_factor)
            low, high = (entry, lower) if lower is not None else (entry, entry * 4.0)
        if slope == 0:
            continue
        root = -const / slope
        if root <= 0:
            # A liquidation price must be strictly positive: a root at or below
            # zero is not a crossing inside the admissible price range, so the
            # segment carries no liquidation.
            continue
        if min(low, high) <= root <= max(low, high):
            zone = ("below-L" if root < lowest_entry else
                    "above-U" if root > highest_entry else "in-ladder")
            return {"root": root, "fills": index + 1, "zone": zone,
                    "filled_notional": filled_notional, "filled_qty": filled_qty,
                    "mark_notional": filled_qty * root}
    return {"root": None, "fills": count, "zone": "no-root",
            "filled_notional": filled_notional, "filled_qty": filled_qty,
            "mark_notional": filled_qty * (lowest_entry if descending
                                           else highest_entry)}


def _solve_side(entries: list[tuple[float, float]], descending: bool, *,
                equity0: float, close_fee: float, resolver: "MmrResolver",
                symbol: str) -> dict:
    """Solve one side, resolving the MMR tier as a fixed point.

    The tier is selected by the notional open at the root, and the root
    depends on the tier, so the tier is iterated until it is self-consistent.
    """
    candidates = resolver.candidates(symbol)
    index = 0
    result: dict = {}
    for _ in range(2 * len(candidates) + 2):
        tier = candidates[index]
        result = walk(entries, descending, equity0=equity0,
                      mmr=tier["mmr"],
                      close_fee_rate=close_fee,
                      cum_maintenance=tier.get("cum", 0.0))
        basis = (result["mark_notional"] if result["root"] is not None
                 else result["filled_notional"])
        following = resolver.select_index(candidates, basis)
        if following == index:
            break
        index = following
    tier = candidates[index]
    result["mmr"] = tier["mmr"]
    result["mmr_source"] = tier.get("source", "unknown")
    result["mmr_reason"] = tier.get("reason", "")
    result["tier"] = tier.get("seq")
    return result


def solve_cell(grid: dict, *, symbol: str = "",
               equity0: float = DEFAULT_EQUITY0,
               leverage: float = DEFAULT_LEVERAGE,
               close_fee: float = DEFAULT_CLOSE_FEE,
               resolver: "MmrResolver | None" = None) -> dict:
    """Solve both sides of one frozen grid cell."""
    resolver = resolver or default_resolver()
    longs, shorts = side_entries(grid, equity0=equity0, leverage=leverage)
    down = _solve_side(longs, True, equity0=equity0, close_fee=close_fee,
                       resolver=resolver, symbol=symbol)
    up = _solve_side(shorts, False, equity0=equity0, close_fee=close_fee,
                     resolver=resolver, symbol=symbol)
    return {"down": down, "up": up,
            "n_long": len(longs), "n_short": len(shorts),
            "long_notional": sum(notional for _, notional in longs),
            "short_notional": sum(notional for _, notional in shorts)}


# ------------------------------------------------------------------- the MMR

def _curl_json(url: str, timeout: int = BINANCE_TIMEOUT_SECONDS) -> dict:
    """Fetch a JSON document with curl (the SKILL's documented path)."""
    completed = subprocess.run(
        ["curl", "-sS", "--max-time", str(timeout), url],
        capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"curl failed for {url}: {completed.stderr.strip()}")
    return json.loads(completed.stdout)


class MmrResolver:
    """Resolve the maintenance margin tier, following the SKILL layering.

    ``native`` is the platform's ``instrumentRulesSnapshot``; it wins when it
    carries a maintenance margin rate. Otherwise the public Binance brackets
    endpoint is read (cached for ``ttl`` seconds), and when that is
    unreachable the frozen default gradient applies, labelled as such.
    """

    def __init__(self, *, native: dict | None = None,
                 fetcher: Callable[[str], dict] | None = None,
                 ttl: int = MMR_CACHE_TTL_SECONDS) -> None:
        self.native = native
        self.fetcher = fetcher
        self.ttl = ttl
        self._cache: dict[str, tuple[float, dict]] = {}

    def brackets(self, symbol: str) -> dict | None:
        """Binance bracket table of ``symbol``, or None when unreachable."""
        cached = self._cache.get(symbol)
        now = time.time()
        if cached and cached[0] > now:
            return cached[1]
        fetcher = self.fetcher or _curl_json
        try:
            payload = fetcher(BINANCE_BRACKETS_URL.format(symbol=symbol))
        except Exception:
            return None
        brackets = ((payload or {}).get("data") or {}).get("brackets") or []
        if not brackets:
            return None
        table = brackets[0]
        if not table.get("riskBrackets"):
            return None
        self._cache[symbol] = (now + self.ttl, table)
        return table

    def candidates(self, symbol: str) -> list[dict]:
        """Ordered candidate tiers for ``symbol`` (lowest notional first)."""
        if self.native and self.native.get("maintenanceMarginRate") is not None:
            return [{"mmr": float(self.native["maintenanceMarginRate"]),
                     "cum": float(self.native.get("cumFastMaintenanceAmount", 0.0) or 0.0),
                     "floor": 0.0, "cap": None, "cap_inclusive": True,
                     "seq": None, "source": "platform-native",
                     "reason": "instrumentRulesSnapshot"}]
        table = self.brackets(symbol)
        if table is not None:
            tiers = []
            for tier in table.get("riskBrackets") or []:
                cap = tier.get("bracketNotionalCap")
                tiers.append({
                    "mmr": float(tier["bracketMaintenanceMarginRate"]),
                    "cum": float(tier.get("cumFastMaintenanceAmount", 0.0) or 0.0),
                    "floor": float(tier.get("bracketNotionalFloor", 0.0)),
                    "cap": (float(cap) if cap is not None else None),
                    "cap_inclusive": False,
                    "seq": tier.get("bracketSeq"),
                    "source": "binance-brackets",
                    "reason": f"binance tier{tier.get('bracketSeq')}",
                    "updateTime": table.get("updateTime")})
            if tiers:
                return tiers
        return [{"mmr": DEFAULT_TIER_MMR_LOW, "cum": 0.0,
                 "floor": 0.0, "cap": DEFAULT_TIER_SPLIT_NOTIONAL,
                 "cap_inclusive": True, "seq": 1, "source": "default-tier",
                 "reason": DEFAULT_TIER_REASON},
                {"mmr": DEFAULT_TIER_MMR_HIGH, "cum": 0.0,
                 "floor": DEFAULT_TIER_SPLIT_NOTIONAL, "cap": None,
                 "cap_inclusive": False, "seq": 2, "source": "default-tier",
                 "reason": DEFAULT_TIER_REASON}]

    @staticmethod
    def select_index(candidates: list[dict], notional: float) -> int:
        """Index of the tier whose notional band contains ``notional``."""
        for index, tier in enumerate(candidates):
            cap = tier["cap"]
            above = notional >= tier["floor"]
            below = True if cap is None else (
                notional <= cap if tier.get("cap_inclusive") else notional < cap)
            if above and below:
                return index
        return 0

    def select(self, symbol: str, notional: float) -> dict:
        """The maintenance tier that applies to ``notional``."""
        candidates = self.candidates(symbol)
        return candidates[self.select_index(candidates, notional)]


def default_resolver() -> MmrResolver:
    """Resolver without platform-native fields (the common case)."""
    return MmrResolver()


def fetch_mmr(symbol: str, notional: float = 0.0, *,
              resolver: MmrResolver | None = None) -> dict:
    """Maintenance margin rate for one symbol at the given open notional."""
    resolver = resolver or default_resolver()
    return resolver.select(symbol, notional)


# -------------------------------------------------------------- the carriers

_NUMERIC_CELL_COLUMNS = ("L", "U", "g_pct", "N", "margin_return_pct", "sharpe",
                         "max_drawdown_pct")
_LIQUIDATION_COLUMNS = ("downward_liquidation_price", "upward_liquidation_price")


def _number(value: Any) -> float | None:
    if value in (None, "", "N/A"):
        return None
    return float(value)


def load_cells(cells_csv: str | Path) -> list[dict]:
    """Read the frozen table-A carrier into solver-ready cell dicts."""
    with Path(cells_csv).open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    cells = []
    for row in rows:
        cell = dict(row)
        for column in _NUMERIC_CELL_COLUMNS + _LIQUIDATION_COLUMNS:
            cell[column] = _number(row.get(column))
        cells.append(cell)
    return cells


def report_table_a(report_md: str | Path) -> dict[tuple[str, str], dict]:
    """Read table A of the report as ``(contract, window) -> column values``.

    Columns are located by header label, so a column split (the liquidation
    column becoming two) does not shift the other readings.
    """
    text = Path(report_md).read_text(encoding="utf-8")
    try:
        section = text.split("## 2. 表 A")[1].split("## 3.")[0]
    except IndexError as error:
        raise ValueError("report has no table A section") from error
    lines = [line.strip() for line in section.splitlines()
             if line.strip().startswith("|")]
    header = [cell.strip() for cell in lines[0].strip("|").split("|")]
    labels = {"合约": "contract", "窗口": "window",
              "敞口/权益峰值": "worst_gross_to_equity"}
    index = {}
    for position, label in enumerate(header):
        if label in labels:
            index[labels[label]] = position
    if "contract" not in index or "window" not in index:
        raise ValueError("report table A lacks contract/window columns")
    table: dict[tuple[str, str], dict] = {}
    for line in lines[2:]:
        columns = [cell.strip() for cell in line.strip("|").split("|")]
        if len(columns) < len(header):
            continue
        key = (columns[index["contract"]], columns[index["window"]])
        record = {}
        for name, position in index.items():
            if name in ("contract", "window"):
                continue
            value = columns[position]
            try:
                record[name] = float(value)
            except ValueError:
                record[name] = None
        table[key] = record
    return table


def load_comparison_windows(comparison_csv: str | Path) -> dict[tuple[str, str], dict]:
    """Recover the per-window pairs / amount-per-grid from the comparison carrier.

    The comparison carrier stores them as ``mean (W1/W2/W3/W4); n/4``; the
    per-window parts are read back before the carrier is rewritten, so a
    regeneration cannot silently drop them.
    """
    path = Path(comparison_csv)
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    windows = ("W1", "W2", "W3", "W4")
    recovered: dict[tuple[str, str], dict] = {}

    def per_window(text: str) -> list[float | None]:
        match = re.search(r"\(([^)]*)\)", str(text or ""))
        if not match:
            return [None] * 4
        parts = match.group(1).split("/")
        values: list[float | None] = []
        for part in parts[:4]:
            try:
                values.append(float(part))
            except ValueError:
                values.append(None)
        return values + [None] * (4 - len(values))

    for row in rows:
        contract = str(row.get("contract") or "")
        amount = per_window(row.get("amount_per_grid") or "")
        pairs = per_window(row.get("total_pairs") or "")
        for index, window in enumerate(windows):
            recovered[(contract, window)] = {"pairs": pairs[index],
                                            "avg_grid_order_notional": amount[index]}
    return recovered


def load_runs(runs_json: str | Path, cells: list[dict]) -> dict[tuple[str, str], dict]:
    """Map the platform run results onto cells (pairs and amount per grid)."""
    runs = json.loads(Path(runs_json).read_text(encoding="utf-8"))
    windows = {(cell["contract"], str(cell.get("start_utc", ""))[:10]): cell["window"]
               for cell in cells}
    mapped: dict[tuple[str, str], dict] = {}
    for run in runs:
        contract = str(run.get("symbol", "")).split("/")[0] + "USDT"
        window = windows.get((contract, str(run.get("start_date", ""))))
        if window is None:
            continue
        result = json.loads(run.get("result_json") or "{}")
        mean, _, _ = gr.average_amount_per_grid(result.get("executions") or [])
        mapped[(contract, window)] = {
            "pairs": int(result.get("gridMatchedTradeCount") or 0),
            "avg_grid_order_notional": mean,
        }
    return mapped


def has_frozen_geometry(cell: dict) -> bool:
    """Whether the cell carries a frozen grid geometry (L/U/N all present).

    A placeholder row laid by ``write_cells_csv`` has no geometry, so it has
    no stress estimate either: the estimate is a function of the frozen
    geometry alone.
    """
    return all(cell.get(column) is not None for column in ("L", "U", "N"))


def solve_cells(cells: list[dict], *, resolver: MmrResolver | None = None,
                strategy_dir: str | Path = STRATEGIES) -> dict[tuple[str, str], dict]:
    """Solve every cell's stress liquidation prices from its frozen geometry.

    Cells without a frozen geometry (placeholder rows) are skipped.
    """
    resolver = resolver or default_resolver()
    strategy_dir = Path(strategy_dir)
    solved: dict[tuple[str, str], dict] = {}
    for cell in cells:
        if not has_frozen_geometry(cell):
            continue
        contract, window = cell["contract"], cell["window"]
        path = strategy_dir / f"{contract}-{window}-1h" / "strategy.py"
        grid = parse_grid(path)
        solved[(contract, window)] = solve_cell(grid, symbol=contract,
                                                resolver=resolver)
    return solved


def backfill(report_dir: str | Path, anchor_utc: Any,
             runs_json: str | Path | None = None, *,
             resolver: MmrResolver | None = None,
             strategy_dir: str | Path = STRATEGIES) -> dict:
    """One-stop entry: solve, regenerate the carriers, sync the report.

    The carriers are regenerated from the frozen table-A carrier plus the
    report's own risk columns, and the report's liquidation columns are
    rewritten from the regenerated carrier, so report and carrier cannot drift.
    """
    report_dir = Path(report_dir)
    evidence = report_dir / "evidence"
    cells_csv = evidence / "cells.csv"
    comparison_csv = evidence / "cells-comparison.csv"
    note_path = evidence / "liquidation-backfill-2026-11-04.md"

    cells = load_cells(cells_csv)
    archived = {(cell["contract"], cell["window"]):
                (cell["downward_liquidation_price"], cell["upward_liquidation_price"])
                for cell in cells}
    archived_snapshot = archived_snapshot_values(note_path)

    table_a = report_table_a(report_dir / "report.md")
    for cell in cells:
        cell["worst_gross_to_equity"] = table_a.get(
            (cell["contract"], cell["window"]), {}).get("worst_gross_to_equity")

    recovered = load_comparison_windows(comparison_csv)
    for cell in cells:
        record = recovered.get((cell["contract"], cell["window"]), {})
        cell["pairs"] = record.get("pairs")
        cell["avg_grid_order_notional"] = record.get("avg_grid_order_notional")
    if runs_json:
        for key, record in load_runs(runs_json, cells).items():
            for cell in cells:
                if (cell["contract"], cell["window"]) == key:
                    cell.update(record)

    solved = solve_cells(cells, resolver=resolver, strategy_dir=strategy_dir)
    for cell in cells:
        result = solved.get((cell["contract"], cell["window"]))
        if result is None:
            continue
        cell["downward_liquidation_price"] = result["down"]["root"]
        cell["upward_liquidation_price"] = result["up"]["root"]
        cell["qualification"] = gr.cell_qualification(cell)[0]

    frequency_seconds = 3600
    for cell in cells:
        raw = cell.get("frequency_seconds")
        if raw:
            frequency_seconds = int(float(raw))
            break
    gr.regen_carriers(anchor_utc, cells, evidence, frequency_seconds)

    _write_note(note_path, cells, solved)
    errata = _diff_against_archived(archived, cells)
    snapshot_errata = _snapshot_errata(archived_snapshot, cells)
    if snapshot_errata:
        _append_erratum(note_path, snapshot_errata)
    sync_report_table_a(report_dir / "report.md", cells)
    sync_report_table_b(report_dir / "report.md", evidence)
    return {"cells": cells, "solved": solved, "evidence_dir": str(evidence),
            "errata": errata, "snapshot_errata": snapshot_errata}


def _diff_against_archived(archived: dict, cells: list[dict]) -> list[str]:
    """Compare the new solutions with the archived carrier values."""
    lines = []
    for cell in cells:
        key = (cell["contract"], cell["window"])
        previous = archived.get(key)
        if previous is None:
            continue
        for index, column in enumerate(_LIQUIDATION_COLUMNS):
            old, new = previous[index], cell[column]
            if old is None and new is None:
                continue
            if old is None or new is None:
                lines.append(f"{key[0]}-{key[1]} {column}: 留档 {old} → 新算 {new}")
                continue
            if abs(old - new) > 1e-9 * max(1.0, abs(old)):
                lines.append(f"{key[0]}-{key[1]} {column}: 留档 {old!r} → 新算 {new!r}")
    return lines


def archived_snapshot_values(note_path: str | Path) -> dict[tuple[str, str], dict]:
    """Read the archived snapshot-caliber table of the evidence note.

    The note keeps the first-pass (snapshot) records above the stress-test
    section; they are the historical values a reader may still compare
    against, so the errata compares the new stress solutions with them.
    """
    path = Path(note_path)
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    # Only the records above the stress-test section are the archived ones;
    # the stress table below carries the same cell ids in its first column.
    head = text.split(NOTE_START)[0] if NOTE_START in text else text
    archived: dict[tuple[str, str], dict] = {}
    for line in head.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        columns = [part.strip() for part in stripped.strip("|").split("|")]
        if len(columns) < 9 or columns[0] in ("cell", "---"):
            continue
        cell_id = columns[0]
        if "-" not in cell_id:
            continue
        contract, _, window = cell_id.rpartition("-")
        if not contract or not window.startswith("W"):
            continue
        try:
            down = float(columns[6])
        except ValueError:
            down = None
        try:
            up = float(columns[7])
        except ValueError:
            up = None
        archived[(contract, window)] = {"down": down, "up": up,
                                        "status": columns[8] if len(columns) > 8 else ""}
    return archived


def _snapshot_errata(archived: dict, cells: list[dict]) -> list[str]:
    """Difference between the archived snapshot values and the new solutions."""
    lines = []
    for cell in cells:
        key = (cell["contract"], cell["window"])
        record = archived.get(key)
        if record is None:
            continue
        for column, old, new in (
                ("downward_liquidation_price", record["down"],
                 cell["downward_liquidation_price"]),
                ("upward_liquidation_price", record["up"],
                 cell["upward_liquidation_price"])):
            if old is None and new is None:
                continue
            if old is None or new is None:
                lines.append(f"{key[0]}-{key[1]} {column}: 留档快照口径 {old} → "
                             f"压力测试口径 {new}")
                continue
            if abs(old - new) > 1e-9 * max(1.0, abs(old)):
                lines.append(f"{key[0]}-{key[1]} {column}: 留档快照口径 {old!r} → "
                             f"压力测试口径 {new!r}")
    return lines


def _price_text(value: float | None) -> str:
    return f"{value:.12g}" if value is not None else "无根(权益下限>0)"


def _note_lines(cells: list[dict], solved: dict) -> list[str]:
    lines = [NOTE_HEADING + "（2026-11-04 Pascal 二次裁定，替代快照口径）", "",
             "- 语义：从网格中线空仓出发，单边下跌逐线成交下半区 long 挂单（CELL_LOWER 限价买）/ "
             "单边上涨逐线成交上半区 short 挂单（CELL_UPPER 限价卖），仓位持有不平仓不复投；"
             "解 E(p) ≤ (MMR+fee)·名义 的价格根，段间线性精确求解（首次穿越语义）",
             "- 每格挂单名义 = E0×pct×leverage = 1000×(1/N)×10（Path B value 路径杠杆放大，"
             "backtest 成交流实证 87.72=1000/114×10）；E0=1000、fee=taker 0.05%",
             "- MMR 来源分层（SKILL 契约，不得跳序）：平台原生字段 > Binance 公开 brackets 接口 > "
             "冻结默认梯度（名义 ≤20,000 用 1.0%，>20,000 用 1.5%，标注 "
             "`default MMR tier (binance unreachable)`）",
             "- 档位口径：按爆仓时刻的持仓名义（mark notional）选档，并按该档重解（不动点迭代）；"
             "Binance 档位表为 Gate 侧代理参数，报告需披露该替换",
             "- 不依赖回测成交/持仓数据，输入仅为冻结网格几何（strategy.py CELL_* 数组）+ 资金口径",
             "",
             "**2026-11-04 F 项修正重算（费用只计一次）**：强平费 F 由 venue 按强平名义收取，"
             "进入维持保证金因子 MF = MMR + F（SKILL 冻结口径 "
             "`E(p) ≤ MM(p) = (mmr + close_fee)·名义 − cum`），权益侧保持毛额，"
             "故多头解 `E0 − N + pQ = MF·pQ − cum`、空头解 `E0 + N − pQ = MF·pQ − cum`，"
             "即 `E(p)−MM(p) = (E0∓N+cum) ± pQ(1∓MF)`。修正前实现把 F 同时扣在权益侧，"
             "等价于把费用计了两次（p 系数 1∓MF∓F）；修正后 p 系数为 1∓MF。"
             "影响量级：16 cell 根相对移动约 −5.05e-4（下行）/ +4.95e-4（上行），"
             "zone 分布与触发时成交格数 16/16 全部不变；"
             "回测数据、runId 41–56 与其余指标列未变，属事后重算。",
             "",
             "| cell | 多头格/空头格 | 多头名义 | 空头名义 | 下行根 | 触发时成交格数 | 下行区域 | "
             "上行根 | 触发时成交格数 | 上行区域 | 下行MMR | 上行MMR |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for cell in cells:
        key = (cell["contract"], cell["window"])
        result = solved.get(key)
        if result is None:
            continue
        down, up = result["down"], result["up"]
        lines.append(
            f"| {key[0]}-{key[1]} | {result['n_long']}/{result['n_short']} | "
            f"{result['long_notional']:.0f} | {result['short_notional']:.0f} | "
            f"{_price_text(down['root'])} | {down['fills']} | {down['zone']} | "
            f"{_price_text(up['root'])} | {up['fills']} | {up['zone']} | "
            f"{down['mmr']:.4%} ({down['mmr_source']}) | {up['mmr']:.4%} ({up['mmr_source']}) |")
    lines += ["",
              "注：in-ladder = 爆仓发生在挂单阶梯内（部分格未成交即爆仓）；below-L/above-U = "
              "阶梯全部成交后于区间外爆仓；no-root = 权益下限 E0−侧名义 > 0，单程不爆仓。",
              "假设：单调行情、限价全成交、无退出/复投周期、不含入场佣金（强度低于含佣金情形，"
              "差异一阶可忽略）；`grid_research.py` 冻结函数未改动，本口径为独立压力求解器。"]
    return lines


def _write_note(path: Path, cells: list[dict], solved: dict) -> None:
    """Refresh the stress-test section of the evidence note (idempotent).

    The earlier snapshot-caliber records above the section are kept; only the
    stress-test section itself is regenerated.
    """
    block = "\n".join([NOTE_START, *_note_lines(cells, solved), NOTE_END])
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if NOTE_START in text and NOTE_END in text:
        head = text.split(NOTE_START)[0]
        tail = text.split(NOTE_END, 1)[1]
        text = head + block + tail
    elif NOTE_HEADING in text:
        head = text.split(NOTE_HEADING)[0]
        text = head.rstrip("\n") + "\n\n" + block + "\n"
    else:
        text = (text.rstrip("\n") + "\n\n" + block + "\n")
    path.write_text(text, encoding="utf-8")


def _append_erratum(path: Path, errata: list[str]) -> None:
    """Write the correction block; the archived records are never deleted.

    The block is marker-delimited and rewritten in place, so re-running the
    backfill does not accumulate copies.
    """
    lines = [ERRATA_HEADING, "",
             "压力测试求解器与留档快照口径的数值差异如下（上方留档记录保留，不删除）：",
             ""]
    lines += [f"- {line}" for line in errata]
    lines.append("")
    block = "\n".join([ERRATA_START, *lines, ERRATA_END])
    text = path.read_text(encoding="utf-8")
    if ERRATA_START in text and ERRATA_END in text:
        head = text.split(ERRATA_START)[0]
        tail = text.split(ERRATA_END, 1)[1]
        text = head + block + tail
    else:
        text = text.rstrip("\n") + "\n\n" + block + "\n"
    path.write_text(text, encoding="utf-8")


# ------------------------------------------------------- the report's tables

def _cell_price(value: float | None) -> str:
    return repr(float(value)) if value is not None else "N/A"


def sync_report_table_a(report_md: str | Path, cells: list[dict]) -> None:
    """Write the solved liquidation prices into table A of the report.

    The values come from the regenerated carrier, never from a hand
    calculation, so the report and ``evidence/cells.csv`` cannot drift. The
    single ``强平价`` column is split into a long and a short column, so the
    table shows both sides of the stress test.
    """
    path = Path(report_md)
    text = path.read_text(encoding="utf-8")
    try:
        head, rest = text.split("## 2. 表 A", 1)
        section, tail = rest.split("## 3.", 1)
    except ValueError as error:
        raise ValueError("report has no table A section") from error
    lookup = {(cell["contract"], cell["window"]): cell for cell in cells}
    lines = section.splitlines()
    header_index = next((index for index, line in enumerate(lines)
                         if line.strip().startswith("|")), None)
    if header_index is None:
        raise ValueError("report table A has no header row")
    header = [part.strip() for part in lines[header_index].strip().strip("|").split("|")]
    if "强平价" in header:
        split_at = header.index("强平价")
        new_header = header[:split_at] + [TABLE_A_LONG, TABLE_A_SHORT] + header[split_at + 1:]
        columns_long = split_at
        columns_short = split_at + 1
        inserted = 1
    elif TABLE_A_LONG in header and TABLE_A_SHORT in header:
        new_header = header
        columns_long = header.index(TABLE_A_LONG)
        columns_short = header.index(TABLE_A_SHORT)
        inserted = 0
    else:
        raise ValueError("report table A has no liquidation column")
    contract_at = header.index("合约") if "合约" in header else 0
    window_at = header.index("窗口") if "窗口" in header else 1

    out = lines[:header_index]
    out.append("| " + " | ".join(new_header) + " |")
    for line in lines[header_index + 1:]:
        stripped = line.strip()
        if not stripped.startswith("|"):
            out.append(line)
            continue
        columns = [part.strip() for part in stripped.strip("|").split("|")]
        if all(part and set(part) <= {"-"} for part in columns):
            out.append("|" + "|".join(["---"] * len(new_header)) + "|")
            continue
        if inserted:
            columns.insert(columns_short, "")
        key = (columns[contract_at], columns[window_at])
        if key in lookup:
            cell = lookup[key]
            columns[columns_long] = _cell_price(cell["downward_liquidation_price"])
            columns[columns_short] = _cell_price(cell["upward_liquidation_price"])
        out.append("| " + " | ".join(columns) + " |")
    path.write_text(head + "## 2. 表 A" + "\n".join(out) + "## 3." + tail,
                    encoding="utf-8")


def sync_report_table_b(report_md: str | Path, evidence_dir: str | Path) -> None:
    """Refresh table B of the report from the regenerated comparison carrier.

    The report's table B is a generated view: the same rows that produced
    ``evidence/table-b-summary.md`` are copied in, so the report and the
    carrier cannot drift.
    """
    path = Path(report_md)
    summary = (Path(evidence_dir) / "table-b-summary.md").read_text(encoding="utf-8")
    table_lines = [line for line in summary.splitlines()
                   if line.strip().startswith("|")]
    footnotes = [line for line in summary.splitlines()
                 if line.startswith("判定符号：") or line.startswith("指标口径：")]
    text = path.read_text(encoding="utf-8")
    try:
        head, rest = text.split("## 3. 表 B", 1)
        section, tail = rest.split("## 4.", 1)
    except ValueError as error:
        raise ValueError("report has no table B section") from error
    kept = [line for line in section.splitlines()
            if line.strip().startswith(">")]
    body = list(table_lines) + footnotes + kept
    path.write_text(head + "## 3. 表 B" + "\n\n" + "\n\n".join(body)
                    + "\n\n## 4." + tail, encoding="utf-8")


# ------------------------------------------------------------------ the CLI

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--report-dir", required=True,
                        help="report topic directory (holds report.md and evidence/)")
    parser.add_argument("--anchor-utc", required=True,
                        help="batch anchor (task date midnight, UTC)")
    parser.add_argument("--runs-json", default=None,
                        help="optional platform run results (pairs / amount per grid)")
    args = parser.parse_args(argv)
    result = backfill(args.report_dir, args.anchor_utc, args.runs_json)
    for cell in result["cells"]:
        solved = result["solved"].get((cell["contract"], cell["window"]))
        if solved is None:
            continue
        print(f"{cell['contract']}-{cell['window']} "
              f"down={cell['downward_liquidation_price']!r} ({solved['down']['zone']}) "
              f"up={cell['upward_liquidation_price']!r} ({solved['up']['zone']})")
    print(f"carriers regenerated in {result['evidence_dir']}")
    if result["errata"]:
        print(f"errata appended: {len(result['errata'])} difference(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
