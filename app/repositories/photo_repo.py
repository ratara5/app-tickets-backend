from app.models.photo import Photo


def save_photo(db, data, current_user):

    photo = Photo(
        photo_id=data.file_id,
        maintenance_id=data.parent_id,
        photo_path=data.file_path # It's a path
        # url_foto=data.file_url,
        # created_by=current_user.user_id # It's not necessary overwrite auditmixin
    )

    db.add(photo)
    db.commit()
    db.refresh(photo)

    return photo

def get_photos(db, current_user, page: int = 1, page_size: int = 50):
    pass