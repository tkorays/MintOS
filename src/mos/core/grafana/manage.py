"""Grafana dashboard management.

Two layers:

  :class:`GrafanaApiClient` — thin HTTP wrapper around Grafana's
  Kubernetes-style dashboard API (``dashboard.grafana.app/v1alpha1/...``).
  Handles auth, version discovery, JSON wrapping, atomic update of
  ``spec.version``. This is the primitive layer.

  :class:`DashboardManager` — higher-level manager that takes
  pre-assembled dashboard JSON from the caller (``deploy(name, json)``,
  ``deploy_many({name: json, ...})``) and runs the upsert / list / get /
  delete workflow. Use this for "I have a dict of dashboards, push
  them" cases.

Both classes are pure-HTTP — no CLI / no file IO. The caller assembles
dashboard JSON externally and feeds it in.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from typing import Any

import requests


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_server_url(url: str) -> str:
    """Strip trailing slash from a Grafana server URL.

    Examples:
        ``"https://grafana.example.com"``    -> ``"https://grafana.example.com"``
        ``"https://grafana.example.com/"``   -> ``"https://grafana.example.com"``
    """
    if not url:
        raise ValueError("Grafana server_url is empty")
    return url.rstrip("/")


def _title_slug(title: str) -> str:
    """Make a URL-safe slug for ``/d/<uid>/<slug>`` browser URLs.

    Lowercases, replaces non-alphanumeric runs with ``-``, collapses
    repeated dashes, and trims leading / trailing dashes.
    """
    if not title:
        return ""
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class UploadResult:
    """Typed return for create / update / upsert operations.

    Attributes:
        action: ``"created"`` or ``"updated"`` — which branch ran.
        name: Dashboard name (used as the K8s-style resource name).
        title: Dashboard title (from the response ``spec``).
        uid: Dashboard UID (same as ``name`` in our usage).
        version: Spec version counter returned by the server.
        resource_version: K8s metadata ``resourceVersion`` (etag-like).
        generation: K8s metadata ``generation``.
        url: Browser URL ``/d/<uid>/<slug>`` for human access.
        raw: Full response body for callers that need more fields.
    """

    action: str
    name: str
    title: str
    uid: str
    version: int | None
    resource_version: str | None
    generation: int | None
    url: str
    raw: dict[str, Any]


# ---------------------------------------------------------------------------
# Low-level HTTP client
# ---------------------------------------------------------------------------


class GrafanaApiClient:
    """HTTP client for Grafana's Kubernetes-style dashboard API.

    Bearer-token auth via API key, version auto-discovery on first
    request, uniform :class:`UploadResult` return shape for write
    operations. Read / delete return raw values or bool.
    """

    def __init__(
        self,
        server_url: str,
        api_key: str,
        namespace: str = "default",
        timeout: float = 20.0,
        verify: bool = True,
    ) -> None:
        if not api_key:
            raise ValueError("Grafana API key is empty")
        self.server_url = _normalize_server_url(server_url)
        self.api_key = api_key
        self.namespace = namespace
        self.api_version = ""
        self.timeout = timeout
        self.verify = verify
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    # ----- URL builders --------------------------------------------------

    def _base_dashboard_path(self) -> str:
        api_version = self.api_version or self.discover_dashboard_api_version()
        self.api_version = api_version
        return (
            f"/apis/dashboard.grafana.app/{api_version}"
            f"/namespaces/{self.namespace}/dashboards"
        )

    def _dashboard_url(self, name: str | None = None) -> str:
        base = f"{self.server_url}{self._base_dashboard_path()}"
        return f"{base}/{name}" if name else base

    def _browser_url(self, name: str, title: str) -> str:
        return f"{self.server_url}/d/{name}/{_title_slug(title)}"

    # ----- low-level response helpers ------------------------------------

    @staticmethod
    def _assert_success(
        response: requests.Response, ok_codes: tuple[int, ...]
    ) -> dict[str, Any]:
        if response.status_code not in ok_codes:
            raise RuntimeError(
                f"Grafana API request failed: status={response.status_code}, "
                f"body={response.text}"
            )
        if not response.text.strip():
            return {}
        return response.json()

    def discover_dashboard_api_version(self) -> str:
        response = self.session.get(
            f"{self.server_url}/apis/dashboard.grafana.app",
            timeout=self.timeout,
            verify=self.verify,
        )
        data = self._assert_success(response, (200,))
        preferred = data.get("preferredVersion", {}).get("version")
        if preferred:
            return preferred
        versions = [
            item.get("version")
            for item in data.get("versions", [])
            if item.get("version")
        ]
        if versions:
            return versions[0]
        raise RuntimeError(
            "Cannot discover dashboard.grafana.app API version from Grafana server"
        )

    def get_grafana_health(self) -> dict[str, Any]:
        response = self.session.get(
            f"{self.server_url}/api/health",
            timeout=self.timeout,
            verify=self.verify,
        )
        return self._assert_success(response, (200,))

    def get_server_info(self) -> dict[str, Any]:
        health = self.get_grafana_health()
        api_version = self.api_version or self.discover_dashboard_api_version()
        self.api_version = api_version
        return {
            "server_url": self.server_url,
            "namespace": self.namespace,
            "grafana_version": health.get("version"),
            "grafana_commit": health.get("commit"),
            "dashboard_api_group": "dashboard.grafana.app",
            "dashboard_api_version": api_version,
            "dashboard_api_path": self._base_dashboard_path(),
        }

    # ----- dashboard CRUD -----------------------------------------------

    def get_dashboard(self, name: str) -> dict[str, Any] | None:
        response = self.session.get(
            self._dashboard_url(name),
            timeout=self.timeout,
            verify=self.verify,
        )
        if response.status_code == 404:
            return None
        return self._assert_success(response, (200,))

    def list_dashboards(self) -> list[dict[str, Any]]:
        """List all dashboards in the configured namespace.

        Returns the raw ``items`` list from the K8s-style collection
        response. Each item typically has ``metadata.name`` and
        ``spec.title`` / ``spec.uid``.
        """
        response = self.session.get(
            self._dashboard_url(),
            timeout=self.timeout,
            verify=self.verify,
        )
        data = self._assert_success(response, (200,))
        return list(data.get("items", []))

    def delete_dashboard(self, name: str) -> bool:
        response = self.session.delete(
            self._dashboard_url(name),
            timeout=self.timeout,
            verify=self.verify,
        )
        if response.status_code == 404:
            return False
        self._assert_success(response, (200,))
        return True

    def create_dashboard(
        self,
        *,
        name: str,
        dashboard_json: dict[str, Any],
        folder_uid: str | None = None,
    ) -> UploadResult:
        spec = copy.deepcopy(dashboard_json)
        spec.pop("id", None)
        spec["uid"] = name
        spec.setdefault("version", 0)

        metadata: dict[str, Any] = {"name": name}
        if folder_uid:
            metadata["annotations"] = {"grafana.app/folder": folder_uid}

        payload = {"metadata": metadata, "spec": spec}
        response = self.session.post(
            self._dashboard_url(),
            data=json.dumps(payload, ensure_ascii=False),
            timeout=self.timeout,
            verify=self.verify,
        )
        data = self._assert_success(response, (200, 201))
        return self._build_result("created", name, spec, data)

    def update_dashboard(
        self,
        *,
        name: str,
        dashboard_json: dict[str, Any],
        message: str = "update dashboard via grafana new api",
        folder_uid: str | None = None,
    ) -> UploadResult:
        current = self.get_dashboard(name)
        if current is None:
            raise RuntimeError(f"Dashboard '{name}' does not exist, cannot update")

        current_version = int(current.get("spec", {}).get("version", 0))
        spec = copy.deepcopy(dashboard_json)
        spec.pop("id", None)
        spec["uid"] = name
        spec["version"] = current_version + 1

        annotations: dict[str, Any] = {"grafana.app/message": message}
        if folder_uid:
            annotations["grafana.app/folder"] = folder_uid

        payload = {
            "metadata": {"name": name, "annotations": annotations},
            "spec": spec,
        }
        response = self.session.put(
            self._dashboard_url(name),
            data=json.dumps(payload, ensure_ascii=False),
            timeout=self.timeout,
            verify=self.verify,
        )
        data = self._assert_success(response, (200,))
        return self._build_result("updated", name, spec, data)

    def create_or_update_dashboard(
        self,
        *,
        name: str,
        dashboard_json: dict[str, Any],
        message: str = "update dashboard via grafana new api",
        folder_uid: str | None = None,
    ) -> UploadResult:
        if self.get_dashboard(name) is None:
            return self.create_dashboard(
                name=name,
                dashboard_json=dashboard_json,
                folder_uid=folder_uid,
            )
        return self.update_dashboard(
            name=name,
            dashboard_json=dashboard_json,
            message=message,
            folder_uid=folder_uid,
        )

    # ----- internal -----------------------------------------------------

    def _build_result(
        self,
        action: str,
        name: str,
        spec: dict[str, Any],
        data: dict[str, Any],
    ) -> UploadResult:
        response_spec = data.get("spec", {}) or {}
        response_metadata = data.get("metadata", {}) or {}
        title = response_spec.get("title") or spec.get("title") or name
        uid = response_spec.get("uid") or spec.get("uid") or name
        version = response_spec.get("version")
        return UploadResult(
            action=action,
            name=name,
            title=title,
            uid=uid,
            version=int(version) if version is not None else None,
            resource_version=response_metadata.get("resourceVersion"),
            generation=response_metadata.get("generation"),
            url=self._browser_url(uid, title),
            raw=data,
        )


# ---------------------------------------------------------------------------
# High-level manager
# ---------------------------------------------------------------------------


@dataclass
class DeployOutcome:
    """Result of a :meth:`DashboardManager.deploy_many` call.

    A single bad dashboard in the batch shouldn't take down the rest:
    the successful ones land in ``succeeded`` and the failing ones in
    ``failed`` with the exception attached. Callers can inspect
    ``failed`` and decide whether to raise or log.
    """

    succeeded: list[UploadResult]
    failed: list[tuple[str, BaseException]]


class DashboardManager:
    """Higher-level dashboard management on top of :class:`GrafanaApiClient`.

    Stateless beyond the wrapped client — every method hits the API.
    The caller assembles dashboard JSON externally and feeds it in via
    :meth:`deploy` or :meth:`deploy_many`.

    Example:
        >>> client = GrafanaApiClient(
        ...     server_url="https://grafana.example.com",
        ...     api_key="...",
        ...     namespace="mos",
        ... )
        >>> mgr = DashboardManager(client)
        >>> result = mgr.deploy(
        ...     "etf-overview",
        ...     {"title": "ETF Overview", "panels": [...]},
        ... )
        >>> result.action
        'created'
    """

    def __init__(self, client: GrafanaApiClient) -> None:
        self.client = client

    # ----- write --------------------------------------------------------

    def deploy(
        self,
        name: str,
        dashboard_json: dict[str, Any],
        *,
        message: str = "update dashboard via mos",
        folder_uid: str | None = None,
    ) -> UploadResult:
        """Upsert a single dashboard. Caller supplies the JSON."""
        return self.client.create_or_update_dashboard(
            name=name,
            dashboard_json=dashboard_json,
            message=message,
            folder_uid=folder_uid,
        )

    def deploy_many(
        self,
        dashboards: dict[str, dict[str, Any]],
        *,
        message: str = "update dashboard via mos",
        folder_uid: str | None = None,
    ) -> DeployOutcome:
        """Upsert each ``(name, json)`` pair.

        Continues on error so a single bad dashboard doesn't abort the
        batch. Returns a :class:`DeployOutcome` with succeeded /
        failed partitions.
        """
        succeeded: list[UploadResult] = []
        failed: list[tuple[str, BaseException]] = []
        for name, json_payload in dashboards.items():
            try:
                succeeded.append(
                    self.deploy(
                        name,
                        json_payload,
                        message=message,
                        folder_uid=folder_uid,
                    )
                )
            except BaseException as exc:  # noqa: BLE001 — manager boundary
                failed.append((name, exc))
        return DeployOutcome(succeeded=succeeded, failed=failed)

    # ----- read / delete ------------------------------------------------

    def list(self) -> list[str]:
        """Return the list of dashboard names in the configured namespace."""
        return [
            item.get("metadata", {}).get("name", "")
            for item in self.client.list_dashboards()
            if item.get("metadata", {}).get("name")
        ]

    def get(self, name: str) -> dict[str, Any] | None:
        """Return the raw dashboard object, or ``None`` if missing."""
        return self.client.get_dashboard(name)

    def delete(self, name: str) -> bool:
        """Delete a dashboard. ``False`` if it didn't exist."""
        return self.client.delete_dashboard(name)
