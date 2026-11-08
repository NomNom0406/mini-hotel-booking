import calendar
import secrets
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.orm.exc import StaleDataError

from ..extensions import db
from ..models import Booking, Room
from ..utils.dates import MAX_NIGHTS, nights_between


class RoomUnavailable(ValueError):
    """Phòng không còn trống (trùng lịch, đã ẩn, hoặc thua cuộc đua)."""


STAFF_ROLES = {"receptionist", "admin"}

# Cancelled và Completed là trạng thái cuối
ALLOWED_TRANSITIONS = {
    "Pending":   {"Confirmed", "Cancelled"},
    "Confirmed": {"Completed", "Cancelled"},
    "Cancelled": set(),
    "Completed": set(),
}

# Booking ở các trạng thái này đang giữ phòng
_BLOCKING_STATUSES = ("Pending", "Confirmed")


def gen_code() -> str:
    """Mã booking dạng BK20270301A1B2 (14 ký tự, cột code dài 20)."""
    return "BK" + date.today().strftime("%Y%m%d") + secrets.token_hex(2).upper()


def _room_has_conflict(room_id: int, check_in: date, check_out: date,
                       exclude_booking_id: int | None = None) -> bool:
    """Có booking Pending/Confirmed nào của phòng giao với [check_in, check_out)."""
    stmt = select(Booking.id).where(
        Booking.room_id == room_id,
        Booking.status.in_(_BLOCKING_STATUSES),
        Booking.check_in < check_out,
        Booking.check_out > check_in,
    )
    if exclude_booking_id is not None:
        stmt = stmt.where(Booking.id != exclude_booking_id)
    return db.session.execute(stmt.limit(1)).first() is not None


def _unique_code() -> str:
    for _ in range(10):
        code = gen_code()
        if not db.session.execute(select(Booking.id).filter_by(code=code)).first():
            return code
    raise RuntimeError("Không sinh được mã booking duy nhất.")


def create_booking(user_id, room_id, check_in, check_out, guests,
                   guest_name, guest_phone, guest_email, note=None) -> Booking:
    """Tạo booking Pending trong một transaction, có khóa lạc quan trên Room."""
    try:
        room = db.session.get(Room, room_id)
        if room is None or not room.is_active:
            raise RoomUnavailable("Phòng không khả dụng.")
        if check_in < date.today():
            raise ValueError("Ngày nhận phòng không được trong quá khứ.")
        if check_out <= check_in:
            raise ValueError("Ngày trả phòng phải sau ngày nhận phòng.")
        if (check_out - check_in).days > MAX_NIGHTS:
            raise ValueError(f"Mỗi lần đặt tối đa {MAX_NIGHTS} đêm.")
        if guests > room.room_type.capacity:
            raise ValueError("Số khách vượt quá sức chứa của phòng.")
        if _room_has_conflict(room_id, check_in, check_out):
            raise RoomUnavailable("Phòng đã được đặt trong khoảng thời gian này.")

        nights = nights_between(check_in, check_out)
        booking = Booking(
            code=_unique_code(),
            user_id=user_id,
            room_id=room_id,
            check_in=check_in,
            check_out=check_out,
            guests=guests,
            guest_name=guest_name,
            guest_phone=guest_phone,
            guest_email=guest_email,
            note=note,
            total_price=room.room_type.base_price * nights,  # server tính, không nhận từ form
            status="Pending",
        )
        db.session.add(booking)
        # Ép UPDATE rooms để tăng version: hai luồng cùng đặt một phòng thì
        # luồng sau gặp StaleDataError.
        flag_modified(room, "is_active")
        db.session.commit()
        return booking
    except StaleDataError:
        db.session.rollback()
        raise RoomUnavailable("Phòng vừa được đặt bởi người khác.") from None
    except Exception:
        db.session.rollback()
        raise


def change_status(booking: Booking, new_status: str, actor, reason: str | None = None) -> Booking:
    """Đổi trạng thái theo ALLOWED_TRANSITIONS. Dùng chung cho web, AJAX và API.

    PermissionError: actor không có quyền. ValueError: chuyển sai (không đổi dữ liệu).
    """
    reason = (reason or "").strip() or None
    is_staff = actor.role in STAFF_ROLES
    is_owner = booking.user_id == actor.id

    if not is_staff:
        # Customer: chỉ chủ booking, và chỉ được hủy
        if not is_owner or new_status != "Cancelled":
            raise PermissionError("Bạn không có quyền thực hiện thao tác này.")

    if new_status not in ALLOWED_TRANSITIONS.get(booking.status, set()):
        raise ValueError(f"Không thể chuyển từ {booking.status} sang {new_status}.")

    today = date.today()
    if new_status == "Cancelled":
        if not is_staff and today >= booking.check_in:
            raise ValueError("Chỉ được tự hủy trước ngày nhận phòng.")
        if is_staff and reason is None:
            raise ValueError("Vui lòng nhập lý do khi từ chối hoặc hủy booking.")
    elif new_status == "Confirmed":
        if _room_has_conflict(booking.room_id, booking.check_in, booking.check_out,
                              exclude_booking_id=booking.id):
            raise ValueError("Phòng đã có booking khác trong khoảng thời gian này.")
    elif new_status == "Completed":
        if today < booking.check_out:
            raise ValueError("Chỉ hoàn tất từ ngày trả phòng trở đi.")

    # Nhân viên hủy booking Confirmed từ ngày nhận phòng trở đi: khách vẫn bị tính tiền.
    # Tính TRƯỚC khi đổi status (lúc này booking.status còn là trạng thái cũ).
    charge = (new_status == "Cancelled" and is_staff
              and booking.status == "Confirmed" and today >= booking.check_in)

    try:
        booking.status = new_status
        if new_status == "Cancelled":
            booking.cancel_reason = reason
            booking.is_charged = charge
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return booking


