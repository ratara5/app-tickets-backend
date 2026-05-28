from app.repositories.cancellation_repo import save_cancellation, get_cancellations


def create_new_cancellation(db, data, current_user):
    # Bussines logic before data persistance
    # ...
    
    cancellation = save_cancellation(db, data, current_user)
    # Business logic after data persistance
    # ...

    return cancellation

def list_cancellations(db, current_user, page: int = 1, page_size: int = 50):
    return get_cancellations(db, current_user, page, page_size)