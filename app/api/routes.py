from flask import Blueprint, jsonify, request, url_for

from ..auth.services import authenticate
from ..bookings.services import (
    STAFF_ROLES, RoomUnavailable, change_status, create_booking,
    list_bookings, update_booking_info,
)
from ..extensions import csrf, db, limiter
from ..hotels.services import get_hotel_room_groups, parse_search_args, search_hotels_page
from ..models import Booking, Hotel
from ..rooms.services import get_active_room, list_available_rooms, room_is_free
from ..utils.dates import nights_between
from .auth import api_user_required, current_api_user, login_token
from .errors import ApiError, register_error_handlers
from .validators import (
    BOOKING_CREATE_SPEC, BOOKING_PATCH_SPEC, STATUSES, clean_fields, clean_reason,
    date_range, int_field, json_body, optional_date_range, validate_status,
)

api_bp = Blueprint("api", __name__)
csrf.exempt(api_bp)  # xác thực bằng header Authorization: Bearer, không dùng cookie
register_error_handlers(api_bp)


# ─── Tiện ích định dạng ─────────────────────────────────────────────────────

def ok(data, status=200):
    return jsonify(data=data), status


def money(value):
    return float(value) if value is not None else None


def image_url(filename):
    """Ảnh seed có tiền tố 'uploads/', ảnh upload là tên trần."""
    if not filename:
        return None
    name = filename if filename.startswith("uploads/") else f"uploads/{filename}"
    return url_for("static", filename=name)


def hotel_summary(hotel, price_from):
    return {
        "id": hotel.id, "name": hotel.name, "province": hotel.province,
        "address": hotel.address, "star_rating": hotel.star_rating,
        "image_url": image_url(hotel.image_filename), "price_from": money(price_from),
    }


def amenity_list(amenities):
    return [{"id": a.id, "name": a.name, "icon": a.icon} for a in amenities]


def room_dict(room):
    rt = room.room_type
    return {
        "id": room.id, "room_number": room.room_number, "floor": room.floor,
        "type": rt.name, "description": rt.description, "capacity": rt.capacity,
        "price_per_night": money(rt.base_price), "image_url": image_url(rt.image_filename),
        "amenities": amenity_list(rt.amenities),
        "hotel": {"id": room.hotel.id, "name": room.hotel.name,
                  "province": room.hotel.province, "address": room.hotel.address},
    }


def booking_dict(b):
    return {
        "id": b.id, "code": b.code, "status": b.status,
        "room": {"id": b.room.id, "room_number": b.room.room_number,
                 "type": b.room.room_type.name, "hotel": b.room.hotel.name},
        "checkin": b.check_in.isoformat(), "checkout": b.check_out.isoformat(),
        "nights": nights_between(b.check_in, b.check_out), "guests": b.guests,
        "guest_name": b.guest_name, "guest_phone": b.guest_phone,
        "guest_email": b.guest_email, "note": b.note,
        "total_price": money(b.total_price), "cancel_reason": b.cancel_reason,
        "created_at": b.created_at.isoformat(),
    }


def load_booking(booking_id, user, owner_only=False):
    """404 nếu không có; 403 nếu đụng booking của người khác (nhân viên xem được tất cả, trừ owner_only)."""
    booking = db.session.get(Booking, booking_id)
    if booking is None:
        raise ApiError(404, "Không tìm thấy booking.")
    is_staff = user.role in STAFF_ROLES
    if (owner_only or not is_staff) and booking.user_id != user.id:
        raise ApiError(403, "Bạn không có quyền với booking này.")
    return booking


# ─── Thông tin ──────────────────────────────────────────────────────────────

@api_bp.get("/")
def index():
    return ok({"service": "Mini Hotel Booking API", "version": 1})


# ─── Xác thực ───────────────────────────────────────────────────────────────

@api_bp.post("/auth/login")
@limiter.limit("5 per minute")
def login():
    body = json_body()
    email, password = body.get("email"), body.get("password")
    errors = {}
    if not isinstance(email, str) or not email.strip():
        errors["email"] = "Bắt buộc."
    if not isinstance(password, str) or not password:
        errors["password"] = "Bắt buộc."
    if errors:
        raise ApiError(400, "Dữ liệu không hợp lệ.", errors)

    user = authenticate(email, password)
    if user is None:
        raise ApiError(401, "Email hoặc mật khẩu không đúng.")
    token, expires_in = login_token(user)
    return ok({"access_token": token, "token_type": "Bearer", "expires_in": expires_in,
               "user": {"id": user.id, "full_name": user.full_name, "role": user.role}})


