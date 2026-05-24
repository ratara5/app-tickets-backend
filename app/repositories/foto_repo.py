from datetime import datetime

from sqlalchemy import or_, and_

from app.models.foto import Foto

def save_foto(db, data, current_user):

    foto = Foto(
        id_foto=data.id_foto,
        id_mantenimiento=data.id_mantenimiento,
        archivo_foto=data.archivo_foto,
        url_foto=data.url_foto,
        created_by=current_user.email
    )

    db.add(foto)
    db.commit()
    db.refresh(foto)

    return foto

def get_fotos(db, current_user, page: int = 1, page_size: int = 50):
    pass