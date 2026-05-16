"""KubernetesPlugin — cluster observability for tbd-agents (SRE Agent).

Read-heavy plugin that lets an SRE agent inspect a Kubernetes cluster:
list namespaces, pods, deployments, events; fetch logs; check resource
usage; and describe nodes.  Two narrow write operations — pod restart and
deployment scale — are supported but are gated by an ``approval_token``.

Credential loading order
------------------------
1. In-cluster service account (``/var/run/secrets/kubernetes.io/serviceaccount``
   exists) — used when the agent runs inside a Kubernetes pod.
2. ``KUBECONFIG`` environment variable — path to a kubeconfig file.
3. Default ``~/.kube/config`` — standard kubectl config location.

The optional ``K8S_CONTEXT`` environment variable selects a named context
from the kubeconfig.  If it is empty, the current-context is used.

Production safety
-----------------
If the active context name contains ``prod``, ``production``, or ``live``
(case-insensitive), ALL write operations require a non-empty
``approval_token`` even if one would otherwise not be needed.  Read
operations are always permitted regardless of context.

The official ``kubernetes`` Python client is imported lazily inside
:meth:`execute` so the plugin can be imported without the library installed.
"""

from __future__ import annotations

import os
from typing import Any

from app.core.plugin_base import PluginBase

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PROD_CONTEXT_KEYWORDS = ("prod", "production", "live")
_DEFAULT_TAIL_LINES = 100
_DEFAULT_SINCE_SECONDS = 3600  # 1 hour
_METRICS_API_GROUP = "metrics.k8s.io"
_WRITE_OPS = {"restart_pod", "scale_deployment"}


def _is_prod_context(context_name: str) -> bool:
    """Return True if *context_name* looks like a production context."""
    lower = context_name.lower()
    return any(keyword in lower for keyword in _PROD_CONTEXT_KEYWORDS)