# ─── Phòng (công khai) ──────────────────────────────────────────────────────

@api_bp.get("/rooms/available")
def rooms_available():
    ci, co = date_range(request.args.get("checkin"), request.args.get("checkout"), allow_past=False)
    guests = int_field(request.args.get("guests"), "guests", 1, 20, required=False) or 1
    hotel_id = int_field(request.args.get("hotel_id"), "hotel_id", 1, required=False)
    room_type_id = int_field(request.args.get("room_type"), "room_type", 1, required=False)
    max_price = int_field(request.args.get("max_price"), "max_price", 0, required=False)

    nights = nights_between(ci, co)
    rooms = list_available_rooms(ci, co, guests, hotel_id, room_type_id, max_price)
    return ok({
        "checkin": ci.isoformat(), "checkout": co.isoformat(), "nights": nights,
        "rooms": [{
            "id": r.id, "room_number": r.room_number, "type": r.room_type.name,
            "capacity": r.room_type.capacity,
            "price_per_night": money(r.room_type.base_price),
            "total_price": money(r.room_type.base_price * nights),
            "hotel": {"id": r.hotel.id, "name": r.hotel.name},
        } for r in rooms],
    })


@api_bp.get("/rooms/<int:room_id>")
def room_detail(room_id):
    room = get_active_room(room_id)
    data = room_dict(room)
    ci, co = optional_date_range(request.args)
    if ci and co:
        nights = nights_between(ci, co)
        data.update({
            "checkin": ci.isoformat(), "checkout": co.isoformat(), "nights": nights,
            "total_price": money(room.room_type.base_price * nights),
            "available": room_is_free(room.id, ci, co),
        })
    return ok(data)


# ─── Khách sạn (công khai) ──────────────────────────────────────────────────

@api_bp.get("/hotels")
def hotels_list():
    params, errors = parse_search_args(request.args)
    if errors:
        raise ApiError(400, "Tham số tìm kiếm không hợp lệ.", errors)

    pagination, prices = search_hotels_page(params)
    ci, co = params["dates"]
    return ok({
        "checkin": params["checkin"], "checkout": params["checkout"],
        "nights": nights_between(ci, co) if ci and co else None,
        "hotels": [hotel_summary(h, prices.get(h.id)) for h in pagination.items],
        "page": pagination.page, "pages": pagination.pages,
        "total": pagination.total, "per_page": pagination.per_page,
    })


@api_bp.get("/hotels/<int:hotel_id>")
def hotel_detail(hotel_id):
    hotel = db.first_or_404(db.select(Hotel).filter_by(id=hotel_id, is_active=True))
    ci, co = optional_date_range(request.args)
    guests = int_field(request.args.get("guests"), "guests", 1, 20, required=False) or 1

    groups = get_hotel_room_groups(
        hotel_id, ci.isoformat() if ci else "", co.isoformat() if co else "", guests)
    return ok({
        "id": hotel.id, "name": hotel.name, "province": hotel.province,
        "address": hotel.address, "star_rating": hotel.star_rating,
        "description": hotel.description, "map_url": hotel.map_url,
        "image_url": image_url(hotel.image_filename),
        "amenities": amenity_list(hotel.amenities),
        "checkin": ci.isoformat() if ci else "", "checkout": co.isoformat() if co else "",
        "nights": nights_between(ci, co) if ci and co else None,
        "room_types": [{
            "id": g["type"].id, "name": g["type"].name,
            "description": g["type"].description, "capacity": g["type"].capacity,
            "price_per_night": money(g["type"].base_price),
            "total_price": money(g["total"]),
            "image_url": image_url(g["type"].image_filename),
            "rooms": [{"id": r.id, "room_number": r.room_number, "floor": r.floor}
                      for r in g["rooms"]],
        } for g in groups],
    })


# ─── Booking (JWT) ──────────────────────────────────────────────────────────

