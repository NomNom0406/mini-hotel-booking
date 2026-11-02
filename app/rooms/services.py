from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import contains_eager

from ..extensions import db
from ..hotels.services import delete_image, parse_dates
from ..models import (
    Amenity, Booking, Hotel, Room, RoomType, hotel_amenities, room_type_amenities,
)

_BLOCKING_STATUSES = ("Pending", "Confirmed")


class RoomNumberTaken(ValueError):
    """Số phòng đã tồn tại trong khách sạn."""


class RoomTypeNameTaken(ValueError):
    """Tên loại phòng đã tồn tại trong khách sạn."""


class AmenityNameTaken(ValueError):
    """Tên tiện nghi đã tồn tại."""


class RuleViolation(ValueError):
    """Vi phạm ràng buộc nghiệp vụ (loại phòng không thuộc khách sạn, đổi khách sạn khi đã có dữ liệu...)."""


# ─── Công khai ──────────────────────────────────────────────────────────────

def _booked_room_ids(ci, co):
    """Truy vấn con: id các phòng đang bị giữ trong [ci, co)."""
    return select(Booking.room_id).where(
        Booking.status.in_(_BLOCKING_STATUSES),
        Booking.check_in < co,
        Booking.check_out > ci,
    )


def hotel_room_type_choices(hotel_id):
    rows = db.session.execute(
        select(RoomType.id, RoomType.name)
        .where(RoomType.hotel_id == hotel_id)
        .order_by(RoomType.base_price, RoomType.id)
    ).all()
    return [(str(type_id), name) for type_id, name in rows]


def list_hotel_rooms(hotel_id, room_type_id=None, price_min=None, price_max=None,
                     checkin=None, checkout=None, guests=1, page=1, per_page=9):
    """Phòng đang hoạt động của một khách sạn: lọc + phân trang.

    Luôn lọc capacity >= guests; có đủ ngày hợp lệ thì loại phòng trùng lịch.
    """
    stmt = (
        select(Room)
        .join(RoomType, Room.room_type_id == RoomType.id)
        .options(contains_eager(Room.room_type))
        .where(Room.hotel_id == hotel_id, Room.is_active == True,
               RoomType.capacity >= guests)
    )
    if room_type_id:
        stmt = stmt.where(RoomType.id == room_type_id)
    if price_min is not None:
        stmt = stmt.where(RoomType.base_price >= price_min)
    if price_max is not None:
        stmt = stmt.where(RoomType.base_price <= price_max)

    ci, co = parse_dates(checkin, checkout)
    if ci and co:
        stmt = stmt.where(Room.id.not_in(_booked_room_ids(ci, co)))

    stmt = stmt.order_by(RoomType.base_price, Room.room_number, Room.id)
    return db.paginate(stmt, page=max(page or 1, 1), per_page=per_page, error_out=False)


def get_active_room(room_id):
    """Phòng đang hoạt động của khách sạn đang hoạt động, nếu không thì 404."""
    return db.first_or_404(
        select(Room)
        .join(Hotel, Room.hotel_id == Hotel.id)
        .where(Room.id == room_id, Room.is_active == True, Hotel.is_active == True)
    )


def room_is_free(room_id, ci, co):
    stmt = select(Booking.id).where(
        Booking.room_id == room_id,
        Booking.status.in_(_BLOCKING_STATUSES),
        Booking.check_in < co,
        Booking.check_out > ci,
    ).limit(1)
    return db.session.execute(stmt).first() is None


# ─── Danh sách chọn cho form admin ──────────────────────────────────────────

def all_hotel_choices():
    rows = db.session.execute(select(Hotel.id, Hotel.name).order_by(Hotel.name)).all()
    return [(hotel_id, name) for hotel_id, name in rows]


def room_type_choices():
    rows = db.session.execute(
        select(RoomType.id, Hotel.name, RoomType.name)
        .join(Hotel, RoomType.hotel_id == Hotel.id)
        .order_by(Hotel.name, RoomType.name)
    ).all()
    return [(type_id, f"{hotel_name} — {type_name}") for type_id, hotel_name, type_name in rows]


