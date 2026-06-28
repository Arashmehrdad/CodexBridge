from __future__ import annotations

from pathlib import Path

from codexbridge.config import AppConfig, DashboardConfig, load_config

from .data_sources import get_dashboard_summary
from .models import DashboardHealthResult
from .render import render_dashboard_html


def create_dashboard_app(config: AppConfig | None = None):
    try:
        from fastapi import FastAPI
        from fastapi.responses import HTMLResponse
    except (
        Exception
    ) as exc:  # pragma: no cover - exercised only without FastAPI installed
        raise RuntimeError(
            f"FastAPI is not available for the dashboard: {exc}"
        ) from exc

    settings = config.dashboard if config else DashboardConfig()
    runs_dir = config.resolve_dashboard_runs_dir() if config else Path.cwd() / "runs"
    app = FastAPI(
        title="CodexBridge Dashboard",
        version="1",
        docs_url=None if settings.dashboard_read_only else "/docs",
    )

    def summary():
        return get_dashboard_summary(
            runs_dir,
            limit=settings.dashboard_max_items,
            max_file_bytes=settings.dashboard_max_file_bytes,
            include_memory=settings.dashboard_include_memory,
            include_repo_status=settings.dashboard_include_repo_status,
        )

    @app.get("/health")
    def health():
        return DashboardHealthResult(
            ok=True, read_only=True, runs_dir=runs_dir
        ).model_dump(mode="json")

    @app.get("/", response_class=HTMLResponse)
    def index():
        return render_dashboard_html(summary())

    @app.get("/api/summary")
    def api_summary():
        return summary().to_dict()

    @app.get("/api/runs")
    def api_runs():
        return [item.to_dict() for item in summary().runs]

    @app.get("/api/jobs")
    def api_jobs():
        return [item.to_dict() for item in summary().jobs]

    @app.get("/api/supervisors")
    def api_supervisors():
        return [item.to_dict() for item in summary().supervisors]

    @app.get("/api/approvals")
    def api_approvals():
        return [item.to_dict() for item in summary().approvals]

    @app.get("/api/codex-escalations")
    def api_codex_escalations():
        return [item.to_dict() for item in summary().codex_escalations]

    @app.get("/api/return-loop")
    def api_return_loop():
        return [item.to_dict() for item in summary().return_loop]

    @app.get("/api/local-coding")
    def api_local_coding():
        return [item.to_dict() for item in summary().local_coding]

    @app.get("/api/memory")
    def api_memory():
        return summary().memory.model_dump(mode="json")

    return app


def main() -> None:
    try:
        import uvicorn
    except Exception as exc:  # pragma: no cover
        raise SystemExit(f"uvicorn is required to serve the dashboard: {exc}") from exc

    config = load_config(validate_repos=False)
    uvicorn.run(
        create_dashboard_app(config),
        host=config.dashboard.dashboard_host,
        port=config.dashboard.dashboard_port,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
