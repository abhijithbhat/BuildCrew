# BuildCrew

Log your contributions, get teammates to confirm them, and share a link that shows GitHub activity and who vouched for what.

Project repository structure:

- **`backend/`**: FastAPI backend service integrated with Supabase and GitHub App OAuth.
- **`mobile/`**: Production Flutter mobile application for deliverable and contribution tracking.
- **`docs/`**: Documentation, Privacy Policy, Account Deletion guide, and Play Store listing draft.

---

## Play Store Listing Draft

> Log your contributions, get teammates to confirm them, and share a link that shows GitHub activity and who vouched for what.

See [Google Play Store Listing Draft](docs/play-store-listing.md) for full metadata.

---

## Mobile Release Build Command

```bash
flutter build appbundle --release \
  --dart-define=API_BASE_URL=https://<your-backend> \
  --dart-define=SUPABASE_URL=... \
  --dart-define=SUPABASE_PUBLISHABLE_KEY=...
```

For more details on mobile setup and debugging options, see [`mobile/README.md`](mobile/README.md).
