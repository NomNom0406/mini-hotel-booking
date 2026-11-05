import os
from datetime import date as date_type

from flask import current_app
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import contains_eager

from ..extensions import db
from ..models import (
    Amenity, Booking, Hotel, Room, RoomType, hotel_amenities, room_type_amenities,
)
from ..utils.dates import nights_between

BLOCKING_STATUSES = ("Pending", "Confirmed")  # chỉ booking ở các trạng thái này giữ phòng
PER_PAGE = 9
DEFAULT_SORT = "stars_desc"
SORT_LABELS = {
    "stars_desc": "Hạng sao cao nhất",
    "price_asc": "Giá thấp đến cao",
    "price_desc": "Giá cao đến thấp",
}


class HotelNameTaken(ValueError):
    """Tên khách sạn đã tồn tại."""


# ─── Ảnh upload ─────────────────────────────────────────────────────────────

def upload_folder() -> str:
    """Thư mục lưu ảnh upload (tuyệt đối), tính từ gốc dự án nếu cấu hình là đường dẫn tương đối."""
    folder = current_app.config["UPLOAD_FOLDER"]
    if not os.path.isabs(folder):
        folder = os.path.join(current_app.root_path, "..", folder)
    return os.path.abspath(folder)


def delete_image(filename) -> None:
    """Xóa ảnh do chức năng upload tạo ra (tên trần). Không đụng ảnh seed có đường dẫn con."""
    if not filename or filename != os.path.basename(filename):
        return
    try:
        os.remove(os.path.join(upload_folder(), filename))
    except OSError:
        pass


# ─── Tìm kiếm ───────────────────────────────────────────────────────────────

def parse_dates(checkin, checkout):
    """'YYYY-MM-DD' x2 -> (date, date). Thiếu, sai định dạng hoặc trả <= nhận thì (None, None)."""
    try:
        ci = date_type.fromisoformat(checkin) if checkin else None
        co = date_type.fromisoformat(checkout) if checkout else None
    except ValueError:
        return None, None
    if ci and co and co > ci:
        return ci, co
    return None, None


def booked_rooms_subquery(ci, co):
    """Truy vấn con: id các phòng đang bị giữ trong [ci, co) (booking Pending/Confirmed chồng ngày)."""
    return select(Booking.room_id).where(
        Booking.status.in_(BLOCKING_STATUSES),
        Booking.check_in < co,
        Booking.check_out > ci,
    )


