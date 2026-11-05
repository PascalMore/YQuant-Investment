"""Generate a QuantDinger-ready, parameterised grid-evolution strategy source.

Contract-agnostic: give it an instrument, a price range and a spacing, and it
emits the same source shape for any symbol (switching contracts is a
parameter change, never a code change).

Platform rules the generated source honours (each one cost a failed run):

1. ``context.params`` is visible only inside executable handlers and the
   platform never calls ``initialize`` at runtime, so the geometry is rebuilt
   at the top of ``handle_data``.
2. The searchable dimensions are ``grid_lower`` / ``grid_upper`` /
   ``grid_gap_pct``; the cell count is derived and the frozen count cap and
   spacing band are enforced by the runtime resolver (mirrors
   ``grid_evolution.resolve_from_gap``).
3. The grid is rebuilt only when the applied parameter signature
   ``(L, U, N)`` changes.  Comparing against rebuilt float arrays reset the
   grid on every bar for about half of all parameter sets.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import math
from pathlib import Path
from typing import Any

# The neighbouring geometry module is loaded by absolute path (same pattern as
# grid_training.py::_load_neighbor) so the scripts directory never has to be on
# sys.path and the module works from any working directory.
_HERE = Path(__file__).resolve().parent


def _load_neighbor(module_name: str, file_name: str) -> Any:
    path = _HERE / file_name
    if not path.is_file():
        raise ImportError(f"required neighbour module missing: {file_name}")
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"neighbour module loader missing: {file_name}")
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_ge = _load_neighbor("grid_evolution_dependency", "grid_evolution.py")
FROZEN_CONSTRAINTS = _ge.FROZEN_CONSTRAINTS
GeometryError = _ge.GeometryError
GridConstraints = _ge.GridConstraints
ResolvedSpacing = _ge.ResolvedSpacing
build_geometry_arrays = _ge.build_geometry_arrays
resolve_from_gap = _ge.resolve_from_gap

# --- the frozen native template ---------------------------------------------
# The template is the verified-compilable grid source (``PUMPUSDT-W2-1h``):
# it carries no discovery-time ``context.log`` call and no evidence gate, so
# the generated source compiles on the platform unchanged.  Do not switch the
# base without re-verifying the platform compile.
LAB = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = LAB / "strategies" / "PUMPUSDT-W2-1h" / "strategy.py"

# --- parameter declarations handed to the platform --------------------------
# The bound ranges are per-contract inputs (``search_ranges``); the spacing
# range is always the frozen business band.  The ``# @param`` lines and the
# parameter-space rows are rendered from the same dict so they cannot drift.
GAP_STEP_PCT = 0.05


def search_declarations(search_ranges: dict[str, tuple[float, float, float]],
                        defaults: dict[str, float],
                        constraints: GridConstraints = FROZEN_CONSTRAINTS
                        ) -> dict[str, dict[str, Any]]:
    """Build the three searchable declarations for one contract.

    ``search_ranges`` maps ``grid_lower`` / ``grid_upper`` to ``(min, max,
    step)``; ``defaults`` carries the baseline value of every parameter.
    """
    gap = (constraints.gap_min_pct, constraints.gap_max_pct, GAP_STEP_PCT)
    ranges = {**search_ranges, "grid_gap_pct": gap}
    descriptions = {"grid_lower": "Lower grid bound, absolute price",
                    "grid_upper": "Upper grid bound, absolute price",
                    "grid_gap_pct": (f"Grid spacing, percent (frozen band "
                                     f"{constraints.gap_min_pct}-{constraints.gap_max_pct})")}
    declarations = {}
    for name in ("grid_lower", "grid_upper", "grid_gap_pct"):
        low, high, step = (float(part) for part in ranges[name])
        if not low < high or step <= 0:
            raise ValueError(f"invalid search range for {name}: {ranges[name]}")
        declarations[name] = {"type": "float", "default": float(defaults[name]),
                              "min": low, "max": high, "step": step,
                              "description": descriptions[name]}
    return declarations


def _clean_number(value: float) -> float:
    """Round away float noise, matching the native template's own cleaner."""
    return round(float(value), 12)


