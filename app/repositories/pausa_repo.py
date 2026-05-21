from datetime import datetime

from app.models.pausa import Pausa

def save_pausa(db, data, current_user):

    pausa = Pausa(
        id_mantenimiento=data.id_mantenimiento,
        motivo_pausa=data.motivo_pausa,
        created_by=current_user.email
    )

    db.add(pausa)
    db.flush()
    db.refresh(pausa)

    return pausa

def get_pausas(db, current_user, page: int = 1, page_size: int = 50):
    pass