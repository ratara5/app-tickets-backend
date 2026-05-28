from app.repositories.pause_repo import save_pausa, get_pausas

def create_new_pausa(db, data, current_user):
    # Lógica de negocio antes de persistir
    # ...
    
    pausa = save_pausa(db, data, current_user)
    # Lógica de negocio después de persistir
    # ...

    return pausa

def list_pausas(db, current_user, page: int = 1, page_size: int = 50):
    return get_pausas(db, current_user, page, page_size)