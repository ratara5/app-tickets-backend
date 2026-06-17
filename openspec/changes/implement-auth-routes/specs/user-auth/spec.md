## ADDED Requirements

### Requirement: User can register a new account
The system SHALL allow a new user to register with email, password, and user name. The password SHALL be hashed before storage. Duplicate email SHALL return 409 Conflict.

#### Scenario: Successful registration
- **WHEN** user sends POST /auth/register with valid email, password, and user_name
- **THEN** system returns 201 with user profile data

#### Scenario: Duplicate email registration
- **WHEN** user sends POST /auth/register with an email that already exists
- **THEN** system returns 409 Conflict with error message

#### Scenario: Registration with missing fields
- **WHEN** user sends POST /auth/register without required fields
- **THEN** system returns 422 Validation Error

### Requirement: User can log in
The system SHALL authenticate a user by email and password, returning a JWT access token.

#### Scenario: Successful login
- **WHEN** user sends POST /auth/login with valid email and password
- **THEN** system returns 200 with access_token and token_type

#### Scenario: Invalid credentials login
- **WHEN** user sends POST /auth/login with wrong email or password
- **THEN** system returns 401 Unauthorized

### Requirement: User can log out
The system SHALL invalidate the current JWT token by adding its jti to a blacklist.

#### Scenario: Successful logout
- **WHEN** authenticated user sends POST /auth/logout
- **THEN** system returns 200 with success message and blacklists the token

#### Scenario: Logout with invalid token
- **WHEN** unauthenticated user sends POST /auth/logout
- **THEN** system returns 401 Unauthorized

### Requirement: User can view their profile
The system SHALL return the authenticated user's profile data.

#### Scenario: Successful profile retrieval
- **WHEN** authenticated user sends GET /auth/me
- **THEN** system returns 200 with user_id, email, user_name, user_role, photo_path, created_at

#### Scenario: Profile retrieval without auth
- **WHEN** unauthenticated user sends GET /auth/me
- **THEN** system returns 401 Unauthorized

### Requirement: User can update their profile
The system SHALL allow the authenticated user to update their user_name and photo_path.

#### Scenario: Successful profile update
- **WHEN** authenticated user sends PUT /auth/me with user_name and/or photo_path
- **THEN** system returns 200 with updated user profile

#### Scenario: Profile update without auth
- **WHEN** unauthenticated user sends PUT /auth/me
- **THEN** system returns 401 Unauthorized