def _parse_date(value):
    """'YYYY-MM-DD' -> date, sai định dạng thì None."""
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def list_bookings(hotel_id=None, status=None, date_from=None, date_to=None,
                  q=None, user_id=None, page=1, per_page=10):
    """Danh sách booking cho nhân viên: lọc + phân trang (order_by ổn định)."""
    stmt = select(Booking).join(Room, Booking.room_id == Room.id)
    if user_id:
        stmt = stmt.where(Booking.user_id == user_id)
    if hotel_id:
        stmt = stmt.where(Room.hotel_id == hotel_id)
    if status:
        stmt = stmt.where(Booking.status == status)
    d_from, d_to = _parse_date(date_from), _parse_date(date_to)
    if d_from:
        stmt = stmt.where(Booking.check_in >= d_from)
    if d_to:
        stmt = stmt.where(Booking.check_in <= d_to)
    if q:
        stmt = stmt.where(
            Booking.code.ilike("%" + q + "%")
            | Booking.guest_name.ilike("%" + q + "%")
        )
    stmt = stmt.order_by(Booking.created_at.desc(), Booking.id.desc())
    return db.paginate(stmt, page=page, per_page=per_page, error_out=False)



def parse_month(value) -> date:
    """'YYYY-MM' -> ngày đầu tháng; sai hoặc rỗng thì lấy tháng hiện tại."""
    try:
        return date.fromisoformat(str(value) + "-01")
    except ValueError:
        return date.today().replace(day=1)


def get_calendar_data(hotel_id: int, month_start: date) -> dict:
    """Lưới phòng x ngày của một khách sạn trong một tháng (chỉ đọc)."""
    days = calendar.monthrange(month_start.year, month_start.month)[1]
    month_end = month_start + timedelta(days=days)  # ngày đầu tháng sau

    rooms = db.session.execute(
        select(Room)
        .options(joinedload(Room.room_type))
        .where(Room.hotel_id == hotel_id, Room.is_active == True)
        .order_by(Room.floor, Room.room_number)
    ).scalars().all()

    bookings = db.session.execute(
        select(Booking).where(
            Booking.room_id.in_([r.id for r in rooms]),
            Booking.check_in < month_end,
            Booking.check_out > month_start,
        )
    ).scalars().all() if rooms else []

    # Booking đã hủy vẽ trước để booking đang giữ phòng đè lên
    bookings.sort(key=lambda b: b.status != "Cancelled")
    cells = {r.id: {} for r in rooms}
    for b in bookings:
        day = max(b.check_in, month_start)
        end = min(b.check_out, month_end)  # đêm cuối là check_out - 1
        while day < end:
            cells[b.room_id][day.day] = {"status": b.status, "code": b.code}
            day += timedelta(days=1)

    return {
        "hotel_id": hotel_id,
        "month": month_start.strftime("%Y-%m"),
        "days": days,
        "rooms": [
            {"id": r.id, "room_number": r.room_number, "type": r.room_type.name,
             "cells": cells[r.id]}
            for r in rooms
        ],
    }



def update_booking_info(booking, actor, changes):
    """Chủ booking sửa guest_name, guest_phone, note khi còn Pending.

    changes: dict chứa một số khóa trong {guest_name, guest_phone, note}.
    PermissionError: không phải chủ booking. ValueError: booking không còn Pending.
    """
    if booking.user_id != actor.id:
        raise PermissionError("Bạn không có quyền sửa booking này.")
    if booking.status != "Pending":
        raise ValueError("Chỉ sửa được booking đang chờ xác nhận.")
    try:
        for key in ("guest_name", "guest_phone", "note"):
            if key in changes:
                setattr(booking, key, changes[key])
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return booking


# ─── Tự động cập nhật trạng thái ────────────────────────────────────────────

AUTO_COMPLETE_AFTER_DAYS = 3
AUTO_CANCEL_REASON = "Tự động hủy: đã qua ngày nhận phòng mà booking chưa được xác nhận."


def auto_update_bookings(today: date | None = None, dry_run: bool = False) -> dict:
    """Tự động cập nhật trạng thái booking (gọi khi mở các trang quản lý).

    - Pending đã qua ngày nhận phòng: chuyển Cancelled kèm lý do.
    - Confirmed đã quá ngày trả phòng AUTO_COMPLETE_AFTER_DAYS ngày: chuyển Completed.
    Booking đã Completed hoặc Cancelled không bị đụng tới.
    dry_run=True: chỉ trả danh sách mã booking sẽ đổi, không ghi DB.
    """
    today = today or date.today()

    to_cancel = Booking.query.filter(
        Booking.status == "Pending", Booking.check_in < today
    ).all()
    to_complete = [
        b for b in Booking.query.filter(
            Booking.status == "Confirmed", Booking.check_out < today
        ).all()
        if (today - b.check_out).days >= AUTO_COMPLETE_AFTER_DAYS
    ]
    result = {
        "cancelled": [b.code for b in to_cancel],
        "completed": [b.code for b in to_complete],
    }
    if dry_run or not (to_cancel or to_complete):
        return result

    try:
        for b in to_cancel:
            if "Cancelled" in ALLOWED_TRANSITIONS.get(b.status, set()):
                b.status = "Cancelled"
                b.cancel_reason = AUTO_CANCEL_REASON
        for b in to_complete:
            if "Completed" in ALLOWED_TRANSITIONS.get(b.status, set()):
                b.status = "Completed"
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return result