def _int_arg(args, key, errors, minimum=None, maximum=None):
    raw = (args.get(key) or "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        errors[key] = f"Tham số {key} phải là số nguyên."
        return None
    if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
        errors[key] = f"Tham số {key} nằm ngoài khoảng cho phép."
        return None
    return value


def parse_search_args(args):
    """Đọc và kiểm tra tham số tìm kiếm từ query string (dùng chung cho web và API).

    args: MultiDict (request.args). Trả (params, errors). Tham số sai không làm hỏng
    kết quả: bị bỏ qua và ghi vào errors (web hiện cảnh báo, API trả 400).
    """
    errors = {}
    province = (args.get("province") or "").strip()
    checkin = (args.get("checkin") or "").strip()
    checkout = (args.get("checkout") or "").strip()

    ci = co = None
    if checkin or checkout:
        ci, co = parse_dates(checkin, checkout)
        if not (ci and co):
            errors["dates"] = ("Ngày không hợp lệ: cần đủ cả ngày nhận và ngày trả, "
                               "ngày trả phải sau ngày nhận.")
            checkin = checkout = ""
        elif ci < date_type.today():
            errors["dates"] = "Ngày nhận không được trong quá khứ."
            ci = co = None
            checkin = checkout = ""

    guests = _int_arg(args, "guests", errors, 1, 20) or 1
    min_price = _int_arg(args, "min_price", errors, 0)
    max_price = _int_arg(args, "max_price", errors, 0)
    if min_price is not None and max_price is not None and min_price > max_price:
        errors["min_price"] = "Giá tối thiểu không được lớn hơn giá tối đa."
        min_price = max_price = None
    stars = _int_arg(args, "stars", errors, 1, 5)

    amenities = []
    for raw in args.getlist("amenity"):
        try:
            amenities.append(int(raw))
        except ValueError:
            errors["amenity"] = "Tiện nghi phải là số nguyên."

    sort = (args.get("sort") or "").strip() or DEFAULT_SORT
    if sort not in SORT_LABELS:
        errors["sort"] = "Cách sắp xếp không hợp lệ."
        sort = DEFAULT_SORT

    page = _int_arg(args, "page", {}, 1) or 1

    params = {
        "province": province, "checkin": checkin, "checkout": checkout,
        "dates": (ci, co), "guests": guests,
        "min_price": min_price, "max_price": max_price, "stars": stars,
        "amenities": amenities, "sort": sort, "page": page,
    }
    return params, errors


def search_query(params):
    """Tham số để dựng lại URL tìm kiếm (không có page), bỏ giá trị rỗng/mặc định."""
    query = {
        "province": params["province"], "checkin": params["checkin"],
        "checkout": params["checkout"],
        "guests": params["guests"] if params["guests"] > 1 else None,
        "min_price": params["min_price"], "max_price": params["max_price"],
        "stars": params["stars"], "amenity": params["amenities"],
        "sort": params["sort"] if params["sort"] != DEFAULT_SORT else None,
    }
    return {k: v for k, v in query.items() if v not in (None, "", [])}


def _qualifying_rooms(params):
    """Subquery: mỗi khách sạn có phòng hợp lệ và giá thấp nhất trong các phòng đó.

    Phòng hợp lệ = đang hoạt động, đủ sức chứa, giá loại phòng trong khoảng lọc,
    và (khi có ngày) không trùng lịch. Khách sạn không có phòng nào hợp lệ thì bị loại.
    """
    ci, co = params["dates"]
    stmt = (
        select(Room.hotel_id.label("hotel_id"),
               func.min(RoomType.base_price).label("price_from"))
        .join(RoomType, Room.room_type_id == RoomType.id)
        .where(Room.is_active == True, RoomType.capacity >= params["guests"])
    )
    if params["min_price"] is not None:
        stmt = stmt.where(RoomType.base_price >= params["min_price"])
    if params["max_price"] is not None:
        stmt = stmt.where(RoomType.base_price <= params["max_price"])
    if ci and co:
        stmt = stmt.where(Room.id.not_in(booked_rooms_subquery(ci, co)))
    return stmt.group_by(Room.hotel_id).subquery()


def _ordering(sort, price_from):
    if sort == "price_asc":
        return (price_from.asc(), Hotel.star_rating.desc(), Hotel.name, Hotel.id)
    if sort == "price_desc":
        return (price_from.desc(), Hotel.star_rating.desc(), Hotel.name, Hotel.id)
    return (Hotel.star_rating.desc(), price_from.asc(), Hotel.name, Hotel.id)


def search_hotels_page(params, per_page=PER_PAGE):
    """Một trang kết quả tìm kiếm: (Pagination của Hotel, {hotel_id: giá từ}).

    Lọc: tỉnh, ngày + số khách, khoảng giá, hạng sao (từ N sao trở lên),
    tiện nghi (khách sạn phải có đủ mọi tiện nghi đã chọn).
    """
    rooms_sq = _qualifying_rooms(params)
    stmt = (
        select(Hotel)
        .join(rooms_sq, rooms_sq.c.hotel_id == Hotel.id)
        .where(Hotel.is_active == True)
    )
    if params["province"]:
        stmt = stmt.where(Hotel.province == params["province"])
    if params["stars"]:
        stmt = stmt.where(Hotel.star_rating >= params["stars"])
    for amenity_id in params["amenities"]:
        stmt = stmt.where(Hotel.id.in_(
            select(hotel_amenities.c.hotel_id)
            .where(hotel_amenities.c.amenity_id == amenity_id)
        ))

    stmt = stmt.order_by(*_ordering(params["sort"], rooms_sq.c.price_from))
    pagination = db.paginate(stmt, page=params["page"], per_page=per_page, error_out=False)

    ids = [h.id for h in pagination.items]
    prices = {}
    if ids:
        rows = db.session.execute(
            select(rooms_sq.c.hotel_id, rooms_sq.c.price_from)
            .where(rooms_sq.c.hotel_id.in_(ids))
        ).all()
        prices = {hotel_id: price for hotel_id, price in rows}
    return pagination, prices


def get_provinces():
    return db.session.execute(
        db.select(Hotel.province).distinct().order_by(Hotel.province)
    ).scalars().all()


def get_hotel_room_groups(hotel_id, checkin=None, checkout=None, guests=1):
    """Phòng của khách sạn gom theo loại phòng.

    Có ngày hợp lệ: chỉ giữ phòng đủ sức chứa và không trùng lịch, kèm tổng tiền.
    Trả list dict: {type, rooms, nights, total (None nếu chưa chọn ngày)}.
    """
    ci, co = parse_dates(checkin, checkout)
    rooms = db.session.execute(
        select(Room)
        .join(RoomType, Room.room_type_id == RoomType.id)
        .options(contains_eager(Room.room_type))
        .where(Room.hotel_id == hotel_id, Room.is_active == True)
        .order_by(RoomType.base_price, RoomType.id, Room.room_number)
    ).scalars().all()

    nights = None
    if ci and co:
        booked = set(db.session.execute(
            booked_rooms_subquery(ci, co).where(Booking.room_id.in_([r.id for r in rooms]))
        ).scalars().all()) if rooms else set()
        rooms = [r for r in rooms
                 if r.room_type.capacity >= guests and r.id not in booked]
        nights = nights_between(ci, co)

    groups = {}
    for room in rooms:
        group = groups.setdefault(room.room_type_id, {
            "type": room.room_type,
            "rooms": [],
            "nights": nights,
            "total": room.room_type.base_price * nights if nights else None,
        })
        group["rooms"].append(room)
    return list(groups.values())


# ─── Quản lý khách sạn (admin) ──────────────────────────────────────────────

def list_hotels_admin():
    """Tất cả khách sạn (cả đang ẩn) và số phòng của từng khách sạn: 2 truy vấn, không N+1."""
    hotels = db.session.execute(
        select(Hotel).order_by(Hotel.province, Hotel.name)
    ).scalars().all()
    rows = db.session.execute(
        select(Room.hotel_id, func.count(Room.id)).group_by(Room.hotel_id)
    ).all()
    return hotels, {hotel_id: count for hotel_id, count in rows}


def get_amenity_choices():
    """[(id, tên)] cho ô chọn tiện nghi."""
    rows = db.session.execute(
        select(Amenity.id, Amenity.name).order_by(Amenity.name)
    ).all()
    return [(amenity_id, name) for amenity_id, name in rows]


def _name_taken(name, exclude_id=None):
    stmt = select(Hotel.id).where(Hotel.name == name)
    if exclude_id is not None:
        stmt = stmt.where(Hotel.id != exclude_id)
    return db.session.execute(stmt.limit(1)).first() is not None


def _apply(hotel, data, amenity_ids):
    hotel.name = data["name"].strip()
    hotel.province = data["province"].strip()
    hotel.address = data["address"].strip()
    hotel.star_rating = data["star_rating"]
    hotel.description = (data.get("description") or "").strip() or None
    hotel.map_url = (data.get("map_url") or "").strip() or None
    hotel.amenities = (
        db.session.execute(
            select(Amenity).where(Amenity.id.in_(amenity_ids))
        ).scalars().all()
        if amenity_ids else []
    )


def create_hotel(data, amenity_ids, image_filename=None):
    name = data["name"].strip()
    if _name_taken(name):
        raise HotelNameTaken("Tên khách sạn đã tồn tại.")
    hotel = Hotel(is_active=True)
    try:
        _apply(hotel, data, amenity_ids)
        if image_filename:
            hotel.image_filename = image_filename
        db.session.add(hotel)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise HotelNameTaken("Tên khách sạn đã tồn tại.") from None
    except Exception:
        db.session.rollback()
        raise
    return hotel


def update_hotel(hotel, data, amenity_ids, image_filename=None):
    """Sửa khách sạn. Có image_filename mới thì thay ảnh và xóa ảnh cũ sau khi commit."""
    name = data["name"].strip()
    if _name_taken(name, exclude_id=hotel.id):
        raise HotelNameTaken("Tên khách sạn đã tồn tại.")
    old_image = hotel.image_filename
    try:
        _apply(hotel, data, amenity_ids)
        if image_filename:
            hotel.image_filename = image_filename
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise HotelNameTaken("Tên khách sạn đã tồn tại.") from None
    except Exception:
        db.session.rollback()
        raise
    if image_filename and old_image and old_image != image_filename:
        delete_image(old_image)
    return hotel


def set_hotel_active(hotel, active):
    """Ẩn/hiện khách sạn. Không có thao tác xóa: khách sạn đã có booking chỉ được ẩn."""
    try:
        hotel.is_active = active
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return hotel



def delete_hotel(hotel):
    """Xóa khách sạn cùng toàn bộ dữ liệu liên quan trong MỘT transaction.

    Thứ tự: booking của các phòng, liên kết tiện nghi của loại phòng, phòng,
    loại phòng, liên kết tiện nghi của khách sạn, rồi khách sạn. Có lỗi thì rollback.
    Sau khi commit mới xóa ảnh upload (tên trần) của khách sạn và các loại phòng;
    ảnh có đường dẫn con (ảnh seed, ảnh trong thư mục) không bị đụng tới.
    """
    hotel_id = hotel.id
    images = [hotel.image_filename] + [
        name for (name,) in db.session.execute(
            select(RoomType.image_filename).where(RoomType.hotel_id == hotel_id)
        ).all()
    ]
    room_ids = select(Room.id).where(Room.hotel_id == hotel_id)
    type_ids = select(RoomType.id).where(RoomType.hotel_id == hotel_id)
    try:
        db.session.execute(
            delete(Booking).where(Booking.room_id.in_(room_ids))
            .execution_options(synchronize_session=False))
        db.session.execute(
            delete(room_type_amenities)
            .where(room_type_amenities.c.room_type_id.in_(type_ids)))
        db.session.execute(
            delete(Room).where(Room.hotel_id == hotel_id)
            .execution_options(synchronize_session=False))
        db.session.execute(
            delete(RoomType).where(RoomType.hotel_id == hotel_id)
            .execution_options(synchronize_session=False))
        db.session.execute(
            delete(hotel_amenities).where(hotel_amenities.c.hotel_id == hotel_id))
        db.session.execute(
            delete(Hotel).where(Hotel.id == hotel_id)
            .execution_options(synchronize_session=False))
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    for name in images:
        delete_image(name)