def _fixed(value: float) -> str:
    """Fixed-point text for a declaration number.

    The platform's ``range=`` parser (``indicator_params._RANGE_RE``) accepts
    only ``-?\\d+(\\.\\d+)?``: ``7.35e-05`` is read as ``7.35`` and the whole
    declaration silently collapses to a single value.
    """
    text = f"{float(value):.12f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-0") else "0"


def _param_block(declarations: dict[str, dict[str, Any]]) -> str:
    """Render the ``# @param`` declarations the platform reads."""
    return "\n".join(
        f"# @param {name} {spec['type']} {_fixed(spec['default'])} {spec['description']} "
        f"range={_fixed(spec['min'])}:{_fixed(spec['max'])}:{_fixed(spec['step'])}"
        for name, spec in declarations.items())


def _geometry_runtime_block(constraints: GridConstraints,
                            default_gap_pct: float = 1.5) -> str:
    """Runtime geometry resolver injected into the strategy source.

    It mirrors ``grid_evolution.resolve_from_gap`` exactly.  The duplicated
    arithmetic is intentional: the strategy runs inside the QuantDinger
    sandbox and cannot import lab modules.  ``tests/test_grid_evolution.py``
    pins the two implementations to the same behaviour.
    """
    return f'''
# --- frozen grid geometry (generated by scripts/grid_evolution.py) ------------
EVOLVE_GAP_MIN_PCT = {constraints.gap_min_pct!r}
EVOLVE_GAP_MAX_PCT = {constraints.gap_max_pct!r}
EVOLVE_GRID_MIN_COUNT = {constraints.min_count!r}
EVOLVE_GRID_MAX_COUNT = {constraints.max_count!r}
EVOLVE_DEFAULT_GAP_PCT = {default_gap_pct!r}
EVOLVE_SIGNATURE = None


def _evolve_feasible_window(lower0, upper0):
    """Integer cell counts satisfying the gap band and the count cap at once."""
    span = math.log(upper0 / lower0)
    n_for_gap_max = span / math.log1p(EVOLVE_GAP_MAX_PCT / 100.0)
    n_for_gap_min = span / math.log1p(EVOLVE_GAP_MIN_PCT / 100.0)
    low = max(EVOLVE_GRID_MIN_COUNT, int(math.ceil(n_for_gap_max - 1e-12)))
    high = min(EVOLVE_GRID_MAX_COUNT, int(math.floor(n_for_gap_min + 1e-12)))
    if low > high:
        raise ValueError("evolve.geometry.infeasible")
    return low, high


def _evolve_resolve(lower0, upper0, requested_gap_pct):
    """Resolve a requested spacing into a geometry honouring both constraints.

    The spacing is the requested business value; the cell count is derived
    from it.  When the derived count falls outside the feasible window the
    spacing itself moves, because the spacing is what the caller asked for.
    Moving the spacing towards the direction that keeps the count inside the
    window guarantees the executed spacing stays inside the frozen band.
    """
    lower0 = float(lower0)
    upper0 = float(upper0)
    requested_gap = float(requested_gap_pct)
    if not 0.0 < lower0 < upper0:
        raise ValueError("evolve.geometry.invalidRange")
    low, high = _evolve_feasible_window(lower0, upper0)
    span = math.log(upper0 / lower0)
    derived = span / math.log1p(requested_gap / 100.0)
    if derived > high:
        count = high
    elif derived < low:
        count = low
    else:
        count = int(round(derived))
    count = max(EVOLVE_GRID_MIN_COUNT, min(EVOLVE_GRID_MAX_COUNT, count))
    gap = 100.0 * math.expm1(span / count)
    return count, gap, low, high


def _evolve_build(lower0, upper0, count):
    """Build the frozen grid arrays for a geometric grid."""
    span = math.log(upper0 / lower0)
    step = span / count
    lower = [lower0 * math.exp(step * index) for index in range(count)]
    upper = [lower0 * math.exp(step * (index + 1)) for index in range(count)]
    reference = (lower0 + upper0) / 2.0
    roles = ["long_entry" if (lower[index] + upper[index]) / 2.0 < reference
             else "short_entry" for index in range(count)]
    pcts = [1.0 / count for _ in roles]
    pcts[-1] = 1.0 - sum(pcts[:-1])
    arm_order = sorted(range(count), key=lambda index: abs(
        (lower[index] if roles[index].startswith("long") else upper[index]) - reference))
    return lower, upper, roles, pcts, arm_order


def _evolve_apply(context):
    """Rebuild the grid from the run parameters inside the handler.

    The platform exposes ``context.params`` only inside executable handlers,
    so this must run per callback rather than in ``initialize``.
    """
    global CELL_LOWER, CELL_UPPER, CELL_ROLES, CELL_BUDGET_PCTS, ARM_ORDER
    global EVOLVE_EXECUTED, EVOLVE_SIGNATURE
    try:
        params = context.params or {{}}
    except AttributeError:
        params = {{}}
    lower0 = float(params.get("grid_lower", CELL_LOWER[0]))
    upper0 = float(params.get("grid_upper", CELL_UPPER[-1]))
    gap_req = float(params.get("grid_gap_pct", EVOLVE_DEFAULT_GAP_PCT))
    count, gap, low, high = _evolve_resolve(lower0, upper0, gap_req)
    # Rebuild only when the APPLIED parameter signature changes.  Comparing
    # against rebuilt float arrays (e.g. upper0 != CELL_UPPER[-1]) is wrong:
    # lower0*exp(span/n*n) is not bit-equal to upper0 for about half of the
    # (L, U, N) combinations, which tore the grid down and reset every cell
    # on every bar (measured 2026-11-05: 0 matched pairs vs 1278).
    signature = (lower0, upper0, count)
    # Module-level state, like CELL_LOWER: ``initialize`` is not called at
    # runtime and the sandbox has no ``getattr``.  None triggers the first build.
    if signature != EVOLVE_SIGNATURE:
        EVOLVE_SIGNATURE = signature
        CELL_LOWER, CELL_UPPER, CELL_ROLES, CELL_BUDGET_PCTS, ARM_ORDER = \\
            _evolve_build(lower0, upper0, count)
        g.evolve_cells = count
        g.cell_states = ["entry_ready" for _ in range(count)]
        g.cell_refs = ["" for _ in range(count)]
        g.cell_quantities = [0.0 for _ in range(count)]
        g.cell_cycles = [1 for _ in range(count)]
    EVOLVE_EXECUTED = {{"N": count, "gap_pct": gap, "requested_gap_pct": gap_req,
                       "L": lower0, "U": upper0,
                       "feasible_window": [low, high]}}
'''


