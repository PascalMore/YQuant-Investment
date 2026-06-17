"""Batch summary and closeout helpers for Smart Money pipeline runs."""
from __future__ import annotations

from typing import Any


def summarize_batch_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize per-file pipeline results into a batch-level report."""
    summary = {
        "total": len(results),
        "success": 0,
        "partial_success": 0,
        "pending_review": 0,
        "failed": 0,
        "dry_run": 0,
        "pending_rows": 0,
        "accepted_rows": 0,
        "mongodb": {},
        "needs_confirmation": [],
        "closeout_status": "success",
        "items": [],
    }

    for item in results:
        status = item.get("status") or ("failed" if item.get("error") else "success")
        if status not in {"success", "partial_success", "pending_review", "failed", "dry_run"}:
            status = "failed" if item.get("error") else "success"
        if status in summary:
            summary[status] += 1

        review = item.get("review") or {}
        summary["pending_rows"] += int(review.get("pending_rows") or 0)
        summary["accepted_rows"] += int(review.get("accepted_rows") or item.get("rows") or 0)

        for key, value in (item.get("mongodb") or {}).items():
            if isinstance(value, int):
                summary["mongodb"][key] = summary["mongodb"].get(key, 0) + value

        pending_files = review.get("pending_files") or {}
        if item.get("pending") and not pending_files:
            pending_files = {
                key: item["pending"][key]
                for key in ("csv", "json")
                if item["pending"].get(key)
            }

        summary_item = {
            "source": item.get("source") or item.get("image") or item.get("txt") or item.get("excel_path"),
            "format": item.get("format"),
            "status": status,
            "rows": item.get("rows"),
            "accepted_rows": review.get("accepted_rows"),
            "pending_rows": review.get("pending_rows"),
            "pending_files": pending_files,
            "error": item.get("error"),
        }
        summary["items"].append(summary_item)

        if int(review.get("pending_rows") or 0) > 0:
            summary["needs_confirmation"].append({
                "type": "pending_review",
                "source": summary_item["source"],
                "rows": int(review.get("pending_rows") or 0),
                "pending_files": pending_files,
                "message": "存在待人工复核记录，确认后再补录或标记 resolved",
            })
        if status == "failed":
            summary["needs_confirmation"].append({
                "type": "failed",
                "source": summary_item["source"],
                "error": item.get("error"),
                "message": "文件处理失败，需要重跑、人工转写或排查源文件",
            })

    if summary["failed"] or summary["pending_review"] or summary["partial_success"] or summary["needs_confirmation"]:
        summary["closeout_status"] = "attention_required"
    if summary["total"] == 0:
        summary["closeout_status"] = "no_files"

    return summary


def format_batch_summary(summary: dict[str, Any]) -> str:
    """Format a concise human-readable batch summary."""
    lines = [
        "Smart Money Pipeline Batch Summary",
        f"- total files: {summary.get('total', 0)}",
        f"- success: {summary.get('success', 0)}",
        f"- partial_success: {summary.get('partial_success', 0)}",
        f"- pending_review: {summary.get('pending_review', 0)}",
        f"- failed: {summary.get('failed', 0)}",
        f"- accepted rows: {summary.get('accepted_rows', 0)}",
        f"- pending rows: {summary.get('pending_rows', 0)}",
    ]
    if summary.get("mongodb"):
        db_counts = ", ".join(f"{key}={value}" for key, value in sorted(summary["mongodb"].items()))
        lines.append(f"- mongodb: {db_counts}")

    pending_items = [item for item in summary.get("items", []) if item.get("pending_rows")]
    if pending_items:
        lines.append("- pending files:")
        for item in pending_items:
            files = item.get("pending_files") or {}
            lines.append(
                f"  - {item.get('source')}: rows={item.get('pending_rows')} "
                f"csv={files.get('csv', '')}"
            )

    failed_items = [item for item in summary.get("items", []) if item.get("status") == "failed"]
    if failed_items:
        lines.append("- failed files:")
        for item in failed_items:
            lines.append(f"  - {item.get('source')}: {item.get('error')}")

    closeout = build_batch_closeout(summary)
    lines.append(f"- closeout status: {closeout['status']}")
    lines.append(f"- confirmation: {closeout['confirmation']['question']}")

    return "\n".join(lines)


def build_batch_closeout(summary: dict[str, Any]) -> dict[str, Any]:
    """Build structured batch closeout from batch summary.

    Returns a dict with:
    - kind: "smart_money_batch_closeout"
    - status: "closed_clean" | "closed_needs_confirmation" | "closed_with_failures" | "closed_dry_run" | "closed_empty"
    - totals: {...}
    - mongodb_counts: dict[str, int]
    - needs_confirmation_items: [...]
    - failed_items: [...]
    - confirmation: {required, reason, question, expected_user_action}
    - message_text: str (formatted Chinese text ready for chat)
    """
    totals = {
        "files": summary.get("total", 0),
        "success": summary.get("success", 0),
        "partial_success": summary.get("partial_success", 0),
        "pending_review": summary.get("pending_review", 0),
        "failed": summary.get("failed", 0),
        "dry_run": summary.get("dry_run", 0),
        "accepted_rows": summary.get("accepted_rows", 0),
        "pending_rows": summary.get("pending_rows", 0),
    }

    needs_confirmation_items = []
    for item in summary.get("items", []):
        pending_rows = item.get("pending_rows") or 0
        status = item.get("status") or ""
        if pending_rows > 0 or status in {"partial_success", "pending_review"}:
            pending_files = item.get("pending_files") or {}
            needs_confirmation_items.append({
                "source": item.get("source"),
                "status": status,
                "pending_rows": pending_rows,
                "pending_files": {
                    "csv": pending_files.get("csv"),
                    "json": pending_files.get("json"),
                },
                "reason": "存在待人工复核记录，确认后再补录或标记 resolved",
            })

    failed_items = []
    for item in summary.get("items", []):
        if item.get("status") == "failed" or item.get("error"):
            failed_items.append({
                "source": item.get("source"),
                "status": "failed",
                "error": item.get("error"),
            })

    # MongoDB counts — only sum int values
    mongodb_counts: dict[str, int] = {}
    for key, value in summary.get("mongodb", {}).items():
        if isinstance(value, int):
            mongodb_counts[key] = value

    # Status classification — priority order per SPEC-03-005 §4.4
    files = totals["files"]
    if files == 0:
        status = "closed_empty"
        confirmation_reason = "empty_batch"
        expected_action = "none"
        confirmation_question = "本批次未发现待处理文件，无需确认。"
        confirmation_required = False
    elif failed_items or totals["failed"] > 0:
        status = "closed_with_failures"
        confirmation_reason = "failed"
        expected_action = "retry_or_ignore_failures"
        n = len(failed_items) or totals["failed"]
        confirmation_question = f"本批次有 {n} 个文件处理失败。请确认：是否重试失败文件，还是忽略并关闭本批次？"
        confirmation_required = True
    elif totals["pending_rows"] > 0 or totals["partial_success"] > 0 or totals["pending_review"] > 0:
        status = "closed_needs_confirmation"
        confirmation_reason = "pending_review"
        expected_action = "confirm_pending_resolution"
        n = totals["pending_rows"]
        confirmation_question = (
            f"本批次仍有 {n} 行需要人工确认。"
            f"请确认：是否按 pending 文件修正后补录，还是暂不入库并保留为待处理？"
        )
        confirmation_required = True
    elif totals["dry_run"] > 0:
        status = "closed_dry_run"
        confirmation_reason = "dry_run"
        expected_action = "acknowledge_dry_run"
        confirmation_question = "本批次为 dry-run，未执行正式入库。请确认：是否按该结果执行正式入库流程？"
        confirmation_required = True
    else:
        status = "closed_clean"
        confirmation_reason = "clean_closeout"
        expected_action = "confirm_archive"
        confirmation_question = "本批次已全部成功入库且无 pending/failed。请确认：是否将本批次标记为已复核完成？"
        confirmation_required = True

    closeout: dict[str, Any] = {
        "kind": "smart_money_batch_closeout",
        "status": status,
        "totals": totals,
        "mongodb_counts": mongodb_counts,
        "needs_confirmation_items": needs_confirmation_items,
        "failed_items": failed_items,
        "confirmation": {
            "required": confirmation_required,
            "reason": confirmation_reason,
            "question": confirmation_question,
            "expected_user_action": expected_action,
        },
    }

    closeout["message_text"] = _format_batch_closeout_text(closeout)
    return closeout


def _format_batch_closeout_text(closeout: dict[str, Any]) -> str:
    """Format closeout dict as user-facing Chinese text."""
    totals = closeout["totals"]
    status = closeout["status"]
    confirmation = closeout["confirmation"]

    lines = [
        "Smart Money 批次处理 Closeout",
        "",
        f"状态：{status}",
        f"文件：total={totals['files']}, success={totals['success']}, "
        f"partial_success={totals['partial_success']}, pending_review={totals['pending_review']}, "
        f"failed={totals['failed']}, dry_run={totals['dry_run']}",
        f"行数：accepted={totals['accepted_rows']}, pending={totals['pending_rows']}",
    ]

    mongodb_counts = closeout.get("mongodb_counts") or {}
    if mongodb_counts:
        db_parts = ", ".join(f"{k}={v}" for k, v in sorted(mongodb_counts.items()))
        lines.append(f"入库：{db_parts}")
    else:
        lines.append("入库：无")

    needs_confirmation_items = closeout.get("needs_confirmation_items") or []
    failed_items = closeout.get("failed_items") or []

    if needs_confirmation_items:
        lines.append("")
        lines.append("待确认：")
        display_items = needs_confirmation_items[:10]
        for item in display_items:
            source = item.get("source") or "<unknown>"
            pending_rows = item.get("pending_rows") or 0
            pending_files = item.get("pending_files") or {}
            csv_path = pending_files.get("csv") or ""
            lines.append(f"- {source}: pending_rows={pending_rows}, csv={csv_path}")
        if len(needs_confirmation_items) > 10:
            lines.append(f"... 还有 {len(needs_confirmation_items) - 10} 项未展示")

        # F-008: 补录命令提示
        lines.append("")
        lines.append("补录命令：确认后运行")
        lines.append("  python3 load_pending_confirmed.py --date <批次日期>")
        lines.append("或逐文件处理：")
        lines.append("  python3 load_pending_confirmed.py --csv <pending_csv路径>")

    if failed_items:
        lines.append("")
        lines.append("失败：")
        display_items = failed_items[:10]
        for item in display_items:
            source = item.get("source") or "<unknown>"
            error = item.get("error") or ""
            lines.append(f"- {source}: {error}")
        if len(failed_items) > 10:
            lines.append(f"... 还有 {len(failed_items) - 10} 项未显示")

    lines.append("")
    lines.append(f"确认问题：{confirmation.get('question', '')}")

    return "\n".join(lines)


def format_batch_closeout(
    summary_or_closeout: dict[str, Any],
    batch_label: str = "本批 Smart Money 数据",
) -> str:
    """Format an operator-facing closeout message for chat confirmation.

    Accepts either a raw ``summary`` dict (legacy) or a pre-built ``closeout`` dict.
    When a summary dict is passed, ``build_batch_closeout`` is called first.
    """
    if summary_or_closeout.get("kind") == "smart_money_batch_closeout":
        closeout = summary_or_closeout
    else:
        closeout = build_batch_closeout(summary_or_closeout)
    return closeout["message_text"]