# ─── Quản lý phòng ──────────────────────────────────────────────────────────

def list_rooms_admin(hotel_id=None, page=1, per_page=15):
    stmt = (
        select(Room)
        .join(Hotel, Room.hotel_id == Hotel.id)
        .join(RoomType, Room.room_type_id == RoomType.id)
        .options(contains_eager(Room.hotel), contains_eager(Room.room_type))
    )
    if hotel_id:
        stmt = stmt.where(Room.hotel_id == hotel_id)
    stmt = stmt.order_by(Hotel.name, Room.floor, Room.room_number, Room.id)
    return db.paginate(stmt, page=max(page or 1, 1), per_page=per_page, error_out=False)


def _check_room(data, room=None):
    hotel_id, type_id = data["hotel_id"], data["room_type_id"]
    room_type = db.session.get(RoomType, type_id)
    if room_type is None or room_type.hotel_id != hotel_id:
        raise RuleViolation("Loại phòng không thuộc khách sạn đã chọn.")
    number = data["room_number"].strip()
    stmt = select(Room.id).where(Room.hotel_id == hotel_id, Room.room_number == number)
    if room is not None:
        stmt = stmt.where(Room.id != room.id)
    if db.session.execute(stmt.limit(1)).first():
        raise RoomNumberTaken("Số phòng đã tồn tại trong khách sạn này.")
    if room is not None and room.hotel_id != hotel_id and db.session.execute(
        select(Booking.id).where(Booking.room_id == room.id).limit(1)
    ).first():
        raise RuleViolation("Phòng đã có booking, không thể chuyển sang khách sạn khác.")
    return number


def create_room(data):
    number = _check_room(data)
    room = Room(hotel_id=data["hotel_id"], room_type_id=data["room_type_id"],
                room_number=number, floor=data["floor"], is_active=True)
    try:
        db.session.add(room)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise RoomNumberTaken("Số phòng đã tồn tại trong khách sạn này.") from None
    except Exception:
        db.session.rollback()
        raise
    return room


def update_room(room, data):
    number = _check_room(data, room)
    try:
        room.hotel_id = data["hotel_id"]
        room.room_type_id = data["room_type_id"]
        room.room_number = number
        room.floor = data["floor"]
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise RoomNumberTaken("Số phòng đã tồn tại trong khách sạn này.") from None
    except Exception:
        db.session.rollback()
        raise
    return room


def set_room_active(room, active):
    """Ẩn/hiện phòng. Không có thao tác xóa: phòng đã có booking chỉ được ẩn."""
    try:
        room.is_active = bool(active)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return room


# ─── Quản lý loại phòng ─────────────────────────────────────────────────────

def list_room_types_admin(hotel_id=None):
    """Loại phòng kèm khách sạn, và số phòng của từng loại (2 truy vấn)."""
    stmt = (
        select(RoomType)
        .join(Hotel, RoomType.hotel_id == Hotel.id)
        .options(contains_eager(RoomType.hotel))
    )
    if hotel_id:
        stmt = stmt.where(RoomType.hotel_id == hotel_id)
    stmt = stmt.order_by(Hotel.name, RoomType.base_price, RoomType.id)
    room_types = db.session.execute(stmt).scalars().all()
    rows = db.session.execute(
        select(Room.room_type_id, func.count(Room.id)).group_by(Room.room_type_id)
    ).all()
    return room_types, {type_id: count for type_id, count in rows}


def _check_room_type(data, room_type=None):
    hotel_id = data["hotel_id"]
    if db.session.get(Hotel, hotel_id) is None:
        raise RuleViolation("Khách sạn không tồn tại.")
    name = data["name"].strip()
    stmt = select(RoomType.id).where(RoomType.hotel_id == hotel_id, RoomType.name == name)
    if room_type is not None:
        stmt = stmt.where(RoomType.id != room_type.id)
    if db.session.execute(stmt.limit(1)).first():
        raise RoomTypeNameTaken("Loại phòng này đã có trong khách sạn đã chọn.")
    if room_type is not None and room_type.hotel_id != hotel_id and db.session.execute(
        select(Room.id).where(Room.room_type_id == room_type.id).limit(1)
    ).first():
        raise RuleViolation("Loại phòng đã có phòng, không thể chuyển sang khách sạn khác.")
    return name