@api_bp.get("/bookings")
@api_user_required()
def bookings_list():
    user = current_api_user()
    status = (request.args.get("status") or "").strip()
    if status and status not in STATUSES:
        raise ApiError(400, "Trạng thái không hợp lệ.",
                       {"status": "Phải là một trong: " + ", ".join(STATUSES) + "."})
    page = int_field(request.args.get("page"), "page", 1, required=False) or 1

    pagination = list_bookings(
        status=status or None,
        user_id=None if user.role in STAFF_ROLES else user.id,  # customer chỉ thấy của mình
        page=page,
    )
    return ok({
        "bookings": [booking_dict(b) for b in pagination.items],
        "page": pagination.page, "pages": pagination.pages,
        "total": pagination.total, "per_page": pagination.per_page,
    })


@api_bp.get("/bookings/<int:booking_id>")
@api_user_required()
def bookings_detail(booking_id):
    return ok(booking_dict(load_booking(booking_id, current_api_user())))


@api_bp.post("/bookings")
@api_user_required("customer")
def bookings_create():
    user = current_api_user()
    body = json_body()
    room_id = int_field(body.get("room_id"), "room_id", 1)
    ci, co = date_range(body.get("checkin"), body.get("checkout"), allow_past=False)
    guests = int_field(body.get("guests", 1), "guests", 1, 20)
    fields = clean_fields(body, BOOKING_CREATE_SPEC)

    try:
        booking = create_booking(
            user_id=user.id, room_id=room_id, check_in=ci, check_out=co, guests=guests,
            guest_name=fields["guest_name"], guest_phone=fields["guest_phone"],
            guest_email=fields["guest_email"], note=fields.get("note"),
        )
    except RoomUnavailable as e:
        raise ApiError(409, str(e) or "Phòng không còn trống.") from None
    except ValueError as e:
        raise ApiError(400, str(e)) from None
    return ok(booking_dict(booking), 201)


@api_bp.patch("/bookings/<int:booking_id>")
@api_user_required()
def bookings_update(booking_id):
    user = current_api_user()
    booking = load_booking(booking_id, user, owner_only=True)
    fields = clean_fields(json_body(), BOOKING_PATCH_SPEC, partial=True)
    if not fields:
        raise ApiError(400, "Không có trường nào để cập nhật.",
                       {"body": "Gửi ít nhất một trong: guest_name, guest_phone, note."})
    try:
        update_booking_info(booking, user, fields)
    except PermissionError as e:
        raise ApiError(403, str(e)) from None
    except ValueError as e:
        raise ApiError(409, str(e)) from None
    return ok(booking_dict(booking))


@api_bp.put("/bookings/<int:booking_id>/status")
@api_user_required("receptionist", "admin")
def bookings_status(booking_id):
    user = current_api_user()
    booking = db.session.get(Booking, booking_id)
    if booking is None:
        raise ApiError(404, "Không tìm thấy booking.")

    body = json_body()
    status = validate_status(body.get("status"))
    reason = clean_reason(body.get("reason"))
    if status == "Cancelled" and not reason:
        raise ApiError(400, "Cần nhập lý do khi hủy hoặc từ chối booking.",
                       {"reason": "Bắt buộc khi chuyển sang Cancelled."})
    try:
        change_status(booking, status, user, reason)
    except PermissionError as e:
        raise ApiError(403, str(e)) from None
    except ValueError as e:
        raise ApiError(409, str(e)) from None
    return ok(booking_dict(booking))


@api_bp.delete("/bookings/<int:booking_id>")
@api_user_required()
def bookings_cancel(booking_id):
    """Hủy booking: không xóa dòng, chuyển sang Cancelled qua change_status()."""
    user = current_api_user()
    booking = load_booking(booking_id, user)

    body = request.get_json(silent=True)
    raw_reason = body.get("reason") if isinstance(body, dict) else None
    reason = clean_reason(raw_reason or request.args.get("reason"))
    if user.role in STAFF_ROLES and not reason:
        raise ApiError(400, "Nhân viên cần nhập lý do khi hủy booking.",
                       {"reason": "Bắt buộc (gửi trong body JSON hoặc query ?reason=)."})
    try:
        change_status(booking, "Cancelled", user, reason)
    except PermissionError as e:
        raise ApiError(403, str(e)) from None
    except ValueError as e:
        raise ApiError(409, str(e)) from None
    return ok(booking_dict(booking))