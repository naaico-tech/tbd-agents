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

- Built assets are served by FastAPI from `/dashboard`
- API requests should target same-origin `/api/*`
- The legacy dashboard remains available at `/dashboard` (`/dashboard-legacy` remains as a compatibility alias)
