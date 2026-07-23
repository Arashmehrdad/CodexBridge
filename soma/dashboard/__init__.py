"""Read-only local dashboard for Soma run visibility."""

from .app import create_dashboard_app
from .data_sources import get_dashboard_summary
from .models import (
    DashboardApprovalSummary,
    DashboardCommandSummary,
    DashboardExternalCoderHandoffSummary,
    DashboardHealthResult,
    DashboardJobSummary,
    DashboardLocalCodingSummary,
    DashboardMemorySummary,
    DashboardRepoStatusSummary,
    DashboardReturnLoopSummary,
    DashboardRunSummary,
    DashboardSummary,
    DashboardSupervisorSummary,
)

__all__ = [
    "DashboardApprovalSummary",
    "DashboardCommandSummary",
    "DashboardExternalCoderHandoffSummary",
    "DashboardHealthResult",
    "DashboardJobSummary",
    "DashboardLocalCodingSummary",
    "DashboardMemorySummary",
    "DashboardRepoStatusSummary",
    "DashboardReturnLoopSummary",
    "DashboardRunSummary",
    "DashboardSummary",
    "DashboardSupervisorSummary",
    "create_dashboard_app",
    "get_dashboard_summary",
]
