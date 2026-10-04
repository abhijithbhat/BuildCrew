# BuildCrew

Project repository structure:

- **`backend/`**: FastAPI backend service integrated with Supabase and GitHub App OAuth.
- **`mobile/`**: Production Flutter mobile application for deliverable and contribution tracking.

---

## Mobile Release Build Command

```bash
flutter build appbundle --release \
  --dart-define=API_BASE_URL=https://<your-backend> \
  --dart-define=SUPABASE_URL=... \
  --dart-define=SUPABASE_PUBLISHABLE_KEY=...
```

For more details on mobile setup and debugging options, see [`mobile/README.md`](mobile/README.md).
