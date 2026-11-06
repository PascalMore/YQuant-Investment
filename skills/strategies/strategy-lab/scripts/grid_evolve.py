"""Standardised grid-evolution driver: one command per contract.

Switching to another contract is a parameter change, never a code change:

    QUANTDINGER_JWT=... PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \\
        skills/strategies/strategy-lab/scripts/grid_evolve.py run \\
        --contract PUMPUSDT --instrument "Crypto:PUMP/USDT@swap" \\
        --lower 0.00147 --upper 0.008984 --gap-pct 1.5 \\
        --evolve-start 2025-08-03 --evolve-end 2026-08-03 \\
        --holdout-start 2026-08-03 --holdout-end 2026-11-03

Sequence (each gate stops the run on failure):

  G1  the generated source compiles on the platform
  G2  the platform exposes exactly grid_lower / grid_upper / grid_gap_pct
  G3  two different parameter sets produce different backtests
  G4  native evolution over the evolution period reaches ``succeeded``
  G5  every top candidate is backtested on each quarterly selection window
      and judged; the selection rule picks the winner
  G5b only when G5 finds no winner: the same candidates are re-judged at
      each fallback leverage (default 8/6/4/3x, descending); the first tier
      with a winner stops the descent
  G6  the winner is backtested once on the held-out window at its own
      leverage (reported only, never fed back into the selection)

Search ranges are mechanical, never hand-tuned: unless overridden, the
grid_lower / grid_upper ranges are the platform's own default
(``baseline x [0.5, 1.5]``) on a fixed number of steps.

Selection rule (Pascal 2026-11-05, frozen):
  * a window is ``qualified`` when G/E <= 2.0, MDD <= 35% and metrics complete;
  * a candidate is eligible when qualified windows >= 50% of the selection
    windows AND no window went bankrupt (platform ``liquidated=true``);
  * among eligible candidates the highest mean window return wins;
  * no eligible candidate -> report "no qualified candidate"; never relax.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import grid_evolution as ge  # noqa: E402
import grid_evolve_source as ges  # noqa: E402

DEFAULT_BASE_URL = "http://127.0.0.1:15000"
REPORTS_ROOT = _HERE.parents[3] / "data" / "reports"

# Frozen risk envelope (strategy-lab SKILL, Pascal 2026-11-04).
RISK_GROSS_TO_EQUITY_LIMIT = 2.0
RISK_DRAWDOWN_LIMIT_PCT = 35.0
# Selection rule (Pascal 2026-11-05): qualified windows >= this share.
QUALIFIED_WINDOW_SHARE = 0.5
# Outer persisted-backtest budget (Pascal 2026-11-05: a parameter, default 500).
BACKTEST_BUDGET = 500
# Fallback leverage tiers, tried in order only when no candidate qualifies.
FALLBACK_LEVERAGES = (8, 6, 4, 3)
# Platform default numeric range (parameter_space._infer_numeric_range).
DEFAULT_RANGE_FACTORS = (0.5, 1.5)
DEFAULT_RANGE_STEPS = 20


class EvolutionError(RuntimeError):
    """A gate failed; the run must not continue."""


class Platform:
    """Thin QuantDinger Human-API client used by the driver."""

    def __init__(self, token: str, base_url: str = DEFAULT_BASE_URL,
                 budget: int = BACKTEST_BUDGET):
        self._token, self._base_url = token, base_url
        self.budget, self.backtests = budget, 0

    def call(self, method: str, path: str, body: dict | None = None,
             params: dict | None = None) -> dict:
        url = self._base_url + path + ("?" + urlencode(params) if params else "")
        request = urllib.request.Request(
            url, data=json.dumps(body).encode() if body is not None else None,
            method=method, headers={"Authorization": "Bearer " + self._token,
                                    "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as error:
            return {"code": 0, "msg": f"HTTP {error.code}"}

    def wait(self, path: str, *, poll_seconds: int, max_polls: int) -> dict:
        for _ in range(max_polls):
            time.sleep(poll_seconds)
            state = self.call("GET", path).get("data") or {}
            if str(state.get("status") or "").lower() not in ("queued", "pending", "running"):
                return state
        raise EvolutionError(f"{path} did not reach a terminal state")

    def backtest(self, source_id: int, start: str, end: str, params: dict,
                 run: dict, leverage: float | None = None) -> dict:
        """Run one persisted backtest and return the judged window metrics."""
        if self.backtests >= self.budget:
            raise EvolutionError(f"backtest budget exhausted ({self.budget})")
        self.backtests += 1
        submitted = self.call("POST", "/api/backtest/jobs", {
            "sourceId": source_id, "startDate": start, "endDate": end,
            "initialCapital": run["capital"], "commission": run["commission"],
            "slippage": run["slippage"], "leverageEnabled": True,
            "leverage": leverage or run["leverage"], "params": params, "persist": True})
        job = (submitted.get("data") or {}).get("jobId")
        if not job:
            raise EvolutionError(f"backtest submit failed: {submitted.get('msg')}")
        state = self.wait(f"/api/backtest/jobs/{job}", poll_seconds=5, max_polls=240)
        result = state.get("result") or {}
        if str(state.get("status")).lower() != "succeeded" or not result.get("runId"):
            raise EvolutionError(f"backtest {state.get('status')} for {start}..{end}")
        return window_metrics(result)


def window_metrics(result: dict) -> dict:
    """Extract the judged metrics from one backtest result."""
    curve = result.get("equityCurve") or []
    gross = max((abs(float(p.get("grossExposure") or 0.0)) for p in curve), default=None)
    return {"runId": int(result["runId"]),
            "margin_return_pct": result.get("totalReturn"),
            "max_drawdown_pct": result.get("maxDrawdown"),
            "sharpe": result.get("sharpeRatio"),
            "worst_gross_to_equity": gross,
            "pairs": int(result.get("gridMatchedTradeCount") or 0),
            "liquidated": bool(result.get("liquidated")),
            "executions": result.get("executions") or []}


def judge_window(metrics: dict) -> tuple[str, str]:
    """Qualify one window against the frozen risk envelope."""
    reasons = []
    gross, drawdown = metrics.get("worst_gross_to_equity"), metrics.get("max_drawdown_pct")
    if metrics.get("liquidated"):
        reasons.append("破产强平")
    if gross is not None and gross > RISK_GROSS_TO_EQUITY_LIMIT:
        reasons.append(f"杠杆超限(敞口/权益 {gross:.2f} > {RISK_GROSS_TO_EQUITY_LIMIT})")
    if drawdown is not None and abs(drawdown) > RISK_DRAWDOWN_LIMIT_PCT:
        reasons.append(f"回撤超限({abs(drawdown):.1f}% > {RISK_DRAWDOWN_LIMIT_PCT}%)")
    if reasons:
        return "risk-breach", "; ".join(reasons)
    if None in (gross, drawdown, metrics.get("margin_return_pct")):
        return "insufficient-evidence", "missing metric"
    return "qualified", "N/A"


def select_candidate(candidates: list[dict]) -> dict | None:
    """Apply the frozen selection rule; return the winner or ``None``.

    Each candidate carries ``windows`` (judged metrics).  A candidate is
    eligible when its qualified share is >= ``QUALIFIED_WINDOW_SHARE`` and no
    window went bankrupt; the highest mean window return wins.
    """
    for candidate in candidates:
        windows = candidate["windows"]
        qualified = sum(w["qualification"] == "qualified" for w in windows)
        bankrupt = [w["window"] for w in windows if w["liquidated"]]
        candidate["qualified_windows"] = qualified
        candidate["bankrupt_windows"] = bankrupt
        candidate["mean_return_pct"] = (
            sum(float(w["margin_return_pct"] or 0.0) for w in windows) / len(windows))
        candidate["eligible"] = (qualified >= QUALIFIED_WINDOW_SHARE * len(windows)
                                 and not bankrupt)
    eligible = [c for c in candidates if c["eligible"]]
    return max(eligible, key=lambda c: c["mean_return_pct"]) if eligible else None


def quarterly_windows(start: str, end: str, first_label: int) -> list[tuple[str, str, str]]:
    """Split [start, end) into calendar quarters, newest first.

    Labels count up from ``first_label`` starting at the most recent quarter,
    matching the table-B convention (W1 = most recent).
    """
    begin, finish = date.fromisoformat(start), date.fromisoformat(end)
    bounds = [finish]
    while bounds[-1] > begin:
        current = bounds[-1]
        month = current.month - 3
        year = current.year + (month - 1) // 12
        bounds.append(date(year, (month - 1) % 12 + 1, current.day))
    if bounds[-1] != begin:
        raise EvolutionError(f"{start}..{end} is not a whole number of quarters")
    return [(f"W{first_label + index}", bounds[index + 1].isoformat(), bounds[index].isoformat())
            for index in range(len(bounds) - 1)]


def parse_range(text: str) -> tuple[float, float, float]:
    low, high, step = (float(part) for part in text.split(":"))
    return low, high, step


def default_range(baseline: float, steps: int = DEFAULT_RANGE_STEPS) -> tuple[float, float, float]:
    """Platform-default search range ``baseline x [0.5, 1.5]`` on ``steps`` steps."""
    low, high = (baseline * factor for factor in DEFAULT_RANGE_FACTORS)
    return float(f"{low:.6g}"), float(f"{high:.6g}"), float(f"{(high - low) / steps:.6g}")


def _evidence_flags(result: dict) -> list[str]:
    """Platform self-reported quality signals, recorded verbatim."""
    summary, selection = result.get("summary") or {}, result.get("selection") or {}
    flags = []
    if not selection.get("recommended"):
        flags.append("平台未推荐(recommended=false)")
    if summary.get("sampleSufficient") is False:
        flags.append(f"样本量不足({summary.get('evaluatedTrials')} trials)")
    evaluated, pruned = summary.get("evaluatedTrials") or 0, summary.get("prunedTrials") or 0
    if evaluated and pruned / evaluated > 0.5:
        flags.append(f"剪枝比例过高({pruned}/{evaluated})")
    return flags


def judge_candidate(platform: Platform, source_id: int, candidate: dict,
                    windows: list[tuple[str, str, str]], run: dict, leverage: float) -> dict:
    """Backtest one candidate on every selection window at ``leverage``."""
    judged = {key: candidate[key] for key in ("rank", "trial", "params", "platform_score",
                                              "geometry")}
    judged["leverage"] = leverage
    judged["windows"] = []
    for label, start, end in windows:
        metrics = platform.backtest(source_id, start, end, candidate["params"], run,
                                    leverage=leverage)
        metrics.pop("executions")
        metrics["qualification"], metrics["reasons"] = judge_window(metrics)
        metrics.update({"window": label, "start": start, "end": end})
        judged["windows"].append(metrics)
        print(f"G5 {leverage}x #{judged['rank']} {label} run{metrics['runId']} "
              f"ret={metrics['margin_return_pct']:.2f}% mdd={metrics['max_drawdown_pct']:.2f}% "
              f"ge={metrics['worst_gross_to_equity']:.2f} liq={metrics['liquidated']} "
              f"-> {metrics['qualification']}", flush=True)
    return judged


def run_evolution(*, contract: str, instrument: str, lower: float, upper: float,
                  gap_pct: float, lower_range: tuple, upper_range: tuple,
                  evolve_start: str, evolve_end: str, holdout_start: str,
                  holdout_end: str, platform: Platform, evidence: Path,
                  timeframe: str = "1h", trials: int = 32, folds: int = 4, seed: int = 42,
                  top: int = 5, run: dict,
                  fallback_leverages: tuple[float, ...] = FALLBACK_LEVERAGES) -> dict:
    """Run the full gated grid-evolution sequence for one contract."""
    source, manifest = ges.generate_evolve_source(
        instrument=instrument, timeframe=timeframe, lower=lower, upper=upper, gap_pct=gap_pct,
        search_ranges={"grid_lower": lower_range, "grid_upper": upper_range},
        cell_id=f"{contract}-EVOLVE")
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "strategy.py").write_text(source, encoding="utf-8")
    record: dict = {"contract": contract, "instrument": instrument,
                    "baseline_geometry": manifest["executed_geometry"],
                    "evolve_period": [evolve_start, evolve_end],
                    "holdout_period": [holdout_start, holdout_end], "run": run}

    def save() -> None:
        (evidence / "evolution-record.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    # G1 compile + create the private source
    compiled = platform.call("POST", "/api/strategies/script-sources/compile", {"code": source})
    if compiled.get("code") != 1:
        raise EvolutionError(f"G1 compile failed: {compiled.get('msg')}")
    created = platform.call("POST", "/api/strategies/script-sources/create", {
        "code": source, "name": f"{contract}-GRID-EVOLVE", "visibility": "private",
        "status": "draft", "description": "strategy-lab parameterised grid evolution"})
    source_id = (created.get("data") or {}).get("id")
    if not source_id:
        raise EvolutionError(f"G1 source creation failed: {created.get('msg')}")
    record["sourceId"] = source_id
    print(f"G1 compile OK, sourceId={source_id}", flush=True)

    # G2 parameter space
    space = platform.call("GET", "/api/strategy-evolution/parameter-space",
                          params={"sourceId": source_id})
    parsed = {row.get("name"): row for row in (space.get("data") or {}).get("parameters") or []}
    if set(parsed) != {"grid_lower", "grid_upper", "grid_gap_pct"}:
        raise EvolutionError(f"G2 parameter space is {sorted(parsed)}")
    # The platform must read back exactly the declared ranges; a parser
    # mismatch silently collapses a dimension to one value.
    for name, spec in manifest["parameter_declarations"].items():
        row = parsed[name]
        if any(abs(float(row[key]) - float(spec[key])) > 1e-9 * max(1.0, abs(spec[key]))
               for key in ("min", "max", "step")):
            raise EvolutionError(f"G2 {name} parsed as {row['min']}:{row['max']}:{row['step']}, "
                                 f"declared {spec['min']}:{spec['max']}:{spec['step']}")
    print("G2 parameter space OK", flush=True)

    # G3 parameters take effect (two spacings on the most recent selection window)
    windows = quarterly_windows(evolve_start, evolve_end, first_label=2)
    probe_start, probe_end = windows[0][1], windows[0][2]
    probes = [platform.backtest(source_id, probe_start, probe_end,
                                {"grid_lower": lower, "grid_upper": upper, "grid_gap_pct": gap},
                                run)
              for gap in (ge.GAP_MIN_PCT, ge.GAP_MAX_PCT)]
    if len({(p["margin_return_pct"], p["pairs"]) for p in probes}) < 2:
        raise EvolutionError("G3 failed: different parameters produced identical results")
    record["g3_probe_runs"] = [p["runId"] for p in probes]
    print(f"G3 parameter effect OK (runIds {record['g3_probe_runs']})", flush=True)

    # G4 native evolution
    config = {"method": "tpe", "trials": trials, "folds": folds, "blindRatio": 0.15,
              "seed": seed, "costMultipliers": [1.0], "topCandidates": top,
              "monteCarloPaths": 100}
    # No ``weights``: the platform ranks by OOS compounded return only
    # (engine.py ``score = components["oosReturn"]``); weights change a
    # display-only quality score, so passing them would only mislead.
    submitted = platform.call("POST", "/api/strategy-evolution/run", {
        "sourceId": source_id, "startDate": evolve_start, "endDate": evolve_end,
        "initialCapital": run["capital"], "commission": run["commission"],
        "slippage": run["slippage"], "leverageEnabled": True, "leverage": run["leverage"],
        "parameterSpace": ges.build_param_space(manifest), "config": config})
    job = (submitted.get("data") or {}).get("jobId")
    if not job:
        raise EvolutionError(f"G4 evolution submit failed: {submitted.get('msg')}")
    record["evolutionJobId"] = job
    print(f"G4 evolution job {job} submitted", flush=True)
    state = platform.wait(f"/api/strategy-evolution/jobs/{job}", poll_seconds=15, max_polls=160)
    if str(state.get("status")).lower() != "succeeded":
        raise EvolutionError(f"G4 evolution {state.get('status')}")
    result = state.get("result") or {}
    (evidence / "evolution-result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    record["platform"] = {"summary": result.get("summary"), "selection": result.get("selection"),
                          "flags": _evidence_flags(result)}
    candidates = [{"rank": index + 1, "trial": c.get("number"), "params": c.get("params"),
                   "platform_score": c.get("score")}
                  for index, c in enumerate((result.get("topCandidates") or [])[:top])]
    if not candidates:
        raise EvolutionError("G4 returned no candidates")
    save()
    print(f"G4 done: {len(candidates)} candidates, flags={record['platform']['flags']}",
          flush=True)

    # G5 judge every candidate on every selection window at the run leverage
    for candidate in candidates:
        params = candidate["params"]
        candidate["geometry"] = ge.resolve_from_gap(
            params["grid_lower"], params["grid_upper"], params["grid_gap_pct"]).to_dict()
    tiers = [run["leverage"]] + [lev for lev in fallback_leverages if lev < run["leverage"]]
    record["leverage_tiers"] = []
    winner = None
    for leverage in tiers:
        judged = [judge_candidate(platform, source_id, candidate, windows, run, leverage)
                  for candidate in candidates]
        winner = select_candidate(judged)
        record["leverage_tiers"].append({"leverage": leverage, "candidates": judged,
                                         "winner_rank": winner["rank"] if winner else None})
        save()
        if winner:
            break
        print(f"G5 no qualified candidate at {leverage}x", flush=True)
    record["winner_rank"] = winner["rank"] if winner else None
    record["winner_leverage"] = winner["leverage"] if winner else None
    save()
    if winner is None:
        print("G5 no qualified candidate at any leverage tier", flush=True)
        return record
    print(f"G5 winner: #{winner['rank']} {winner['params']} at {winner['leverage']}x "
          f"mean={winner['mean_return_pct']:.2f}%", flush=True)

    # G6 held-out window, reported only
    holdout = platform.backtest(source_id, holdout_start, holdout_end, winner["params"], run,
                                leverage=winner["leverage"])
    holdout["average_amount_per_grid"] = _mean_cell_notional(holdout.pop("executions"))
    holdout["qualification"], holdout["reasons"] = judge_window(holdout)
    holdout.update({"window": "W1", "start": holdout_start, "end": holdout_end,
                    "leverage": winner["leverage"]})
    record["holdout"] = holdout
    save()
    print(f"G6 holdout W1 run{holdout['runId']} ret={holdout['margin_return_pct']:.2f}% "
          f"mdd={holdout['max_drawdown_pct']:.2f}% -> {holdout['qualification']}", flush=True)
    return record


def _mean_cell_notional(executions: list[dict]) -> float | None:
    import grid_research as gr
    return gr.average_amount_per_grid(executions)[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "describe"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--contract", required=True)
        cmd.add_argument("--instrument", required=True)
        cmd.add_argument("--lower", type=float, required=True, help="baseline L")
        cmd.add_argument("--upper", type=float, required=True, help="baseline U")
        cmd.add_argument("--gap-pct", type=float, required=True, help="baseline spacing, %%")
        cmd.add_argument("--lower-range", type=parse_range,
                         help="min:max:step; default baseline x [0.5, 1.5]")
        cmd.add_argument("--upper-range", type=parse_range,
                         help="min:max:step; default baseline x [0.5, 1.5]")
        cmd.add_argument("--fallback-leverages", default=",".join(map(str, FALLBACK_LEVERAGES)),
                         help="comma-separated, descending; empty disables the fallback")
        cmd.add_argument("--evolve-start", required=True)
        cmd.add_argument("--evolve-end", required=True)
        cmd.add_argument("--holdout-start", required=True)
        cmd.add_argument("--holdout-end", required=True)
        cmd.add_argument("--trials", type=int, default=32)
        cmd.add_argument("--top", type=int, default=5)
        cmd.add_argument("--seed", type=int, default=42)
        cmd.add_argument("--leverage", type=int, default=10)
        cmd.add_argument("--capital", type=float, default=1000.0)
        cmd.add_argument("--budget", type=int, default=BACKTEST_BUDGET)
        cmd.add_argument("--base-url", default=DEFAULT_BASE_URL)
        cmd.add_argument("--evidence-dir", type=Path)
    args = parser.parse_args(argv)
    args.lower_range = args.lower_range or default_range(args.lower)
    args.upper_range = args.upper_range or default_range(args.upper)
    fallback = tuple(float(x) for x in args.fallback_leverages.split(",") if x.strip())
    if list(fallback) != sorted(fallback, reverse=True) or any(x >= args.leverage for x in fallback):
        print("--fallback-leverages must be descending and below --leverage", file=sys.stderr)
        return 64
    windows = quarterly_windows(args.evolve_start, args.evolve_end, first_label=2)
    per_tier = args.top * len(windows)
    needed = 2 + per_tier * (1 + len(fallback)) + 1
    if args.command == "describe":
        print(json.dumps({
            "baseline": ge.resolve_from_gap(args.lower, args.upper, args.gap_pct).to_dict(),
            "selection_windows": windows,
            "holdout": [args.holdout_start, args.holdout_end],
            "search_ranges": {"grid_lower": args.lower_range, "grid_upper": args.upper_range},
            "leverage": args.leverage, "fallback_leverages": fallback,
            "backtests_needed_worst_case": needed, "budget": args.budget},
            ensure_ascii=False, indent=1))
        return 0
    # The platform treats endDate as inclusive (the evolution plan's last bar
    # is evolve_end 23:00), so a held-out window starting on evolve_end
    # shares that day with the evolution data.
    if args.holdout_start <= args.evolve_end:
        print(f"warning: holdout starts {args.holdout_start}, the platform includes "
              f"evolve_end {args.evolve_end} in the evolution data; the held-out "
              "window overlaps it by one day", file=sys.stderr)
    if needed > args.budget:
        print(f"budget {args.budget} < worst case {needed}; lower --top or tiers",
              file=sys.stderr)
        return 5
    token = (os.environ.get("QUANTDINGER_JWT") or "").strip()
    if not token:
        print("export QUANTDINGER_JWT before running", file=sys.stderr)
        return 4
    evidence = args.evidence_dir or (
        REPORTS_ROOT / f"{date.today().isoformat()}-{args.contract.lower()}-grid-evolve"
        / "evidence")
    try:
        record = run_evolution(
            contract=args.contract, instrument=args.instrument, lower=args.lower,
            upper=args.upper, gap_pct=args.gap_pct, lower_range=args.lower_range,
            upper_range=args.upper_range, evolve_start=args.evolve_start,
            evolve_end=args.evolve_end, holdout_start=args.holdout_start,
            holdout_end=args.holdout_end, trials=args.trials, seed=args.seed, top=args.top,
            platform=Platform(token, args.base_url, args.budget), evidence=evidence,
            fallback_leverages=fallback,
            run={"capital": args.capital, "commission": 0.0005, "slippage": 0.0005,
                 "leverage": args.leverage})
    except EvolutionError as error:
        print(f"GATE FAILED: {error}", file=sys.stderr)
        return 2
    print(json.dumps({"sourceId": record.get("sourceId"), "winner": record.get("winner_rank"),
                      "winner_leverage": record.get("winner_leverage"),
                      "evidence": str(evidence)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
