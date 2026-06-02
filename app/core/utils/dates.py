from datetime import date
from dateutil.relativedelta import relativedelta

import holidays


def start_of_month(n: int = 0) -> date:
    """First day of the month + n months."""
    return (date.today().replace(day=1) + relativedelta(months=n))

def end_of_month(n: int = 0) -> date:
    """Last day of the month + n months."""
    return (date.today().replace(day=1) + relativedelta(months=n+1) - relativedelta(days=1))

DYNAMIC_DATES = {
    "first_day_last_month": lambda: start_of_month(-1),
    "last_day_last_month":  lambda: end_of_month(-1),
    "first_day_this_month": lambda: start_of_month(0),
    "last_day_this_month":  lambda: end_of_month(0)
}

def resolve_date(token: str) -> str:
    """
    Resolves a dynamic date token to an ISO string.
    Args:
        token: key defined in DYNAMIC_DATES
    Returns:
        Date in 'YYYY-MM-DD' format
    Raises:
        ValueError if the token is not registered
    """
    fn = DYNAMIC_DATES.get(token)
    if not fn:
        raise ValueError(f"Unknown date token: '{token}'")
    return fn().isoformat()  # "2025-01-01"

CO_HOLIDAYS = holidays.Colombia() # TODO: Inject TZ and country as env vars