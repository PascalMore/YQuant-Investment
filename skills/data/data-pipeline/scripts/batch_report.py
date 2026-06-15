"""Batch summary helpers for Smart Money pipeline runs."""
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
        "pending_rows": 0,
        "accepted_rows": 0,
        "mongodb": {},
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

        summary["items"].append({
            "source": item.get("source") or item.get("image") or item.get("txt") or item.get("excel_path"),
            "format": item.get("format"),
            "status": status,
            "rows": item.get("rows"),
            "accepted_rows": review.get("accepted_rows"),
            "pending_rows": review.get("pending_rows"),
            "pending_files": pending_files,
            "error": item.get("error"),
        })

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

    return "\n".join(lines)
