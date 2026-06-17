## Context

The project has a partial auth layer: JWT utilities (`app/core/security.py`), an auth dependency (`app/api/deps.py`), a user model (`FSMUser`), a login service/repo, and a `POST /auth/login` route. However, the auth router is **not registered** in the app (`app/api/routes/__init__.py`), so login returns 404. There is a bug in `auth_service.py` using `user.id` instead of `user.user_id`. Registration, logout, and profile endpoints are entirely absent. The `users.py` route file is empty.

## Goals / Non-Goals

**Goals:**
- Register the auth router so login works at runtime
- Add `POST /auth/register` for new user sign-up
- Add `POST /auth/logout` via a server-side token blacklist
- Add `GET /auth/me` to return the current user's profile
- Add `PUT /auth/me` to update the current user's name and photo
- Fix the `user.id` → `user.user_id` bug in `auth_service.py`
- Add an empty users router placeholder for future admin endpoints
- Add tests for all new endpoints

**Non-Goals:**
- Password reset / forgot password flow
- Email verification on registration
- OAuth / social login
- Role management or admin user management endpoints
- Refresh token rotation (single JWT model)

## Decisions

### 1. Token blacklisting via database table
A `token_blacklist` table stores JWT `jti` (JWT ID) claims with an expiry timestamp. On logout, the token's `jti` is inserted; the auth dependency checks the blacklist on every request. This is simpler than Redis for the current scale and avoids an extra infrastructure dependency.

### 2. Registration creates user with hashed password
The `POST /auth/register` endpoint accepts email, password, and user_name. Password is hashed via `hash_password()` before storage. `user_role` defaults to `TECHNICIAN`. Duplicate email returns 409 Conflict.

### 3. Profile endpoints use the same auth dependency
`GET /auth/me` and `PUT /auth/me` reuse the existing `get_current_user` dependency for consistency with other routes.

### 4. PUT /auth/me over PATCH
Full profile update via PUT since the profile model is small (name + photo). If partial updates are needed later, PATCH can be added.

### 5. Add `jti` to JWT payload
The `create_access_token` function will be extended to include a `jti` claim (UUID v4) so tokens can be uniquely identified for blacklisting.

### 6. Remove `bearer` middleware — keep `HTTPBearer` in dependency
The existing pattern (HTTPBearer as Security dependency) works correctly. No change needed.

## Risks / Trade-offs

- [Database-dependent blacklist] → At high scale, DB lookups on every request could become a bottleneck. Mitigation: monitor and cache with Redis later if needed.
- [JWT size increase from `jti`] → Negligible (~36 bytes per token). No impact.
- [No token refresh] → Users must re-authenticate after expiry. Acceptable for MVP; refresh tokens can be added later.
- [Registration without email verification] → Users can register with any email. Acceptable for internal FSM system; verification can be added later.
