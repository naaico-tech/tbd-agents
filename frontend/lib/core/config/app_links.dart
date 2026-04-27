class AppLinks {
  static const String dashboardRoot = '/dashboard-new-ui';
  static const String agents = '$dashboardRoot/agents';
  static const String agentMemoryPattern = '$agents/:agentId/memory';
  static const String mcpServers = '$dashboardRoot/mcp-servers';
  static const String customTools = '$dashboardRoot/custom-tools';
  static const String skills = '$dashboardRoot/skills';
  static const String knowledge = '$dashboardRoot/knowledge';
  static const String guardrails = '$dashboardRoot/guardrails';
  static const String tokens = '$dashboardRoot/tokens';
  static const String providers = '$dashboardRoot/providers';
  static const String workflows = '$dashboardRoot/workflows';
  static const String workflowDetailPattern = '$workflows/:workflowId';
  static const String scheduledAgents = '$dashboardRoot/scheduled-agents';
  static const String tasks = '$dashboardRoot/tasks';
  static const String taskLogsPattern = '$tasks/:taskId/logs';
  static const String runTask = '$dashboardRoot/run-task';
  static const String chat = '$dashboardRoot/chat';

  static const String apiBasePath = '/api';
  static const String legacyDashboardBasePath = '/dashboard';

  /// Remove routes from legacy embed as they gain full Flutter parity.
  static const Set<String> _nativeRoutes = <String>{
    dashboardRoot,
    customTools,
  };

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

  static Uri apiUri(String path, {Map<String, String>? queryParameters}) {
    final normalizedPath = path.startsWith('/') ? path : '/$path';
    final resolvedPath = normalizedPath.startsWith(apiBasePath)
        ? normalizedPath
        : '$apiBasePath$normalizedPath';
    return Uri(path: resolvedPath, queryParameters: queryParameters);
  }

  static String agentMemory(String agentId) => '$agents/$agentId/memory';

  static String workflowDetail(String workflowId) => '$workflows/$workflowId';

  static String taskLogs(String taskId) => '$tasks/$taskId/logs';

  static String? legacyPageForRoute(String route) {
    final matchedRoute = _matchLegacyRoute(route);
    return matchedRoute == null ? null : _legacyPagesByRoute[matchedRoute];
  }

  static bool shouldEmbedLegacyRoute(String route) {
    final matchedRoute = _matchLegacyRoute(route);
    return matchedRoute != null && !_nativeRoutes.contains(matchedRoute);
  }

  static Uri legacyDashboardUri({
    String? route,
    String? page,
    bool embed = true,
    String chrome = 'none',
    String? hashPath,
    Map<String, String>? hashQueryParameters,
  }) {
    final legacyPage =
        page ?? (route == null ? null : legacyPageForRoute(route));
    final queryParameters = <String, String>{
      if (embed) 'embed': '1',
      if (chrome.isNotEmpty) 'chrome': chrome,
    };
    if (legacyPage != null) {
      queryParameters['page'] = legacyPage;
    }

    String? fragment;
    if ((hashPath ?? '').isNotEmpty || (hashQueryParameters ?? {}).isNotEmpty) {
      final normalizedHashPath = (hashPath ?? '').isEmpty
          ? '/${legacyPage ?? ''}'
          : hashPath!.startsWith('/')
          ? hashPath
          : '/$hashPath';
      final hashQuery = Uri(queryParameters: hashQueryParameters).query;
      fragment = normalizedHashPath;
      if (hashQuery.isNotEmpty) {
        fragment = '$fragment?$hashQuery';
      }
    }

    return Uri(
      path: legacyDashboardBasePath,
      queryParameters: queryParameters,
      fragment: fragment,
    );
  }

  static Uri legacyDashboardUriForAppUri(
    Uri uri, {
    bool embed = true,
    String chrome = 'none',
  }) {
    final matchedRoute = _matchLegacyRoute(uri.path);
    final legacyPage = matchedRoute == null
        ? null
        : _legacyPagesByRoute[matchedRoute];
    final remainder = matchedRoute == null
        ? ''
        : uri.path.substring(matchedRoute.length);
    final hasHashDetails =
        remainder.isNotEmpty && remainder != '/' ||
        uri.queryParameters.isNotEmpty;

    return legacyDashboardUri(
      route: matchedRoute ?? uri.path,
      page: legacyPage,
      embed: embed,
      chrome: chrome,
      hashPath: hasHashDetails ? '/${legacyPage ?? ''}$remainder' : null,
      hashQueryParameters: hasHashDetails ? uri.queryParameters : null,
    );
  }

  static String? _matchLegacyRoute(String route) {
    final normalizedRoute = route.endsWith('/') && route.length > 1
        ? route.substring(0, route.length - 1)
        : route;
    final matches = _legacyPagesByRoute.keys.where(
      (candidate) =>
          normalizedRoute == candidate ||
          normalizedRoute.startsWith('$candidate/'),
    );
    if (matches.isEmpty) {
      return null;
    }

    return matches.reduce(
      (current, next) => next.length > current.length ? next : current,
    );
  }
}
