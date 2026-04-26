bool get canUseBrowserNavigation => false;

void openInBrowser(String url) {
  throw UnsupportedError(
    'Browser navigation is only available on Flutter web.',
  );
}
