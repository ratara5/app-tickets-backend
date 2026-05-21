from app.repositories.mantenimiento_repo import save_mantenimiento, get_visible_mantenimientos

def create_new_mantenimiento(db, data, current_user):
    return save_mantenimiento(db, data, current_user)

def list_mantenimientos(db, current_user, page: int = 1, page_size: int = 50):
    return get_visible_mantenimientos(db, current_user, page, page_size)