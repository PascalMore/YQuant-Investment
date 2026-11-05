"""Grid evolution geometry: the single source of truth for grid constraints.

Contract (frozen by Pascal, both constraints must hold simultaneously):

  C1  gap in [GAP_MIN_PCT, GAP_MAX_PCT]   grid spacing, equal-ratio (geometric)
  C2  N in [GRID_MIN_COUNT, GRID_MAX_COUNT]
  C3  geometric (equal-ratio) grid mode

In a geometric grid the spacing and the cell count are one degree of
freedom: ``U/L = (1 + gap)^N``.  The searchable dimension is the spacing
(``grid_gap_pct``); the count is derived.  When the derived count leaves the
feasible window the spacing moves (it is the requested business value) and
the move is disclosed, so the executed spacing never leaves the frozen band.

This module is the platform-independent core shared by the strategy source
generator and the evolution driver, so the geometry that executes on
QuantDinger and the tables that describe it cannot drift.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

# --- frozen user constraints (Pascal 2026-11-05) ----------------------------
GAP_MIN_PCT = 0.45
GAP_MAX_PCT = 1.5
GRID_MIN_COUNT = 3
GRID_MAX_COUNT = 200
GRID_MODE = "geometric"

ABS_TOL = 1e-12
REL_TOL = 1e-10


class GeometryError(ValueError):
    """Raised when no geometry satisfies C1 and C2 simultaneously."""


@dataclass(frozen=True)
class GridConstraints:
    """User-controlled grid constraints; both apply at the same time."""

    gap_min_pct: float = GAP_MIN_PCT
    gap_max_pct: float = GAP_MAX_PCT
    min_count: int = GRID_MIN_COUNT
    max_count: int = GRID_MAX_COUNT
    mode: str = GRID_MODE

    def __post_init__(self) -> None:
        if not 0 < self.gap_min_pct < self.gap_max_pct:
            raise ValueError("gap_min_pct must be positive and below gap_max_pct")
        if self.min_count < 1 or self.max_count < self.min_count:
            raise ValueError("invalid grid count bounds")
        if self.mode != "geometric":
            raise ValueError("only the geometric grid mode is supported")

    @property
    def is_frozen(self) -> bool:
        return (self.gap_min_pct == GAP_MIN_PCT and self.gap_max_pct == GAP_MAX_PCT
                and self.min_count == GRID_MIN_COUNT and self.max_count == GRID_MAX_COUNT
                and self.mode == GRID_MODE)


FROZEN_CONSTRAINTS = GridConstraints()


def gap_for_count(lower: float, upper: float, count: int) -> float:
    """Geometric spacing in percent for ``count`` cells over [lower, upper]."""
    if not 0 < lower < upper:
        raise ValueError("lower must be positive and below upper")
    if count < 1:
        raise ValueError("count must be positive")
    return 100.0 * math.expm1(math.log(upper / lower) / count)


def count_for_gap(lower: float, upper: float, gap_pct: float) -> float:
    """Real-valued cell count implied by a spacing (not necessarily an integer)."""
    if not 0 < lower < upper:
        raise ValueError("lower must be positive and below upper")
    if gap_pct <= -100.0:
        raise ValueError("gap_pct must be greater than -100")
    return math.log(upper / lower) / math.log1p(gap_pct / 100.0)


def feasible_count_window(lower: float, upper: float,
                          constraints: GridConstraints = FROZEN_CONSTRAINTS) -> tuple[int, int]:
    """Integer cell counts satisfying C1 and C2 simultaneously.

    Returns ``(low, high)`` inclusive.  Raises :class:`GeometryError` when the
    price range admits no feasible grid (e.g. too wide for the gap floor or too
    narrow for the gap ceiling).
    """
    if not 0 < lower < upper:
        raise GeometryError("lower must be positive and below upper")
    span = math.log(upper / lower)
    # gap <= gap_max  =>  N >= span / ln(1+gap_max)
    # gap >= gap_min  =>  N <= span / ln(1+gap_min)
    n_for_gap_max = span / math.log1p(constraints.gap_max_pct / 100.0)
    n_for_gap_min = span / math.log1p(constraints.gap_min_pct / 100.0)
    low = max(constraints.min_count, math.ceil(n_for_gap_max - ABS_TOL))
    high = min(constraints.max_count, math.floor(n_for_gap_min + ABS_TOL))
    if low > high:
        raise GeometryError(
            f"no feasible grid for [{lower:g}, {upper:g}]: "
            f"gap in [{constraints.gap_min_pct}, {constraints.gap_max_pct}] and "
            f"N in [{constraints.min_count}, {constraints.max_count}] cannot both hold")
    return low, high


@dataclass(frozen=True)
class ResolvedSpacing:
    """The geometry resolved from a requested *spacing*.

    Under the spacing-first contract (the searchable dimension is the gap),
    the requested gap is the business value and the cell count is derived.
    When the derived count falls outside the feasible window the gap itself
    must move, because the gap is what the caller asked for.  The moved gap
    always lands inside the frozen band and the move is disclosed.
    """

    lower: float
    upper: float
    count: int
    gap_pct: float
    requested_gap_pct: float
    adjustment: str          # exact | gap_raised_to_n_max | gap_lowered_to_n_min
    feasible_window: tuple[int, int]
    constraints: GridConstraints = field(default=FROZEN_CONSTRAINTS)

    @property
    def satisfies_gap(self) -> bool:
        c = self.constraints
        return c.gap_min_pct - 1e-9 <= self.gap_pct <= c.gap_max_pct + 1e-9

    @property
    def satisfies_count(self) -> bool:
        c = self.constraints
        return c.min_count <= self.count <= c.max_count

    @property
    def satisfies_both(self) -> bool:
        return self.satisfies_gap and self.satisfies_count

    def disclosure(self) -> str:
        return (f"N={self.count} gap={self.gap_pct:.6f}% "
                f"(requested gap={self.requested_gap_pct:.6f}%, {self.adjustment}, "
                f"feasible N in [{self.feasible_window[0]}, {self.feasible_window[1]}], "
                f"gap in [{self.constraints.gap_min_pct}, {self.constraints.gap_max_pct}]%)")

    def to_dict(self) -> dict[str, Any]:
        return {
            "L": self.lower, "U": self.upper, "N": self.count, "g_pct": self.gap_pct,
            "requested_gap_pct": self.requested_gap_pct, "adjustment": self.adjustment,
            "feasible_N_window": list(self.feasible_window),
            "gap_bounds_pct": [self.constraints.gap_min_pct, self.constraints.gap_max_pct],
            "mode": self.constraints.mode,
        }


def build_geometry_arrays(lower: float, upper: float, count: int,
                           constraints: GridConstraints = FROZEN_CONSTRAINTS
                           ) -> dict[str, Any]:
    """Build the frozen grid arrays for a geometric grid.

    Mirrors the native template exactly: points are ``lower * (upper/lower) **
    (index/count)`` with the endpoints pinned, roles split at the mid price,
    budgets equal-weight with the last cell absorbing the residual, and arm
    order sorted by distance from the mid price.
    """
    low, high = feasible_count_window(lower, upper, constraints)
    if not low <= int(count) <= high:
        raise GeometryError(f"N={count} outside the feasible window [{low}, {high}]")
    lower_f, upper_f, count_f = float(lower), float(upper), int(count)
    points = [lower_f * (upper_f / lower_f) ** (index / count_f) for index in range(count_f + 1)]
    points[0], points[-1] = lower_f, upper_f
    reference = (lower_f + upper_f) / 2.0
    roles = ["long_entry" if (low + high) / 2.0 < reference else "short_entry"
             for low, high in zip(points[:-1], points[1:])]
    weights = [1.0 / count_f for _ in roles]
    weights[-1] = 1.0 - sum(weights[:-1])
    arm_order = sorted(range(count_f), key=lambda index: abs(
        (points[index] if roles[index].startswith("long") else points[index + 1]) - reference))
    return {
        "lower": points[:-1],
        "upper": points[1:],
        "roles": roles,
        "pcts": weights,
        "arm_order": arm_order,
    }


def resolve_from_gap(lower: float, upper: float, gap_pct: float,
                     constraints: GridConstraints = FROZEN_CONSTRAINTS) -> ResolvedSpacing:
    """Resolve a requested *spacing* into a geometry honouring C1 and C2.

    The spacing is the requested business value; the cell count is derived
    from it.  When the derived count falls outside the feasible window the
    spacing itself moves, because the spacing is what the caller asked for.

    Moving the spacing in the direction that keeps the count inside
    [min_count, max_count] guarantees the executed spacing stays inside the
    frozen band: a count that is too large (spacing too tight) is fixed by
    raising the spacing, and a count that is too small (spacing too wide) is
    fixed by lowering it.  Both directions are clamped to the band, so the
    executed spacing can never leave [gap_min_pct, gap_max_pct].
    """
    lower = float(lower)
    upper = float(upper)
    requested_gap = float(gap_pct)
    if not 0.0 < lower < upper:
        raise GeometryError("evolve.geometry.invalidRange")
    low, high = feasible_count_window(lower, upper, constraints)
    derived_count = count_for_gap(lower, upper, requested_gap)
    if derived_count > high:
        # spacing too tight -> too many cells -> raise the spacing
        count = high
        adjustment = "gap_raised_to_n_max"
    elif derived_count < low:
        # spacing too wide -> too few cells -> lower the spacing
        count = low
        adjustment = "gap_lowered_to_n_min"
    else:
        count = int(round(derived_count))
        adjustment = "exact"
    count = max(constraints.min_count, min(constraints.max_count, count))
    executed_gap = gap_for_count(lower, upper, count)
    resolved = ResolvedSpacing(
        lower=lower, upper=upper, count=count, gap_pct=executed_gap,
        requested_gap_pct=requested_gap, adjustment=adjustment,
        feasible_window=(low, high), constraints=constraints)
    if not resolved.satisfies_both:
        raise GeometryError(
            f"evolve.geometry.unresolvable: {resolved.disclosure()}")
    return resolved


def verify_geometry(geometry: dict[str, Any],
                     constraints: GridConstraints = FROZEN_CONSTRAINTS) -> dict[str, Any]:
    """Independently verify a geometry dict against both frozen constraints.

    Used by the acceptance path: the checker must not reuse the resolver.
    """
    lower = float(geometry["L"])
    upper = float(geometry["U"])
    count = int(geometry["N"])
    gap = float(geometry["g_pct"])
    problems: list[str] = []
    if not 0 < lower < upper:
        problems.append("L/U not a positive ascending pair")
    if not constraints.min_count <= count <= constraints.max_count:
        problems.append(f"N={count} outside [{constraints.min_count}, {constraints.max_count}]")
    if not constraints.gap_min_pct - 1e-9 <= gap <= constraints.gap_max_pct + 1e-9:
        problems.append(f"gap={gap:.6f}% outside "
                        f"[{constraints.gap_min_pct}, {constraints.gap_max_pct}]")
    recomputed = gap_for_count(lower, upper, count) if 0 < lower < upper else float("nan")
    if 0 < lower < upper and abs(recomputed - gap) > 1e-6:
        problems.append(f"gap mismatch: stated {gap:.6f}% vs recomputed {recomputed:.6f}%")
    for column in ("cell_lower", "cell_upper"):
        cells = geometry.get(column)
        if cells is None:
            continue
        if len(cells) != count:
            problems.append(f"{column} length does not match N")
    return {"ok": not problems, "problems": problems, "recomputed_gap_pct": recomputed}


__all__ = [
    "ABS_TOL", "FROZEN_CONSTRAINTS", "GAP_MAX_PCT", "GAP_MIN_PCT", "GRID_MAX_COUNT",
    "GRID_MIN_COUNT", "GRID_MODE", "REL_TOL", "GeometryError", "GridConstraints",
    "ResolvedSpacing", "build_geometry_arrays", "count_for_gap", "feasible_count_window",
    "gap_for_count", "resolve_from_gap", "verify_geometry",
]
