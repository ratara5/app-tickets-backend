from app.repositories.cancellation_repo import save_cancelacion, get_cancelaciones

def create_new_cancelacion(db, data, current_user):
    # Lógica de negocio antes de persistir
    # ...
    
    cancelacion = save_cancelacion(db, data, current_user)
    # Lógica de negocio después de persistir
    # ...

    return cancelacion

def list_cancelaciones(db, current_user, page: int = 1, page_size: int = 50):
    return get_cancelaciones(db, current_user, page, page_size)