"""Recommended MCP allowlists for high-volume integrations.

These defaults are intentionally conservative for the built-in SRE and
documentation workflows so the runtime does not advertise large, mostly unused
tool catalogs.
"""

from collections.abc import Iterable, Sequence

RECOMMENDED_ALLOWED_TOOL_NAMES: dict[str, tuple[str, ...]] = {
    "datadog": (
        "analyze_datadog_logs",
        "search_datadog_logs",
        "search_datadog_spans",
        "get_datadog_trace",
        "get_datadog_metric",
        "get_datadog_metric_context",
    ),
    "notion": (
        "API-post-search",
        "API-retrieve-a-page",
        "API-post-page",
        "API-patch-page",
        "API-get-block-children",
        "API-patch-block-children",
    ),
    "zid-open-apis": (
        "fetch_api_documentation",
        "list_current-open-api-partners",
    ),
}

RECOMMENDED_ALLOWED_TOOL_PREFIXES: dict[str, tuple[str, ...]] = {
    "salla-docs": (
        "read_project_oas_",
        "read_project_oas_ref_resources_",
        "refresh_project_oas_",
    ),
}


def get_recommended_allowed_tools(
    server_name: str, available_tool_names: Iterable[str] | None = None
) -> list[str]:
    """Return the recommended allowlist for a known MCP server.

    Some MCP servers expose environment-specific tool names. For those servers,
    pass the live tool inventory and this helper will resolve the matching names
    from their stable prefixes.
    """
    tools: Sequence[str] = RECOMMENDED_ALLOWED_TOOL_NAMES.get(server_name, ())
    resolved_tools = list(tools)
    prefixes = RECOMMENDED_ALLOWED_TOOL_PREFIXES.get(server_name, ())
    if not prefixes or available_tool_names is None:
        return resolved_tools

    seen = set(resolved_tools)
    for tool_name in available_tool_names:
        if tool_name in seen:
            continue
        if any(tool_name.startswith(prefix) for prefix in prefixes):
            resolved_tools.append(tool_name)
            seen.add(tool_name)
    return resolved_tools