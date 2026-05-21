from app.core.security import verify_password, create_access_token

def login_user(user, password: str):

    if not verify_password(password, user.password_hash):
        return None

    return create_access_token({
        "sub": str(user.id)
    })