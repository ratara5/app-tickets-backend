## 1. Foundation — Models, Schemas, Security

- [x] 1.1 Create `TokenBlacklist` SQLAlchemy model with `jti`, `expires_at` columns
- [x] 1.2 Add Alembic migration for `token_blacklist` table
- [x] 1.3 Add `RegisterRequest`, `UserProfileResponse`, `UserUpdateRequest` Pydantic schemas in `app/schemas/auth.py` and `app/schemas/user.py`
- [x] 1.4 Extend `create_access_token` in `app/core/security.py` to include `jti` (UUID v4) in JWT payload

## 2. Repository Layer

- [x] 2.1 Add `create_user` function to `app/repositories/fsm_user_repo.py`
- [x] 2.2 Add `get_user_by_id` function to `app/repositories/fsm_user_repo.py`
- [x] 2.3 Add `update_user` function to `app/repositories/fsm_user_repo.py`
- [x] 2.4 Create `app/repositories/token_blacklist_repo.py` with `add_to_blacklist` and `is_blacklisted` functions

## 3. Service Layer

- [x] 3.1 Add `register_user` service function in `app/services/auth_service.py` — hash password, create user, return JWT
- [x] 3.2 Add `logout_user` service function in `app/services/auth_service.py` — blacklist token
- [x] 3.3 Add `get_user_profile` service function in `app/services/auth_service.py` — return user data
- [x] 3.4 Add `update_user_profile` service function in `app/services/auth_service.py` — update user_name/photo_path
- [x] 3.5 Fix `login_user` bug: `str(user.id)` → `str(user.user_id)` in `app/services/auth_service.py`
- [x] 3.6 Update `get_current_user` dependency in `app/api/deps.py` to check token blacklist

## 4. Route Layer

- [x] 4.1 Add `POST /auth/register` endpoint in `app/api/routes/auth.py`
- [x] 4.2 Add `POST /auth/logout` endpoint in `app/api/routes/auth.py`
- [x] 4.3 Add `GET /auth/me` endpoint in `app/api/routes/auth.py`
- [x] 4.4 Add `PUT /auth/me` endpoint in `app/api/routes/auth.py`
- [x] 4.5 Register `auth` and `users` routers in `app/api/routes/__init__.py`

## 5. Tests

- [x] 5.1 Write tests for user registration (success, duplicate email, validation errors)
- [x] 5.2 Write tests for user login (success, invalid credentials)
- [x] 5.3 Write tests for user logout (success, invalid token)
- [x] 5.4 Write tests for profile retrieval (authenticated, unauthenticated)
- [x] 5.5 Write tests for profile update (authenticated, unauthenticated)
- [x] 5.6 Write tests for token blacklist enforcement (blacklisted token rejected)

## 6. Verification

- [x] 6.1 Run tests and confirm all pass
- [x] 6.2 Run linting/type checking (*no linting tools configured, skipped*)
- [x] 6.3 Update `docs/api-spec.yml` with new auth endpoints
