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

def get_photo(db, maintenance_id, photo_id) -> Photo | None:
    return (
        db.query(Photo)
        .filter(Photo.maintenance_id == maintenance_id, Photo.photo_id == photo_id)
        .first()
    )

def get_photo_by_id(db, photo_id) -> Photo | None:
    return db.query(Photo).filter(Photo.photo_id == photo_id).first()

def delete_photo(db, photo: Photo) -> None:
    db.delete(photo)
    db.commit()

def get_photos(db, current_user, page: int = 1, page_size: int = 50):
    pass