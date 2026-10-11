# Account avatars

Open the top-right account menu, then **更换头像**. Select a JPG, PNG or WebP,
preview it, and save. **恢复默认** removes the saved avatar and restores initials.
The maximum uploaded file size is **5 × 1024 × 1024 bytes**, enforced on both sides.

## API and storage

- `POST /api/users/me/avatar`: multipart `file`; returns the current user envelope.
- `GET /api/users/me/avatar`: authenticated `image/webp`, not a JSON envelope.
- `DELETE /api/users/me/avatar`: resets the avatar; returns the current user envelope.
- `GET /api/auth/me`: adds nullable `avatar_url`; existing fields are unchanged.

All avatar endpoints require the current user's access token. The frontend loads
the image as an authenticated Blob and revokes object URLs on replacement/logout.
No public bucket, credentials, signed links or auth tokens in image URLs are needed.

Storage reuses `app/core/storage.py` and the existing `STORAGE_BACKEND`/`OSS_*`
settings. OSS objects use `<OSS_PREFIX>/avatars/<user_id>/<uuid>-avatar.webp`;
local files use `<UPLOAD_DIR>/avatars/<user_id>/<uuid>-avatar.webp`. Contract storage
paths are unchanged. Successful replacement/reset deletes the previous avatar.
If an old-object deletion fails, it is logged without undoing the saved profile.

Pillow (already present transitively, now declared directly) validates the actual
image, applies EXIF orientation, resizes to at most 512px, and re-encodes static
WebP without original metadata. SVG/GIF and invalid images are not accepted.

## Deployment

Restart the backend to create the independent `user_avatars` metadata table through
the existing `Base.metadata.create_all` startup path. Existing `users` columns and
data require no migration. Rebuild/reload the frontend Nginx configuration: the
exact avatar location allows 6 MB request bodies (5 MB file plus multipart overhead).
If another reverse proxy sits in front, it must also allow this request size.

## Verification

- `backend/tests/test_avatar.py`: authenticated routes, real image decoding, size
  boundaries, user isolation, replacement/reset and failed-commit cleanup, with
  temporary local storage and a fake OSS bucket. No cloud calls or keys.
- `frontend/tests/avatar.test.mjs`: size/type validation, profile refresh,
  stale-download isolation, object URL cleanup and failed-reset preservation.
- Browser checks use an isolated SQLite/FakeRedis backend, not production data.

## Changed files

| Area | Files | Change |
| --- | --- | --- |
| Backend API | `backend/app/api/avatars.py`, `backend/app/api/auth.py`, `backend/app/main.py` | Current-user endpoints, profile flag and router registration |
| Backend images/storage | `backend/app/services/avatar.py`, `backend/app/core/storage.py` | Decode/re-encode, 5 MB validation, shared OSS/local storage |
| Metadata | `backend/app/models/user.py`, `backend/app/models/__init__.py`, `backend/app/schemas/auth.py` | Independent avatar table and nullable profile field |
| Dependencies | `backend/pyproject.toml`, `backend/uv.lock` | Declare the existing Pillow dependency directly; no package upgrade |
| Frontend API/state | `frontend/src/api/avatar.ts`, `frontend/src/stores/auth.ts`, `frontend/src/types/api.ts`, `frontend/src/utils/avatar.ts` | Upload/read/reset, validation and object URL lifecycle |
| Frontend UI | `frontend/src/components/account/AvatarDialog.vue`, `frontend/src/components/ui/AppUserAvatar.vue`, `frontend/src/components/layout/AppNavbar.vue`, `frontend/src/views/Layout.vue` | Account menu, accessible preview dialog and avatar fallback |
| Styles/proxy | `frontend/src/styles/tokens.css`, `frontend/src/styles/application-shell.css`, `frontend/nginx.conf` | Dialog tokens, reduced motion and multipart body limit |
| Regression tests | `backend/tests/test_avatar.py`, `frontend/tests/avatar.test.mjs` | Storage, auth, images, size boundaries and stale-request cleanup |
| Documentation | `frontend/AVATARS.md` | Usage, deployment and verification |

## Separate existing risk (not changed by this feature)

The older `api/users.py` management routes do not enforce current-user/admin
permissions. The new avatar routes enforce their own `get_current_user` dependency;
the older account-management authorization needs a separate review and fix.
