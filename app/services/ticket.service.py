from app.repositories.tickets import save_ticket
from app.repositories.tickets import get_visible_tickets

def create_new_ticket(db, data, current_user):
    return save_ticket(db, data, current_user)

def list_tickets(db, current_user, page: int = 1, page_size: int = 50):
    return get_visible_tickets(db, current_user, page, page_size)

