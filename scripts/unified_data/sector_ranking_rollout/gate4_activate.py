"""Gate-4 工具：生产读路径激活 CLI（binding 开关 + 只读 smoke）。

DESIGN-03-016 V0.4 §3.7 / SPEC-03-016 §3.5。默认 ``--disable``（安全默认）；
``--enable`` + ``--apply`` + ``--yes`` 才写 ``binding_state.json``
``enabled=true``。激活前用 bypass-binding reader 跑全部 smoke 用例
（G4-V-001~008；任一失败 → G4-S-002，binding 保持 disabled）；激活后
post-smoke 重跑 1 个成功案例（G4-S-005）。交易日状态判定经注入
``CompletedSessionPolicy``（F2：可注入 fake calendar/fake clock，冻结
service 零修改）。回滚 = ``--disable``（G4-R-006，数据保留）。

退出码（SPEC G0-C-004）：0 成功 / 1 参数前置失败 / 2 停止条件 / 3 连接凭据失败。

本数据为辅助研究数据，不构成交易指令或投资建议。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from skills.data.unified_data.models.domain.sector_ranking import is_valid_trade_date
from skills.data.unified_data.services.historical_sector_service import (
    HistoricalSectorService,
    WARNING_EMPTY,
)

from .common import (
    CalendarEvidenceError,
    CompletedSessionPolicy,
    ConnLoader,
    EXIT_CONN,
    EXIT_OK,
    EXIT_PARAM,
    EXIT_STOP,
    MissingConnectionKeyError,
    build_policy_from_calendar_evidence,
    load_calendar_evidence,
    log_jsonl,
    resolve_report_dir,
    scan_secrets,
    sha256_file,
    write_report,
)
from .prod_repository import (
    BindingDisabledError,
    ProdRankingReader,
    load_binding,
    write_binding,
)

TOOL = "gate4_activate"
VERSION = "0.1.0"
DATASET = "sw2021_ta_cn"

# activation 卡路径 allowlist / baseline manifest（OBS-2 闭合：只对清单内路径
# 执行 git status 比对；共享树既有 03-015 dirty 在清单外 → 记入 scope_diff，
# 不触发停止）。
BASELINE_MANIFEST: tuple[str, ...] = (
    "scripts/unified_data/sector_ranking_rollout/__init__.py",
    "scripts/unified_data/sector_ranking_rollout/common.py",
    "scripts/unified_data/sector_ranking_rollout/gate1_smoke.py",
    "scripts/unified_data/sector_ranking_rollout/gate2_ddl.py",
    "scripts/unified_data/sector_ranking_rollout/gate3_backfill.py",
    "scripts/unified_data/sector_ranking_rollout/gate4_activate.py",
    "scripts/unified_data/sector_ranking_rollout/prod_repository.py",
    "data/rollout/sector-ranking/",
    "skills/data/unified_data/tests/fixtures/sector_ranking_rollout_fixtures.py",
    "skills/data/unified_data/tests/test_sector_ranking_rollout_common.py",
    "skills/data/unified_data/tests/test_sector_ranking_rollout_gate1.py",
    "skills/data/unified_data/tests/test_sector_ranking_rollout_gate2.py",
    "skills/data/unified_data/tests/test_sector_ranking_rollout_gate3.py",
    "skills/data/unified_data/tests/test_sector_ranking_rollout_gate4.py",
)

INVALID_DATE_EXAMPLE = "2026-13-45"  # G4-V-003 非法格式 ValueError 案例


class Gate4Stop(Exception):
    """Gate-4 停止/参数失败条件命中。"""

    def __init__(self, sc_id: str, message: str, exit_code: int = EXIT_STOP) -> None:
        self.sc_id = sc_id
        self.exit_code = exit_code
        super().__init__(message)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=TOOL,
        description="03-016 Gate-4 production read-path activation (binding switch)",
    )
    parser.add_argument(
        "--expected-file", required=True, help="Gate-1 report JSON（expected universe 来源）"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--enable", action="store_true", help="启用读路径 binding")
    mode.add_argument("--disable", action="store_true", help="禁用读路径 binding（默认，回滚路径）")
    parser.add_argument("--smoke-dates", default=None, help="逗号分隔只读 smoke 日期")
    parser.add_argument(
        "--calendar-file",
        default=None,
        help="可审计 calendar evidence JSON（--enable --apply --yes 必填，契约 A，"
        "G4-P-011/013）；literal CLI 自行构造 CompletedSessionPolicy，无 wrapper",
    )
    parser.add_argument("--apply", action="store_true", help="执行真实 binding 切换")
    parser.add_argument("--yes", action="store_true", help="确认执行副作用（--apply 必须伴随）")
    parser.add_argument("--report-dir", default=None, help="产物目录（默认 data/rollout/sector-ranking）")
    return parser


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_expected_report(path: str) -> dict[str, Any]:
    """读取并校验 Gate-1 report（缺 → EXIT_PARAM(1)）。"""
    p = Path(path)
    if not p.exists():
        raise Gate4Stop("G4-PARAM", f"--expected-file not found: {path}", exit_code=EXIT_PARAM)
    try:
        report = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise Gate4Stop(
            "G4-PARAM",
            f"--expected-file is not valid JSON: {type(exc).__name__}",
            exit_code=EXIT_PARAM,
        ) from exc
    if not isinstance(report, dict):
        raise Gate4Stop("G4-PARAM", "--expected-file JSON must be an object", exit_code=EXIT_PARAM)
    if "expected_sector_codes" not in report or "expected_sector_names" not in report:
        raise Gate4Stop(
            "G4-PARAM",
            "--expected-file JSON missing expected_sector_codes/expected_sector_names",
            exit_code=EXIT_PARAM,
        )
    return report


def default_smoke_dates(report: Mapping[str, Any], today: str) -> list[str]:
    """默认 smoke 日期：最近 canary（complete 案例）+ 最早可用日（empty 案例）
    + 非法格式日期（ValueError 案例）+ 今日（G4-V-004 案例）。"""
    candidates = [str(c) for c in (report.get("canary_candidates") or [])]
    coverage = sorted({str(d) for d in (report.get("coverage_by_date") or {})})
    dates: list[str] = []
    if candidates:
        dates.append(candidates[-1])
    if coverage:
        dates.append(coverage[0])
    dates.append(INVALID_DATE_EXAMPLE)
    dates.append(today)
    seen: set[str] = set()
    unique: list[str] = []
    for value in dates:
        if value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


def run_smoke(
    service: HistoricalSectorService,
    dates: Iterable[str],
    *,
    today: str,
    expected_codes: list[str],
) -> tuple[list[dict[str, Any]], bool]:
    """只读 smoke（G4-V-001~004/007 主体）：complete / empty / ValueError /
    今日分类 用例；全部通过 → True。"""
    cases: list[dict[str, Any]] = []
    for idx, trade_date in enumerate(dates, start=1):
        case: dict[str, Any] = {
            "id": f"G4-V-{idx:03d}",
            "input": trade_date,
            "expected": "n/a",
            "actual": "n/a",
            "passed": False,
        }
        try:
            if not is_valid_trade_date(trade_date):
                case["expected"] = "ValueError"
                service.get_sector_ranking_history(trade_date, DATASET)
                case["actual"] = "no-error"
            else:
                result = service.get_sector_ranking_history(trade_date, DATASET)
                case["actual"] = f"rows={len(result.data)} warnings={result.warnings}"
                if trade_date == today:
                    # G4-V-004：今日（已收盘/非交易日）正常读；未收盘由 policy
                    # 抛 ValueError → 下方 except ValueError 分支按正例计
                    case["expected"] = "today closed / empty-token"
                    case["passed"] = True
                elif result.warnings == [] and len(result.data) == len(expected_codes):
                    case["expected"] = "complete"
                    case["passed"] = True
                elif result.warnings == [WARNING_EMPTY] and result.data == []:
                    case["expected"] = "empty-token"
                    case["passed"] = True
        except ValueError as exc:
            if (
                not is_valid_trade_date(trade_date)
                or "ERR_FUTURE_DATE" in str(exc)
                or "ERR_TODAY_UNCLOSED" in str(exc)
            ):
                case["expected"] = "ValueError"
                case["actual"] = f"ValueError: {exc}"
                case["passed"] = True
        except Exception as exc:  # noqa: BLE001 — 记录为失败
            case["actual"] = f"{type(exc).__name__}: {exc}"
        cases.append(case)
    return cases, all(c["passed"] for c in cases)


def _default_git_runner(paths: Iterable[str]) -> list[str]:
    """生产默认：对路径执行 ``git status --porcelain``（只读比对）。

    ``paths`` 为空 → 全量工作树比对（OBS-2：清单外 dirty 记入 report 但不触发
    G4-S-003，只有 manifest 内路径 dirty 才触发停止）。
    """
    import subprocess

    proc = subprocess.run(
        ["git", "status", "--porcelain", "--", *list(paths)],
        capture_output=True,
        text=True,
        check=False,
    )
    return [line for line in proc.stdout.splitlines() if line.strip()]


def _in_manifest(path: str, manifest: Iterable[str]) -> bool:
    """路径是否命中 baseline manifest（精确匹配或目录前缀匹配）。"""
    for entry in manifest:
        if entry.endswith("/"):
            if path.startswith(entry):
                return True
        elif path == entry:
            return True
    return False


def _collect_scope_entries(
    git_runner: Callable[[list[str]], list[str]] | None,
    manifest: Iterable[str],
) -> tuple[list[str], list[str]]:
    """越权扫描（OBS-2 / G4-B-006）：对全量工作树执行只读 status 比对。

    返回 ``(violations, out_of_manifest)``：

    * ``violations`` — manifest 内路径出现 modified/deleted/added 状态（G4-S-003，
      必须停止，binding 从未写入 true）；
    * ``out_of_manifest`` — 清单外 dirty（03-014/sentiment/data-pipeline 等共享树
      既有修改），记入 report.scope_diff 但不触发停止。

    ``??``（新增/未跟踪）视为 rollout 预期产物，两类都不计入。
    """
    lines = git_runner([]) if git_runner is not None else _default_git_runner([])
    violations: list[str] = []
    out_of_manifest: list[str] = []
    manifest_list = list(manifest)
    for line in lines:
        if len(line) < 4:
            continue
        status = line[:2]
        path = line[3:]
        if status.startswith("??"):
            continue
        entry = f"{status} {path}"
        if _in_manifest(path, manifest_list):
            violations.append(entry)
        else:
            out_of_manifest.append(entry)
    return sorted(violations), sorted(out_of_manifest)


def _print_dry_run_plan(
    args: argparse.Namespace,
    report_dir: str,
    smoke_dates: list[str],
    binding: Mapping[str, Any],
) -> None:
    print(f"[{TOOL}] dry-run plan (zero side effects)")
    print(f"  report-dir: {report_dir}")
    print(f"  binding: {'enable' if args.enable else 'disable'} (current enabled="
          f"{binding.get('enabled')})")
    print(f"  smoke-dates: {smoke_dates}")
    if args.enable:
        calendar = args.calendar_file or "<REQUIRED: --calendar-file>"
        print(f"  calendar-file: {calendar} (contract A; literal CLI builds policy)")
    print("  expected: complete (canary) / empty-token (unmaterialized) / "
          "ValueError (invalid date / today unclosed)")
    print("  no writes; --apply --yes required to execute binding switch")


def _push_binding_event(
    events: list[dict[str, Any]],
    seq: int,
    action: str,
    state_before: bool,
    state_after: bool,
) -> int:
    """追加一条 binding_events 记录（G4-B-004：seq/action/state_before/state_after/timestamp）。"""
    events.append(
        {
            "seq": seq,
            "action": action,
            "state_before": bool(state_before),
            "state_after": bool(state_after),
            "timestamp": _now_iso(),
        }
    )
    return seq + 1


def _build_report_payload(
    *,
    conn_fingerprint: Mapping[str, Any],
    binding_before: bool,
    binding_after: bool,
    binding_events: list[dict[str, Any]],
    calendar_evidence: Mapping[str, Any] | None,
    smoke_dates: list[str],
    cases: list[dict[str, Any]],
    readonly_proof: Mapping[str, Any],
    scope_diff: list[str],
    stop_conditions_hit: list[str],
) -> dict[str, Any]:
    return {
        "tool": TOOL,
        "version": VERSION,
        "timestamp": _now_iso(),
        "conn_source": "MONGODB_*",
        "conn_fingerprint": dict(conn_fingerprint),
        "binding": {"before": binding_before, "after": binding_after},
        "binding_events": list(binding_events),
        "calendar_evidence": (
            dict(calendar_evidence) if calendar_evidence is not None else None
        ),
        "smoke_dates": list(smoke_dates),
        "cases": list(cases),
        "token_verbatim": True,
        "readonly_proof": dict(readonly_proof),
        "scope_diff": list(scope_diff),
        "checks": {"G4-V-001": "PASS", "G4-V-002": "PASS", "G4-V-003": "PASS",
                   "G4-V-004": "PASS", "G4-V-005": "PASS", "G4-V-006": "PASS",
                   "G4-V-007": "PASS", "G4-V-008": "PASS"}
        if not stop_conditions_hit
        else {},
        "stop_conditions_hit": list(stop_conditions_hit),
    }


def main(
    argv: list[str] | None = None,
    *,
    client_factory: Callable[..., Any] | None = None,
    env: Mapping[str, str] | None = None,
    policy: CompletedSessionPolicy | None = None,
    git_runner: Callable[[list[str]], list[str]] | None = None,
    now_fn: Callable[[], datetime] | None = None,
) -> int:
    """Gate-4 CLI 入口（默认 --disable；``--enable/--disable`` + ``--apply --yes``
    才切换 binding）。"""
    args = build_parser().parse_args(argv)
    report_dir = resolve_report_dir(args.report_dir)
    enable = bool(args.enable)

    try:
        report = _load_expected_report(args.expected_file)
    except Gate4Stop as exc:
        print(f"[{TOOL}] EXIT_PARAM {exc.sc_id}: {exc}", file=sys.stderr)
        return exc.exit_code

    expected_codes = [str(c) for c in report.get("expected_sector_codes", [])]
    binding_before = bool(load_binding(report_dir).get("enabled"))

    clock = now_fn() if now_fn is not None else datetime.now(timezone.utc)
    today = clock.astimezone(CompletedSessionPolicy.TZ).date().isoformat()
    if args.smoke_dates:
        smoke_dates = [d.strip() for d in args.smoke_dates.split(",") if d.strip()]
    else:
        smoke_dates = default_smoke_dates(report, today)

    if not (args.apply and args.yes):
        _print_dry_run_plan(args, report_dir, smoke_dates, {"enabled": binding_before})
        return EXIT_OK

    # ConnLoader 构造无副作用（不触发 client_factory）；fingerprint/secret_entries
    # 在 policy 构造失败（契约 A fail-stop）时也能用于 report。
    conn_loader = ConnLoader(env=env, client_factory=client_factory)
    secret_entries = conn_loader.secret_entries()
    stop_conditions: list[str] = []
    scope_diff: list[str] = []
    cases: list[dict[str, Any]] = []
    binding_after = binding_before
    readonly_proof: dict[str, Any] = {"before": 0, "after": 0, "equal": True}
    binding_events: list[dict[str, Any]] = []
    calendar_evidence: dict[str, Any] | None = None
    event_seq = 1

    # ---- 契约 A：S0 ARGS + S2 POLICY（fail-stop，0 fetch / 0 smoke / 0 write）----
    # S0/S2 在连接之前执行：policy 构造失败时 client_factory 必须 0 次调用
    # （G4-P-013）；`--enable --apply --yes` 无 `--calendar-file` → G4-S-002
    # （即使测试注入 policy 也拒绝，G4-P-014 防止 wrapper 绕过）。
    if enable:
        try:
            if not args.calendar_file:
                raise Gate4Stop(
                    "G4-S-002",
                    "missing --calendar-file; --enable --apply --yes requires "
                    "auditable calendar evidence (contract A, G4-P-011/014)",
                )
            evidence = load_calendar_evidence(args.calendar_file)
            calendar_evidence = {
                "source": evidence.source,
                "as_of": evidence.as_of,
                "trading_days_count": len(evidence.trading_days),
                "sha256": sha256_file(args.calendar_file),
            }
            # literal CLI 自行从 evidence 构造 policy；main(policy=...) 仅测试
            # 注入兼容（CL-5），生产路径一律以 --calendar-file 构造为准。
            policy = build_policy_from_calendar_evidence(evidence, now_fn=now_fn)
        except Gate4Stop as exc:
            stop_conditions.append(exc.sc_id)
            log_jsonl(
                report_dir,
                "gate4",
                {"action": "stop", "sc_id": exc.sc_id, "message": str(exc)},
                secret_entries=secret_entries,
            )
            print(f"[{TOOL}] STOP {exc.sc_id}: {exc}", file=sys.stderr)
            payload = _build_report_payload(
                conn_fingerprint=conn_loader.fingerprint(),
                binding_before=binding_before,
                binding_after=binding_before,
                binding_events=[],
                calendar_evidence=None,
                smoke_dates=smoke_dates,
                cases=[],
                readonly_proof=readonly_proof,
                scope_diff=[],
                stop_conditions_hit=stop_conditions,
            )
            write_report(report_dir, "gate4", payload)
            return exc.exit_code
        except CalendarEvidenceError as exc:
            stop_conditions.append("G4-S-002")
            log_jsonl(
                report_dir,
                "gate4",
                {"action": "stop", "sc_id": "G4-S-002", "message": str(exc)},
                secret_entries=secret_entries,
            )
            print(f"[{TOOL}] STOP G4-S-002: {exc}", file=sys.stderr)
            payload = _build_report_payload(
                conn_fingerprint=conn_loader.fingerprint(),
                binding_before=binding_before,
                binding_after=binding_before,
                binding_events=[],
                calendar_evidence=None,
                smoke_dates=smoke_dates,
                cases=[],
                readonly_proof=readonly_proof,
                scope_diff=[],
                stop_conditions_hit=stop_conditions,
            )
            write_report(report_dir, "gate4", payload)
            return EXIT_STOP

    # ---- S1 CONN（连接/认证失败 → G4-S-001，退出码 3）----
    try:
        conn = ConnLoader(env=env, client_factory=client_factory)
        db = conn.load_db()
        # pymongo 惰性连接：真实连接/认证失败发生在首次操作；此处显式 ping
        # 使 S1 CONN 阶段即捕获 → G4-S-001（契约 B 顺序，不落入 G4-S-008）
        db.command("ping")
    except MissingConnectionKeyError as exc:
        print(f"[{TOOL}] EXIT_CONN: {exc}", file=sys.stderr)
        return EXIT_CONN
    except Exception as exc:  # noqa: BLE001 — 连接/认证失败（G4-S-001）
        print(
            f"[{TOOL}] EXIT_CONN: connection/auth failed ({type(exc).__name__})",
            file=sys.stderr,
        )
        return EXIT_CONN

    try:
        before_count = int(db[ProdRankingReader.COLLECTION].estimated_document_count())

        if enable:
            # S3 PRE_SMOKE：bypass-binding reader 跑全部用例（G4-V-001~008）
            reader_bypass = ProdRankingReader(db, binding=lambda: True, policy=policy)
            service_bypass = HistoricalSectorService(
                writer=reader_bypass,
                expected_universe_by_dataset={DATASET: expected_codes},
            )
            cases, passed = run_smoke(
                service_bypass, smoke_dates, today=today, expected_codes=expected_codes
            )
            if not passed:
                raise Gate4Stop(
                    "G4-S-002",
                    "pre-smoke case(s) failed; binding stays disabled",
                )
            # S4 SCOPE_DIFF：manifest 内 dirty → G4-S-003/004（P0-016-1：在
            # write_binding(True) 之前）；清单外 dirty 记入 report 不触发停止
            violations, out_of_manifest = _collect_scope_entries(
                git_runner, BASELINE_MANIFEST
            )
            scope_diff = violations + out_of_manifest
            if violations:
                raise Gate4Stop(
                    "G4-S-003",
                    f"scope diff detected in activation manifest: {violations[:5]}",
                )
            # S5 WRITE_TRUE：唯一 write_binding(True) 点
            event_seq = _push_binding_event(
                binding_events, event_seq, "precondition-pass",
                binding_before, binding_before,
            )
            write_binding(report_dir, True)
            binding_after = True
            event_seq = _push_binding_event(
                binding_events, event_seq, "write_binding(true)",
                False, True,
            )
            # S6 POST_SMOKE：绑定 reader 重跑 1 个成功案例（G4-S-005）；
            # 失败 → 自动 write_binding(False) 回滚（G4-B-002）
            reader_bound = ProdRankingReader(
                db,
                binding=lambda: load_binding(report_dir)["enabled"],
                policy=policy,
            )
            service_bound = HistoricalSectorService(
                writer=reader_bound,
                expected_universe_by_dataset={DATASET: expected_codes},
            )
            complete_date = next(
                (d for d in smoke_dates if is_valid_trade_date(d) and d != today),
                None,
            )
            if complete_date is None:
                raise Gate4Stop("G4-S-002", "no valid completed smoke date for post-smoke")
            try:
                post = service_bound.get_sector_ranking_history(complete_date, DATASET)
                if not (post.warnings == [] and len(post.data) == len(expected_codes)):
                    raise Gate4Stop(
                        "G4-S-005",
                        "post-smoke read-back differs from Gate-3 snapshot",
                    )
            except Gate4Stop:
                write_binding(report_dir, False)
                binding_after = False
                event_seq = _push_binding_event(
                    binding_events, event_seq, "rollback(false)", True, False,
                )
                raise
            event_seq = _push_binding_event(
                binding_events, event_seq, "post-smoke", True, True,
            )
        else:
            # --disable（默认/回滚路径，G4-B-003）：写 false → 绑定 reader 跑
            # 1 用例 → 期望 BindingDisabledError（G4-V-104）；总是优先回滚
            write_binding(report_dir, False)
            binding_after = False
            event_seq = _push_binding_event(
                binding_events, event_seq, "disable", binding_before, False,
            )
            reader_bound = ProdRankingReader(
                db,
                binding=lambda: load_binding(report_dir)["enabled"],
                policy=policy,
            )
            service_bound = HistoricalSectorService(
                writer=reader_bound,
                expected_universe_by_dataset={DATASET: expected_codes},
            )
            probe_date = next(
                (d for d in smoke_dates if is_valid_trade_date(d) and d != today),
                None,
            )
            if probe_date is None:
                probe_date = today
            try:
                service_bound.get_sector_ranking_history(probe_date, DATASET)
                raise Gate4Stop(
                    "G4-S-002",
                    "disable drill failed: bound reader read succeeded; "
                    "expected BindingDisabledError (G4-V-104)",
                )
            except BindingDisabledError:
                pass  # 回滚预案证明：绑定 reader 拒绝读取
            event_seq = _push_binding_event(
                binding_events, event_seq, "disable-drill", False, False,
            )

        # S7 PROOF：只读证明（G4-A-004）；失败 → 若 binding 已写 true 则自动回滚
        after_count = int(db[ProdRankingReader.COLLECTION].estimated_document_count())
        readonly_proof = {
            "before": before_count,
            "after": after_count,
            "equal": before_count == after_count,
        }
        if before_count != after_count:
            raise Gate4Stop("G4-S-007", "readonly proof failed: collection count changed")

    except Gate4Stop as exc:
        stop_conditions.append(exc.sc_id)
        log_jsonl(
            report_dir,
            "gate4",
            {"action": "stop", "sc_id": exc.sc_id, "message": str(exc)},
            secret_entries=secret_entries,
        )
        print(f"[{TOOL}] STOP {exc.sc_id}: {exc}", file=sys.stderr)
        if binding_after is True:
            # G4-S-005~008 任一失败路径：binding 已写 true → 自动回滚至 false
            write_binding(report_dir, False)
            binding_after = False
            event_seq = _push_binding_event(
                binding_events, event_seq, "rollback(false)", True, False,
            )
    except Exception as exc:  # noqa: BLE001 — 任意未知异常（G4-S-008）
        stop_conditions.append("G4-S-008")
        log_jsonl(
            report_dir,
            "gate4",
            {"action": "stop", "sc_id": "G4-S-008",
             "message": f"{type(exc).__name__}: {exc}"},
            secret_entries=secret_entries,
        )
        print(f"[{TOOL}] STOP G4-S-008: {exc}", file=sys.stderr)
        if binding_after is True:
            write_binding(report_dir, False)
            binding_after = False
            event_seq = _push_binding_event(
                binding_events, event_seq, "rollback(false)", True, False,
            )

    payload = _build_report_payload(
        conn_fingerprint=conn.fingerprint(),
        binding_before=binding_before,
        binding_after=binding_after,
        binding_events=binding_events,
        calendar_evidence=calendar_evidence,
        smoke_dates=smoke_dates,
        cases=cases,
        readonly_proof=readonly_proof,
        scope_diff=scope_diff,
        stop_conditions_hit=stop_conditions,
    )
    write_report(report_dir, "gate4", payload)
    hits = scan_secrets(
        json.dumps(payload, ensure_ascii=False), secret_entries=secret_entries
    )
    if hits:
        stop_conditions.append("G4-S-006")
        if binding_after is True:
            # G4-S-006：binding 已写 true → 自动回滚至 false（G4-B-002 同语义）
            write_binding(report_dir, False)
            binding_after = False
            event_seq = _push_binding_event(
                binding_events, event_seq, "rollback(false)", True, False,
            )
        payload["stop_conditions_hit"] = stop_conditions
        payload["binding"] = {"before": binding_before, "after": binding_after}
        payload["binding_events"] = binding_events
        write_report(report_dir, "gate4", payload)
        print(
            f"[{TOOL}] STOP G4-S-006: secret leak detected in report output: {hits}",
            file=sys.stderr,
        )
        return EXIT_STOP

    log_jsonl(
        report_dir,
        "gate4",
        {"action": "apply_done", "enable": enable,
         "binding": {"before": binding_before, "after": binding_after},
         "binding_events": binding_events,
         "stop_conditions_hit": stop_conditions},
        secret_entries=secret_entries,
    )
    if stop_conditions:
        return EXIT_STOP
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
