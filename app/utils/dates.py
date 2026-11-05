from datetime import date

MAX_NIGHTS = 30  # mỗi lần đặt tối đa 30 đêm

def nights_between(check_in: date, check_out: date) -> int:
    """Trả về số đêm giữ check_in và check_out"""
    delta = check_out - check_in
    if delta.days <= 0:
        raise ValueError("check_out phải sau check_in")
    return delta.days

def is_valid_date_range(check_in: date, check_out: date) -> bool:
    return check_out > check_in >= date.today()


def has_conflict(room_id: int, check_in: date, check_out: date,
                 exclude_booking_id: int | None = None) -> bool:
    """
    Kiểm tra phòng room_id có booking Pending/Confirmed nào
    trùng lịch với [check_in, check_out) không.
    Loại trừ exclude_booking_id khi xác nhận booking đang xét.
    """
    from ..models import Booking
    from ..extensions import db
    from sqlalchemy import select, and_

    filters = [
        Booking.room_id == room_id,
        Booking.status.in_(["Pending", "Confirmed"]),
        Booking.check_in < check_out,
        Booking.check_out > check_in,
    ]
    if exclude_booking_id is not None:
        filters.append(Booking.id != exclude_booking_id)

    stmt = select(Booking.id).where(and_(*filters)).limit(1)
    return db.session.execute(stmt).first() is not None