from app.core.mcp_allowlists import RECOMMENDED_ALLOWED_TOOL_NAMES, get_recommended_allowed_tools


class TestRecommendedMcpAllowedTools:
    def test_known_server_returns_copy(self):
        tools = get_recommended_allowed_tools("datadog")

        assert tools == list(RECOMMENDED_ALLOWED_TOOL_NAMES["datadog"])

        tools.append("mutated")

        assert get_recommended_allowed_tools("datadog") == list(RECOMMENDED_ALLOWED_TOOL_NAMES["datadog"])

    def test_unknown_server_returns_empty_list(self):
        assert get_recommended_allowed_tools("unknown") == []

    def test_datadog_allowlist_is_read_only(self):
        tools = set(get_recommended_allowed_tools("datadog"))

        assert "create_datadog_monitor" not in tools
        assert "create_datadog_notebook" not in tools
        assert "edit_datadog_notebook" not in tools
        assert "upsert_datadog_dashboard" not in tools

    def test_salla_allowlist_resolves_from_prefixes(self):
        available = [
            "read_project_oas_t8v3ts",
            "read_project_oas_ref_resources_t8v3ts",
            "refresh_project_oas_t8v3ts",
            "other_tool",
        ]

        assert get_recommended_allowed_tools("salla-docs", available_tool_names=available) == [
            "read_project_oas_t8v3ts",
            "read_project_oas_ref_resources_t8v3ts",
            "refresh_project_oas_t8v3ts",
        ]