"""Grafana dashboard management — public API.

Two layers:

  :class:`GrafanaApiClient` — low-level HTTP wrapper around Grafana's
  Kubernetes-style dashboard API.

  :class:`DashboardManager` — higher-level: takes pre-assembled
  dashboard JSON, runs upsert / list / get / delete.

Typical usage::

    from mos.core.grafana import GrafanaApiClient, DashboardManager

    client = GrafanaApiClient(
        server_url="https://grafana.example.com",
        api_key="...",
        namespace="mos",
    )
    mgr = DashboardManager(client)
    mgr.deploy("etf-overview", {"title": "ETF Overview", "panels": [...]})
"""

from mos.core.grafana.manage import (
    DashboardManager,
    DeployOutcome,
    GrafanaApiClient,
    UploadResult,
)

__all__ = [
    "DashboardManager",
    "DeployOutcome",
    "GrafanaApiClient",
    "UploadResult",
]
