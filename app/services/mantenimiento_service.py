from app.repositories.mantenimientos import get_visible_mantenimientos

def list_mantenimientos(db, current_user, page: int = 1, page_size: int = 50):
    return get_visible_mantenimientos(db, current_user, page, page_size)