def _handle_data_header() -> str:
    """The wrapper that applies the parameters before the native callback."""
    return '''
def handle_data(context, data):
    """Apply the run parameters, then run the native grid callback."""
    _evolve_apply(context)
    _evolve_handle_data(context, data)
'''


def generate_evolve_source(*, instrument: str, timeframe: str = "1h",
                           lower: float = 0.00147, upper: float = 0.008984,
                           gap_pct: float = 1.5,
                           search_ranges: dict[str, tuple[float, float, float]],
                           cell_id: str = "GRID-EVOLVE",
                           constraints: GridConstraints = FROZEN_CONSTRAINTS,
                           template_path: Path = TEMPLATE_PATH,
                           ) -> tuple[str, dict[str, Any]]:
    """Emit a parameterised grid-evolution strategy source.

    ``search_ranges`` declares the sampled ``grid_lower`` / ``grid_upper``
    ranges for this contract.  Returns ``(source, manifest)``.  The manifest records the executed
    geometry so the caller can persist it alongside the backtest evidence.

    The searchable dimension is the spacing (``gap_pct``); the cell count is
    derived from it.
    """
    template_path = Path(template_path)
    raw = template_path.read_bytes()
    original = raw.decode("utf-8")
    ast.parse(original)  # static syntax check of the native template

    resolved = resolve_from_gap(lower, upper, gap_pct, constraints)
    declarations = search_declarations(
        search_ranges, {"grid_lower": lower, "grid_upper": upper, "grid_gap_pct": gap_pct},
        constraints)
    arrays = build_geometry_arrays(resolved.lower, resolved.upper, resolved.count,
                                   constraints)

    constants = {
        "INSTRUMENT": instrument,
        "TIMEFRAME": timeframe,
        "CELL_LOWER": [_clean_number(v) for v in arrays["lower"]],
        "CELL_UPPER": [_clean_number(v) for v in arrays["upper"]],
        "CELL_ROLES": arrays["roles"],
        "CELL_BUDGET_PCTS": arrays["pcts"],
        "ARM_ORDER": arrays["arm_order"],
        "MAX_OPEN_ENTRY_ORDERS": min(4, resolved.count),
    }
    extra = {
        "CELL_ID": cell_id,
        "TEMPLATE_SHA256": hashlib.sha256(raw).hexdigest(),
        "SOURCE_KIND": "parameterised_grid_evolution",
        "EVOLVE_EXECUTED": {"N": resolved.count, "gap_pct": resolved.gap_pct,
                            "requested_gap_pct": resolved.requested_gap_pct,
                            "feasible_window": list(resolved.feasible_window)},
        "FROZEN_PARAMETERS": {
            "L": resolved.lower, "U": resolved.upper, "N": resolved.count,
            "g_pct": resolved.gap_pct, "grid_lines": resolved.count + 1,
            "requested_gap_pct": resolved.requested_gap_pct,
            "adjustment": resolved.adjustment,
            "gap_bounds_pct": [constraints.gap_min_pct, constraints.gap_max_pct],
            "count_bounds": [constraints.min_count, constraints.max_count],
            "mode": constraints.mode,
        },
    }
    json.dumps(extra, allow_nan=False, default=str)  # finite-value guard

    lines = original.splitlines(keepends=True)
    replacements: list[tuple[int, int, str]] = []
    native_handle_data = ""
    replaced_names = set(constants) | set(extra)
    for node in ast.parse(original).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in constants:
                replacements.append((node.lineno - 1, node.end_lineno or node.lineno,
                                     f"{name} = {constants[name]!r}\n"))
            elif name in replaced_names:
                # Drop the template's own copy so the generated header is the
                # single source of truth for that name.
                replacements.append((node.lineno - 1, node.end_lineno or node.lineno, ""))
        elif isinstance(node, ast.FunctionDef):
            text = "".join(lines[node.lineno - 1:node.end_lineno])
            end = node.end_lineno or node.lineno
            if node.name == "handle_data":
                # The native callback is kept under a new name and invoked by
                # the parameterised wrapper appended below.
                native_handle_data = text.replace("def handle_data(", "def _evolve_handle_data(", 1)
                replacements.append((node.lineno - 1, end, ""))
            else:
                replacements.append((node.lineno - 1, end, text + "\n"))
    for start, end, replacement in sorted(replacements, reverse=True):
        lines[start:end] = [replacement]
    if not native_handle_data:
        raise ValueError("native template has no handle_data callback")

    body = "".join(lines)
    header = (
        '"""Parameterised geometric grid for QuantDinger native evolution.\n\n'
        "Generated by scripts/grid_evolve_source.py; the frozen cell-count cap and\n"
        "the business spacing band are enforced inside handle_data, where the platform\n"
        "exposes the run parameters.  Never edit the generated file by hand.\n"
        '"""\n'
        "import json\n"
        "import math\n"
        f"{_param_block(declarations)}\n"
        + "".join(f"{name} = {value!r}\n" for name, value in extra.items())
    )
    source = (
        header
        + body
        + _geometry_runtime_block(constraints, resolved.gap_pct)
        + "\n"
        + native_handle_data.rstrip("\n")
        + "\n\n"
        + _handle_data_header()
    )
    ast.parse(source)  # static syntax check of the emitted source
    manifest = {
        "cell_id": cell_id,
        "instrument": instrument,
        "timeframe": timeframe,
        "template_sha256": extra["TEMPLATE_SHA256"],
        "executed_geometry": resolved.to_dict(),
        "parameter_declarations": declarations,
        "source_bytes": len(source),
    }
    return source, manifest


def build_param_space(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Platform parameter-space rows, identical to the ``# @param`` lines."""
    return [{"name": name, "type": "number", "default": spec["default"],
             "min": spec["min"], "max": spec["max"], "step": spec["step"],
             "description": spec["description"]}
            for name, spec in manifest["parameter_declarations"].items()]


__all__ = ["GAP_STEP_PCT", "TEMPLATE_PATH", "build_param_space", "generate_evolve_source",
           "search_declarations"]
