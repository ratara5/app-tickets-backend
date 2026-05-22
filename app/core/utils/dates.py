from datetime import date
from dateutil.relativedelta import relativedelta
import holidays

def start_of_month(n: int = 0) -> date:
    """Primer día del mes actual + n meses."""
    return (date.today().replace(day=1) + relativedelta(months=n))

def end_of_month(n: int = 0) -> date:
    """Último día del mes actual + n meses."""
    return (date.today().replace(day=1) + relativedelta(months=n+1) - relativedelta(days=1))

DYNAMIC_DATES = {
    "first_day_last_month": lambda: start_of_month(-1),
    "last_day_last_month":  lambda: end_of_month(-1),
    "first_day_this_month": lambda: start_of_month(0),
    "last_day_this_month":  lambda: end_of_month(0)
}

def resolve_date(token: str) -> str:
    """
    Resuelve un token de fecha dinámica a string ISO.
 
    Args:
        token: clave definida en DYNAMIC_DATES
 
    Returns:
        Fecha en formato 'YYYY-MM-DD'
 
    Raises:
        ValueError si el token no está registrado
    """
    fn = DYNAMIC_DATES.get(token)
    if not fn:
        raise ValueError(f"Token de fecha desconocido: '{token}'")
    return fn().isoformat()  # "2025-01-01"

CO_HOLIDAYS = holidays.Colombia() # TODO: Inyectar TZ y país como variables de entorno