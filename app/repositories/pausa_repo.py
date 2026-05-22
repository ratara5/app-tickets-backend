from datetime import datetime

from app.models.pausa import Pausa

def save_pausa(db, data, current_user):

    pausa = Pausa(
        id_mantenimiento=data.id_mantenimiento,
        motivo_pausa=data.motivo_pausa,
        fecha_hora_pausa=datetime.now().strftime("%Y-%m-%d %H:%M:%S+00"), # TODO: Inyectar TZ desde entorno y aplicar datetime.now(tz=ZoneInfo("Continente/Ciudad")).strftime("%Y-%m-%d %H:%M:%S+00")
        created_by=current_user.email
    )

    db.add(pausa)
    db.flush()
    db.refresh(pausa)

    return pausa

def get_pausas(db, current_user, page: int = 1, page_size: int = 50):
    pass