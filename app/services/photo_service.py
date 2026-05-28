from app.repositories.photo_repo import save_photo, get_photos

from app.services.registry import service

from app.schemas.file import FileSave


@service(schema=FileSave) # The param seems redundant
def create_new_photo(db, data: FileSave, current_user): # Name for consistency, actually refers to save of one record whit the photo metadata
    # Bussines logic before data persistance
    # ...
    
    photo = save_photo(db, data, current_user)
    # Bussines logic after data persistance
    # ...

    return photo

def list_photos(db, current_user, page: int = 1, page_size: int = 50):
    return get_photos(db, current_user, page, page_size)