from app.repositories.mantenimiento_repo import create_mantenimiento, get_visible_mantenimientos

def create_new_mantenimiento(db, data, current_user):
    # Lógica de negocio antes de persistir
    # ...

    mantenimiento = create_mantenimiento(db, data, current_user)
    
    # Lógica de negocio después de persistir

    return mantenimiento

def list_mantenimientos(db, current_user, page: int = 1, page_size: int = 50):
    return get_visible_mantenimientos(db, current_user, page, page_size)