# TBD Agents Flutter Dashboard

The Flutter web app under `frontend/` is built into the main FastAPI image and served at `http://localhost:8000/dashboard`.

## Local checks

```bash
flutter config --enable-web
flutter pub get
flutter analyze
flutter test
flutter build web --release --base-href /dashboard/
```

## Integration contract

- Built assets are served by FastAPI from `/dashboard`.
- API requests target same-origin `/api/*`.
- The legacy dashboard is available at `/dashboard-legacy`.
- `/dashboard-new-ui` remains a compatibility alias that serves the legacy static dashboard.
