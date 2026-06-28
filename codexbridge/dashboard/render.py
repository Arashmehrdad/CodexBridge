from __future__ import annotations

import html

from .models import DashboardSummary


def render_dashboard_html(summary: DashboardSummary) -> str:
    sections = [
        (
            "Overall health",
            [
                f"ok={summary.health.ok}",
                f"read_only={summary.health.read_only}",
                f"runs_dir={summary.health.runs_dir}",
            ],
        ),
        ("Recent command runs", _lines(summary.commands)),
        ("Long-running jobs", _lines(summary.jobs)),
        ("Supervisors", _lines(summary.supervisors)),
        (
            "Pending approvals",
            _lines([item for item in summary.approvals if item.status == "pending"]),
        ),
        ("Codex escalations", _lines(summary.codex_escalations)),
        ("Return-loop / PulseSender readiness", _lines(summary.return_loop)),
        ("Local-coding previews/applications", _lines(summary.local_coding)),
        (
            "Memory overview",
            [
                f"records={summary.memory.total_records}",
                *(_lines(summary.memory.recent)),
            ],
        ),
        (
            "Current repo status",
            [summary.repo_status.summary or summary.repo_status.status],
        ),
    ]
    body = "\n".join(
        f"<section><h2>{html.escape(title)}</h2>{_list(items)}</section>"
        for title, items in sections
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>CodexBridge Dashboard</title>"
        "<style>body{font-family:system-ui,Segoe UI,sans-serif;margin:24px;max-width:1100px}"
        "section{border-top:1px solid #ddd;padding:12px 0}code{background:#f6f6f6;padding:2px 4px}"
        ".muted{color:#666}</style></head><body>"
        "<h1>CodexBridge Dashboard</h1><p class='muted'>Read-only local operations view.</p>"
        f"{body}</body></html>"
    )


def _lines(items) -> list[str]:
    lines = []
    for item in items:
        artifact = (
            f" artifact={item.artifact_path}"
            if getattr(item, "artifact_path", None)
            else ""
        )
        lines.append(
            f"{item.id} [{item.status}] {item.summary or item.failure_summary or item.error}{artifact}"
        )
    return lines or ["No items."]


def _list(items: list[str]) -> str:
    return (
        "<ul>"
        + "".join(f"<li><code>{html.escape(str(item))}</code></li>" for item in items)
        + "</ul>"
    )
