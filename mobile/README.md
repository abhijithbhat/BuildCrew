# BuildCrew Mobile App

Production Flutter client for BuildCrew deliverable tracking and project passport verification.

---

## Production Release Build

To build a production Play Store Android App Bundle (`.aab`), all production backend and Supabase credentials must be passed via `--dart-define`. In release mode (`kReleaseMode`), the app enforces HTTPS and requires `API_BASE_URL` to be present, throwing a `StateError` if missing or insecure.

```bash
flutter build appbundle --release \
  --dart-define=API_BASE_URL=https://<your-backend> \
  --dart-define=SUPABASE_URL=... \
  --dart-define=SUPABASE_PUBLISHABLE_KEY=...
```

For building an APK for distribution or internal testing:

```bash
flutter build apk --release \
  --dart-define=API_BASE_URL=https://<your-backend> \
  --dart-define=SUPABASE_URL=... \
  --dart-define=SUPABASE_PUBLISHABLE_KEY=...
```

---

## Local Development & Debugging

In debug mode, the app automatically falls back to local dev loopbacks (`http://127.0.0.1:8000` for ADB reverse tunnel and `http://10.0.2.2:8000` for Android Emulator). You can optionally provide a local LAN IP (e.g. your computer's Wi-Fi IP for testing on physical devices):

```bash
flutter run --dart-define=LOCAL_LAN_URL=http://192.168.1.50:8000
```

Or connect a physical device via USB and run ADB reverse tunneling:

```bash
adb reverse tcp:8000 tcp:8000
flutter run
```

---

## Configuration Reference

| Parameter | Required in Release? | Default in Debug | Description |
|---|---|---|---|
| `API_BASE_URL` | **Yes** (must start with `https://`) | Falls back to local dev loopbacks | Backend REST API endpoint |
| `SUPABASE_URL` | **Yes** | Built-in dev Supabase project URL | Supabase Auth & Storage API URL |
| `SUPABASE_PUBLISHABLE_KEY` | **Yes** | Built-in dev Supabase publishable anon key | Supabase client anon key |
| `LOCAL_LAN_URL` | No (ignored in release) | Empty (skipped in fallback chain) | Host Wi-Fi IP for physical device testing |

---

## Networking & Timeouts

All HTTP calls made by `ApiClient` and domain services (`AuthService`, `ProjectService`, `GitHubService`, `HealthService`) share strict timeouts:
- **Connect Timeout**: 8 seconds
- **Receive Timeout**: 20 seconds
- **Send Timeout**: 20 seconds
