class AppLinks {
  static const String dashboardRoot = '/dashboard';
  static const String agents = '$dashboardRoot/agents';
  static const String mcpServers = '$dashboardRoot/mcp-servers';
  static const String customTools = '$dashboardRoot/custom-tools';
  static const String skills = '$dashboardRoot/skills';
  static const String knowledge = '$dashboardRoot/knowledge';
  static const String guardrails = '$dashboardRoot/guardrails';
  static const String tokens = '$dashboardRoot/tokens';
  static const String providers = '$dashboardRoot/providers';
  static const String workflows = '$dashboardRoot/workflows';
  static const String scheduledAgents = '$dashboardRoot/scheduled-agents';
  static const String tasks = '$dashboardRoot/tasks';
  static const String runTask = '$dashboardRoot/run-task';
  static const String chat = '$dashboardRoot/chat';

  static const String apiBasePath = '/api';
  static const String legacyDashboardBasePath = '/dashboard-legacy';

  static const Map<String, String> _legacyPagesByRoute = {
    dashboardRoot: 'dashboard',
    agents: 'agents',
    mcpServers: 'mcps',
    customTools: 'custom-tools',
    skills: 'skills',
    knowledge: 'knowledge',
    guardrails: 'guardrails',
    tokens: 'tokens',
    providers: 'providers',
    workflows: 'workflows',
    scheduledAgents: 'scheduled-agents',
    tasks: 'tasks',
    runTask: 'task',
    chat: 'chat',
  };

  static Uri apiUri(
    String path, {
    Map<String, String>? queryParameters,
  }) {
    final normalizedPath = path.startsWith('/') ? path : '/$path';
    final resolvedPath = normalizedPath.startsWith(apiBasePath)
        ? normalizedPath
        : '$apiBasePath$normalizedPath';
    return Uri(path: resolvedPath, queryParameters: queryParameters);
  }

  static String? legacyPageForRoute(String route) => _legacyPagesByRoute[route];

  static Uri legacyDashboardUri({String? route, String? page, bool embed = true}) {
    final legacyPage = page ?? (route == null ? null : legacyPageForRoute(route));
    final queryParameters = <String, String>{
      if (embed) 'embed': '1',
    };
    if (legacyPage != null) {
      queryParameters['page'] = legacyPage;
    }

    return Uri(
      path: legacyDashboardBasePath,
      queryParameters: queryParameters,
    );
  }
}