def _apply_room_type(room_type, data, name, amenity_ids):
    room_type.hotel_id = data["hotel_id"]
    room_type.name = name
    room_type.description = (data.get("description") or "").strip() or None
    room_type.base_price = data["base_price"]
    room_type.capacity = data["capacity"]
    room_type.amenities = (
        db.session.execute(
            select(Amenity).where(Amenity.id.in_(amenity_ids))
        ).scalars().all()
        if amenity_ids else []
    )


def create_room_type(data, amenity_ids, image_filename=None):
    name = _check_room_type(data)
    room_type = RoomType()
    try:
        _apply_room_type(room_type, data, name, amenity_ids)
        if image_filename:
            room_type.image_filename = image_filename
        db.session.add(room_type)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise RoomTypeNameTaken("Loại phòng này đã có trong khách sạn đã chọn.") from None
    except Exception:
        db.session.rollback()
        raise
    return room_type


def update_room_type(room_type, data, amenity_ids, image_filename=None):
    """Sửa loại phòng. Có ảnh mới thì thay ảnh và xóa ảnh cũ sau khi commit."""
    name = _check_room_type(data, room_type)
    old_image = room_type.image_filename
    try:
        _apply_room_type(room_type, data, name, amenity_ids)
        if image_filename:
            room_type.image_filename = image_filename
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise RoomTypeNameTaken("Loại phòng này đã có trong khách sạn đã chọn.") from None
    except Exception:
        db.session.rollback()
        raise
    if image_filename and old_image and old_image != image_filename:
        delete_image(old_image)
    return room_type


# ─── Quản lý tiện nghi ──────────────────────────────────────────────────────

def list_amenities_admin():
    """Tiện nghi kèm số khách sạn và số loại phòng đang dùng."""
    amenities = db.session.execute(select(Amenity).order_by(Amenity.name)).scalars().all()
    hotel_rows = db.session.execute(
        select(hotel_amenities.c.amenity_id, func.count())
        .group_by(hotel_amenities.c.amenity_id)
    ).all()
    type_rows = db.session.execute(
        select(room_type_amenities.c.amenity_id, func.count())
        .group_by(room_type_amenities.c.amenity_id)
    ).all()
    return (amenities,
            {amenity_id: n for amenity_id, n in hotel_rows},
            {amenity_id: n for amenity_id, n in type_rows})


def _amenity_name_taken(name, exclude_id=None):
    stmt = select(Amenity.id).where(Amenity.name == name)
    if exclude_id is not None:
        stmt = stmt.where(Amenity.id != exclude_id)
    return db.session.execute(stmt.limit(1)).first() is not None


def create_amenity(name, icon):
    name = name.strip()
    if _amenity_name_taken(name):
        raise AmenityNameTaken("Tiện nghi này đã tồn tại.")
    amenity = Amenity(name=name, icon=(icon or "").strip() or None)
    try:
        db.session.add(amenity)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise AmenityNameTaken("Tiện nghi này đã tồn tại.") from None
    except Exception:
        db.session.rollback()
        raise
    return amenity


def update_amenity(amenity, name, icon):
    name = name.strip()
    if _amenity_name_taken(name, exclude_id=amenity.id):
        raise AmenityNameTaken("Tiện nghi này đã tồn tại.")
    try:
        amenity.name = name
        amenity.icon = (icon or "").strip() or None
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise AmenityNameTaken("Tiện nghi này đã tồn tại.") from None
    except Exception:
        db.session.rollback()
        raise
    return amenity


def delete_amenity(amenity):
    """Xóa tiện nghi; các dòng ở bảng nối bị xóa theo (ON DELETE CASCADE)."""
    try:
        db.session.delete(amenity)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise