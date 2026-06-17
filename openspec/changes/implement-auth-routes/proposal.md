## Why

The backend has a partial auth system (JWT utilities, password hashing, and a login endpoint) but login is not registered in the app router, registration is missing, and there is no logout or profile management. This blocks mobile app authentication and user self-service.

## What Changes

- Register the existing `auth` router in the app so `POST /auth/login` works at runtime
- Add `POST /auth/register` endpoint for new user sign-up
- Add `POST /auth/logout` endpoint for session invalidation
- Add `GET /auth/me` endpoint to return the current authenticated user's profile
- Add `PUT /auth/me` endpoint to update the current user's profile
- Fix `auth_service.py` bug where `user.id` is used instead of `user.user_id`
- Register the `users` router (currently empty) for future user management extensibility
- Add corresponding tests for all new endpoints

## Capabilities

### New Capabilities
- `user-auth`: User registration, login, logout, and profile management (view/update)

### Modified Capabilities
*(No existing capabilities are being modified.)*

## Impact

- **Routes**: `app/api/routes/auth.py` — new endpoints; `app/api/routes/__init__.py` — register auth router
- **Services**: `app/services/auth_service.py` — add register, logout, profile services; fix `user.id` bug
- **Repositories**: `app/repositories/fsm_user_repo.py` — add create user, get user by id, update user
- **Schemas**: `app/schemas/auth.py` — add RegisterRequest, LogoutResponse; `app/schemas/user.py` — add UserProfile, UserUpdate
- **Deps**: `app/api/deps.py` — minor adjustments if needed for profile endpoint
- **Tests**: New test file(s) for auth endpoints
