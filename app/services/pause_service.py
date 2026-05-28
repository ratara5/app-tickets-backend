from app.repositories.pause_repo import save_pause, get_pauses


def create_new_pause(db, data, current_user):
    # Business logic before data persistance
    # ...
    
    pause = save_pause(db, data, current_user)
    # Business logic after data persistance
    # ...

    return pause

def list_pauses(db, current_user, page: int = 1, page_size: int = 50):
    return get_pauses(db, current_user, page, page_size)