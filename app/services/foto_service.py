from app.repositories.foto_repo import save_foto, get_fotos

def create_new_foto(db, data, current_user): # Nombre por consistencia, pero hace referencia al guardado de un registro con la información de una foto
    # Lógica de negocio antes de persistir
    # ...
    
    foto = save_foto(db, data, current_user)
    # Lógica de negocio después de persistir
    # ...

    return foto

def list_fotos(db, current_user, page: int = 1, page_size: int = 50):
    return get_fotos(db, current_user, page, page_size)