class KubernetesPlugin(PluginBase):
    """Kubernetes cluster inspection plugin for SRE agents.

    Provides read access to the most commonly needed cluster resources —
    namespaces, pods, deployments, events, logs, and node descriptions —
    plus two approval-gated write operations: delete-to-restart a pod and
    scale a deployment.

    Supported operations
    --------------------
    **Cluster / namespace level**

    ``list_namespaces``
        List all namespaces in the cluster with their phase and labels.
    ``list_events``
        List Kubernetes events in a namespace, optionally filtered by a
        field selector (e.g. ``"involvedObject.name=my-pod"``).

    **Pods**

    ``list_pods``
        List pods in a namespace with optional label selector filtering.
    ``get_pod``
        Retrieve full spec and status for a specific pod.
    ``pod_logs``
        Fetch log lines from a pod container, with optional tail and
        time-window filters.
    ``top_pods``
        Return CPU and memory usage for pods via the ``metrics.k8s.io`` API
        (requires the Metrics Server to be running in the cluster).

    **Deployments**

    ``list_deployments``
        List deployments in a namespace with replica counts and conditions.
    ``get_deployment``
        Retrieve full spec and status for a specific deployment.

    **Nodes**

    ``describe_node``
        Return labels, taints, capacity, allocatable resources, and
        conditions for a named node.

    **Write (approval required)**

    ``restart_pod``
        Delete the named pod so its controller (Deployment / ReplicaSet)
        recreates it.  Acts as a graceful restart.  Requires
        ``approval_token``.  Also requires ``approval_token`` for any
        prod-named context.
    ``scale_deployment``
        Patch the replica count of a deployment.  Requires
        ``approval_token``.  Also requires ``approval_token`` for any
        prod-named context.
    """

    # ------------------------------------------------------------------
    # PluginBase interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "kubernetes"

    @property
    def description(self) -> str:
        return (
            "Kubernetes cluster inspection for SRE agents. "
            "Read operations: list_namespaces, list_pods, get_pod, pod_logs, "
            "list_deployments, get_deployment, list_events, top_pods, "
            "describe_node. "
            "Write operations (approval_token required): restart_pod (delete "
            "pod so controller recreates it), scale_deployment (patch replicas)."
        )

    @property
    def tags(self) -> list[str]:
        return ["kubernetes", "k8s", "infrastructure", "observability", "sre", "read"]

    @property
    def env_config(self) -> dict[str, str]:
        return {
            "KUBECONFIG": "{{token:kubeconfig-path}}",
            "K8S_CONTEXT": "",
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_config(self):
        """Load Kubernetes client config (in-cluster → kubeconfig fallback).

        Returns:
            The active context name string (empty for in-cluster auth).
        """
        from kubernetes import client as k8s_client, config as k8s_config  # noqa: PLC0415

        context_name = os.environ.get("K8S_CONTEXT", "").strip()
        kubeconfig = os.environ.get("KUBECONFIG", "").strip() or None

        in_cluster_sa = "/var/run/secrets/kubernetes.io/serviceaccount/token"
        if os.path.exists(in_cluster_sa):
            k8s_config.load_incluster_config()
            return ""

        try:
            contexts, active_ctx = k8s_config.list_kube_config_contexts(
                config_file=kubeconfig
            )
        except Exception:  # noqa: BLE001
            contexts, active_ctx = [], {}

        if context_name:
            k8s_config.load_kube_config(
                config_file=kubeconfig,
                context=context_name,
            )
            return context_name

        k8s_config.load_kube_config(config_file=kubeconfig)
        return (active_ctx or {}).get("name", "")

    def _clients(self):
        """Load config and return a tuple of common API client objects.

        Returns:
            Tuple of ``(CoreV1Api, AppsV1Api, context_name)``
        """
        from kubernetes import client as k8s_client  # noqa: PLC0415

        context_name = self._load_config()
        return (
            k8s_client.CoreV1Api(),
            k8s_client.AppsV1Api(),
            context_name,
        )

    def _check_write_allowed(self, context_name: str, approval_token: str) -> str | None:
        """Return an error string if the write should be blocked, else ``None``."""
        if not approval_token.strip():
            return (
                "approval_token is required for all write operations. "
                "Obtain a token from your team's change-management workflow."
            )
        if _is_prod_context(context_name) and not approval_token.strip():
            return (
                f"Context {context_name!r} is a production context. "
                "approval_token is required for ALL write operations in production."
            )
        return None

    def _serialize_pod(self, pod) -> dict[str, Any]:
        """Return a compact summary dict from a ``V1Pod`` object."""
        meta = pod.metadata
        spec = pod.spec
        status = pod.status
        containers = [
            {"name": c.name, "image": c.image}
            for c in (spec.containers or [])
        ]
        conditions = [
            {"type": c.type, "status": c.status, "reason": c.reason or ""}
            for c in (status.conditions or [])
        ]
        return {
            "name": meta.name,
            "namespace": meta.namespace,
            "phase": status.phase or "",
            "node": spec.node_name or "",
            "containers": containers,
            "conditions": conditions,
            "labels": dict(meta.labels or {}),
            "creation_timestamp": str(meta.creation_timestamp),
        }

    def _serialize_deployment(self, dep) -> dict[str, Any]:
        """Return a compact summary dict from a ``V1Deployment`` object."""
        meta = dep.metadata
        spec = dep.spec
        status = dep.status
        conditions = [
            {"type": c.type, "status": c.status, "reason": c.reason or ""}
            for c in (status.conditions or [])
        ]
        return {
            "name": meta.name,
            "namespace": meta.namespace,
            "replicas": spec.replicas,
            "ready_replicas": status.ready_replicas or 0,
            "available_replicas": status.available_replicas or 0,
            "conditions": conditions,
            "labels": dict(meta.labels or {}),
            "creation_timestamp": str(meta.creation_timestamp),
        }

    # ------------------------------------------------------------------
    # execute — main dispatcher
    # ------------------------------------------------------------------

    def execute(
        self,
        operation: str,
        # namespace-scoped ops
        namespace: str = "default",
        # pod ops
        pod: str = "",
        label_selector: str = "",
        container: str = "",
        tail_lines: int = _DEFAULT_TAIL_LINES,
        since_seconds: int = _DEFAULT_SINCE_SECONDS,
        # deployment ops
        name: str = "",
        replicas: int = 1,
        # event ops
        field_selector: str = "",
        # node ops (describe_node)
        # reuses 'name' param above
        # write gate
        approval_token: str = "",
    ) -> dict:
        """Execute a Kubernetes cluster inspection or write operation.

        Args:
            operation: One of the supported operation names (see class
                docstring).
            namespace: Kubernetes namespace.  Defaults to ``"default"``.
                Used by all namespaced operations.
            pod: Pod name.  Required for ``get_pod``, ``pod_logs``, and
                ``restart_pod``.
            label_selector: Label selector string (e.g.
                ``"app=nginx,tier=frontend"``).  Optional for ``list_pods``.
            container: Container name within the pod.  Optional for
                ``pod_logs`` — defaults to the first container.
            tail_lines: Number of log lines to return from the end of the
                log.  Defaults to ``100``.
            since_seconds: Restrict log output to the last N seconds.
                Defaults to ``3600`` (1 hour).
            name: Resource name.  Required for ``get_deployment``,
                ``scale_deployment``, and ``describe_node``.
            replicas: Desired replica count for ``scale_deployment``.
                Must be ≥ 0.
            field_selector: Kubernetes field selector string (e.g.
                ``"involvedObject.name=my-pod"``).  Optional for
                ``list_events``.
            approval_token: Opaque token required for write operations
                (``restart_pod``, ``scale_deployment``) and for any write
                against a production-named context.

        Returns:
            A dict whose structure depends on the operation, or
            ``{"error": "..."}`` on failure.
        """
        from kubernetes.client.exceptions import ApiException  # noqa: PLC0415

        try:
            core_v1, apps_v1, context_name = self._clients()
        except Exception as exc:  # noqa: BLE001
            return {"error": f"Failed to load Kubernetes client config: {exc}"}
        op = operation.strip().lower()

        # ----------------------------------------------------------------
        # list_namespaces
        # ----------------------------------------------------------------
        if op == "list_namespaces":
            try:
                result = core_v1.list_namespace()
            except ApiException as exc:
                return {"error": f"Kubernetes API error: {exc}"}
            namespaces = [
                {
                    "name": ns.metadata.name,
                    "phase": ns.status.phase or "",
                    "labels": dict(ns.metadata.labels or {}),
                }
                for ns in result.items
            ]
            return {"namespaces": namespaces, "count": len(namespaces)}

        # ----------------------------------------------------------------
        # list_pods
        # ----------------------------------------------------------------
        if op == "list_pods":
            kwargs: dict[str, Any] = {}
            if label_selector.strip():
                kwargs["label_selector"] = label_selector.strip()
            try:
                result = core_v1.list_namespaced_pod(namespace=namespace, **kwargs)
            except ApiException as exc:
                return {"error": f"Kubernetes API error: {exc}"}
            pods = [self._serialize_pod(p) for p in result.items]
            return {"pods": pods, "namespace": namespace, "count": len(pods)}

        # ----------------------------------------------------------------
        # get_pod
        # ----------------------------------------------------------------
        if op == "get_pod":
            if not pod.strip():
                return {"error": "get_pod requires a non-empty 'pod' name."}
            try:
                result = core_v1.read_namespaced_pod(
                    name=pod.strip(), namespace=namespace
                )
            except ApiException as exc:
                return {"error": f"Kubernetes API error: {exc}"}
            return self._serialize_pod(result)

        # ----------------------------------------------------------------
        # pod_logs
        # ----------------------------------------------------------------
        if op == "pod_logs":
            if not pod.strip():
                return {"error": "pod_logs requires a non-empty 'pod' name."}
            kwargs = {
                "name": pod.strip(),
                "namespace": namespace,
                "tail_lines": max(1, tail_lines),
                "since_seconds": max(1, since_seconds),
            }
            if container.strip():
                kwargs["container"] = container.strip()
            try:
                logs = core_v1.read_namespaced_pod_log(**kwargs)
            except ApiException as exc:
                return {"error": f"Kubernetes API error: {exc}"}
            return {
                "pod": pod.strip(),
                "namespace": namespace,
                "container": container.strip() or "(default)",
                "logs": logs,
            }

        # ----------------------------------------------------------------
        # list_deployments
        # ----------------------------------------------------------------
        if op == "list_deployments":
            try:
                result = apps_v1.list_namespaced_deployment(namespace=namespace)
            except ApiException as exc:
                return {"error": f"Kubernetes API error: {exc}"}
            deployments = [self._serialize_deployment(d) for d in result.items]
            return {
                "deployments": deployments,
                "namespace": namespace,
                "count": len(deployments),
            }

        # ----------------------------------------------------------------
        # get_deployment
        # ----------------------------------------------------------------
        if op == "get_deployment":
            if not name.strip():
                return {"error": "get_deployment requires a non-empty 'name'."}
            try:
                result = apps_v1.read_namespaced_deployment(
                    name=name.strip(), namespace=namespace
                )
            except ApiException as exc:
                return {"error": f"Kubernetes API error: {exc}"}
            return self._serialize_deployment(result)

        # ----------------------------------------------------------------
        # list_events
        # ----------------------------------------------------------------
        if op == "list_events":
            kwargs = {"namespace": namespace}
            if field_selector.strip():
                kwargs["field_selector"] = field_selector.strip()
            try:
                result = core_v1.list_namespaced_event(**kwargs)
            except ApiException as exc:
                return {"error": f"Kubernetes API error: {exc}"}
            events = [
                {
                    "name": e.metadata.name,
                    "reason": e.reason or "",
                    "message": e.message or "",
                    "type": e.type or "",
                    "count": e.count or 0,
                    "involved_object": {
                        "kind": e.involved_object.kind,
                        "name": e.involved_object.name,
                        "namespace": e.involved_object.namespace,
                    },
                    "first_timestamp": str(e.first_timestamp),
                    "last_timestamp": str(e.last_timestamp),
                }
                for e in result.items
            ]
            return {"events": events, "namespace": namespace, "count": len(events)}

        # ----------------------------------------------------------------
        # top_pods  — requires Metrics Server (metrics.k8s.io)
        # ----------------------------------------------------------------
        if op == "top_pods":
            from kubernetes import client as k8s_client  # noqa: PLC0415

            custom_api = k8s_client.CustomObjectsApi()
            try:
                result = custom_api.list_namespaced_custom_object(
                    group=_METRICS_API_GROUP,
                    version="v1beta1",
                    namespace=namespace,
                    plural="pods",
                )
            except ApiException as exc:
                return {
                    "error": (
                        f"Metrics Server unavailable or not installed: {exc}. "
                        "Ensure metrics-server is deployed in the cluster."
                    )
                }
            pod_metrics = [
                {
                    "name": item.get("metadata", {}).get("name", ""),
                    "containers": [
                        {
                            "name": c.get("name", ""),
                            "cpu": c.get("usage", {}).get("cpu", ""),
                            "memory": c.get("usage", {}).get("memory", ""),
                        }
                        for c in item.get("containers", [])
                    ],
                    "timestamp": item.get("timestamp", ""),
                }
                for item in result.get("items", [])
            ]
            return {
                "pod_metrics": pod_metrics,
                "namespace": namespace,
                "count": len(pod_metrics),
            }

        # ----------------------------------------------------------------
        # describe_node
        # ----------------------------------------------------------------
        if op == "describe_node":
            if not name.strip():
                return {"error": "describe_node requires a non-empty 'name'."}
            try:
                node = core_v1.read_node(name=name.strip())
            except ApiException as exc:
                return {"error": f"Kubernetes API error: {exc}"}
            meta = node.metadata
            spec = node.spec
            status = node.status
            conditions = [
                {
                    "type": c.type,
                    "status": c.status,
                    "reason": c.reason or "",
                    "message": c.message or "",
                }
                for c in (status.conditions or [])
            ]
            taints = [
                {
                    "key": t.key,
                    "effect": t.effect,
                    "value": t.value or "",
                }
                for t in (spec.taints or [])
            ]
            return {
                "name": meta.name,
                "labels": dict(meta.labels or {}),
                "taints": taints,
                "capacity": dict(
                    (k, str(v)) for k, v in (status.capacity or {}).items()
                ),
                "allocatable": dict(
                    (k, str(v)) for k, v in (status.allocatable or {}).items()
                ),
                "conditions": conditions,
            }

        # ----------------------------------------------------------------
        # restart_pod  (write — requires approval_token)
        # ----------------------------------------------------------------
        if op == "restart_pod":
            err = self._check_write_allowed(context_name, approval_token)
            if err:
                return {"error": err}
            if not pod.strip():
                return {"error": "restart_pod requires a non-empty 'pod' name."}

            try:
                core_v1.delete_namespaced_pod(
                    name=pod.strip(),
                    namespace=namespace,
                )
            except ApiException as exc:
                return {"error": f"Kubernetes API error deleting pod: {exc}"}

            return {
                "restarted": True,
                "pod": pod.strip(),
                "namespace": namespace,
                "note": (
                    "Pod deleted; the owning controller (Deployment/ReplicaSet) "
                    "will recreate it automatically."
                ),
            }

        # ----------------------------------------------------------------
        # scale_deployment  (write — requires approval_token)
        # ----------------------------------------------------------------
        if op == "scale_deployment":
            err = self._check_write_allowed(context_name, approval_token)
            if err:
                return {"error": err}
            if not name.strip():
                return {"error": "scale_deployment requires a non-empty 'name'."}
            if replicas < 0:
                return {"error": "scale_deployment requires 'replicas' >= 0."}

            patch_body = {"spec": {"replicas": replicas}}
            try:
                apps_v1.patch_namespaced_deployment_scale(
                    name=name.strip(),
                    namespace=namespace,
                    body=patch_body,
                )
            except ApiException as exc:
                return {"error": f"Kubernetes API error patching deployment: {exc}"}

            return {
                "scaled": True,
                "deployment": name.strip(),
                "namespace": namespace,
                "replicas": replicas,
            }

        # ----------------------------------------------------------------
        # Unsupported operation
        # ----------------------------------------------------------------
        valid_ops = (
            "list_namespaces, list_pods, get_pod, pod_logs, "
            "list_deployments, get_deployment, list_events, top_pods, "
            "describe_node, restart_pod, scale_deployment"
        )
        return {
            "error": (
                f"Unsupported operation: {operation!r}. "
                f"Valid operations: {valid_ops}."
            )
        }
