#imports, hằng số, helper
from calendar import monthrange
from datetime import date, datetime, timedelta

from sqlalchemy import and_, extract, func, or_, select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from ..auth.services import EmailTaken
from ..extensions import db
from ..models import Booking, Hotel, Room, User

MONTHS_WINDOW = 6
REVENUE_STATUSES = ("Confirmed", "Completed")
BOOKING_STATUSES = ("Pending", "Confirmed", "Cancelled", "Completed")


def _last_months(n=MONTHS_WINDOW):
    today = date.today()
    year, month = today.year, today.month
    months = []
    for _ in range(n):
        months.append((year, month))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    months.reverse()
    return months


def _scoped(query, hotel_id):
    query = query.select_from(Booking).join(Room, Booking.room_id == Room.id)
    if hotel_id is not None:
        query = query.filter(Room.hotel_id == hotel_id)
    return query


def _count_active_rooms(hotel_id):
    query = db.session.query(func.count(Room.id)).filter(Room.is_active == True)
    if hotel_id is not None:
        query = query.filter(Room.hotel_id == hotel_id)
    return query.scalar() or 0


#doanh thu theo tháng
def get_revenue_by_month(hotel_id=None):
    months = _last_months()
    start = date(months[0][0], months[0][1], 1)
    year = extract("year", Booking.check_in)
    month = extract("month", Booking.check_in)

    rows = (
        _scoped(db.session.query(year, month, func.sum(Booking.total_price)), hotel_id)
        .filter(
            or_(
                Booking.status.in_(REVENUE_STATUSES),
                # hủy muộn do nhân viên (is_charged) vẫn là doanh thu
                and_(Booking.status == "Cancelled", Booking.is_charged == True),
            ),
            Booking.check_in >= start,
        )
        .group_by(year, month)
        .all()
    )
    totals = {(int(y), int(m)): float(total or 0) for y, m, total in rows}
    return [
        {"month": f"{y}-{m:02d}", "revenue": totals.get((y, m), 0.0)}
        for y, m in months
    ]

#công suất phòng (theo tháng và hôm nay)
def get_occupancy_by_month(hotel_id=None):
    active_rooms = _count_active_rooms(hotel_id)
    result = []
    for y, m in _last_months():
        days = monthrange(y, m)[1]
        start = date(y, m, 1)
        end = start + timedelta(days=days)

        rows = (
            _scoped(db.session.query(Booking.check_in, Booking.check_out), hotel_id)
            .filter(
                Booking.status.in_(REVENUE_STATUSES),
                Booking.check_in < end,
                Booking.check_out > start,
            )
            .all()
        )
        nights = sum((min(c_out, end) - max(c_in, start)).days for c_in, c_out in rows)
        capacity = active_rooms * days
        rate = round(nights / capacity * 100, 1) if capacity else 0.0
        result.append({"month": f"{y}-{m:02d}", "occupancy": rate})
    return result


def get_occupancy_today(hotel_id=None):
    today = date.today()
    active_rooms = _count_active_rooms(hotel_id)
    occupied = (
        _scoped(db.session.query(func.count(Booking.room_id.distinct())), hotel_id)
        .filter(
            Booking.status == "Confirmed",
            Booking.check_in <= today,
            Booking.check_out > today,
        )
        .scalar()
        or 0
    )
    rate = round(occupied / active_rooms * 100, 1) if active_rooms else 0.0
    return {"occupied": occupied, "active_rooms": active_rooms, "rate": rate}

#booking theo tháng + tỷ lệ trạng thái
def get_bookings_by_month(hotel_id=None):
    months = _last_months()
    start = datetime(months[0][0], months[0][1], 1)
    year = extract("year", Booking.created_at)
    month = extract("month", Booking.created_at)

    rows = (
        _scoped(
            db.session.query(year, month, Booking.status, func.count(Booking.id)),
            hotel_id,
        )
        .filter(Booking.created_at >= start)
        .group_by(year, month, Booking.status)
        .all()
    )
    counts = {(int(y), int(m), str(s)): c for y, m, s, c in rows}

    series = {
        s: [counts.get((y, m, s), 0) for y, m in months] for s in BOOKING_STATUSES
    }
    total = sum(sum(values) for values in series.values())
    ratio = {
        s: round(sum(series[s]) / total * 100, 1) if total else 0.0
        for s in BOOKING_STATUSES
    }
    return {
        "months": [f"{y}-{m:02d}" for y, m in months],
        "series": series,
        "ratio": ratio,
    }

#hàm gộp cho dashboard và /admin/dashboard/data
def get_dashboard_data(hotel_id=None):
    revenue = get_revenue_by_month(hotel_id)
    bookings = get_bookings_by_month(hotel_id)
    return {
        "revenue": revenue,
        "revenue_total": sum(item["revenue"] for item in revenue),
        "occupancy": get_occupancy_by_month(hotel_id),
        "occupancy_today": get_occupancy_today(hotel_id),
        "bookings": bookings,
        "bookings_total": sum(sum(v) for v in bookings["series"].values()),
    }


def get_hotel_choices():
    return (
        db.session.query(Hotel.id, Hotel.name)
        .filter(Hotel.is_active == True)
        .order_by(Hotel.name)
        .all()
    )


# ─── Quản lý người dùng ─────────────────────────────────────────────────────

VALID_ROLES = ("customer", "receptionist", "admin")
SELF_PROTECT_MSG = "Bạn không thể tự hạ vai trò hoặc khóa chính mình."


def list_users():
    return db.session.execute(
        select(User).order_by(User.created_at.desc(), User.id.desc())
    ).scalars().all()


def create_receptionist(full_name, email, phone, password) -> User:
    """Admin tạo tài khoản lễ tân (đăng ký công khai luôn là customer)."""
    email = email.strip().lower()
    if db.session.execute(select(User.id).where(User.email == email).limit(1)).first():
        raise EmailTaken("Email đã được sử dụng.")
    user = User(
        full_name=full_name.strip(),
        email=email,
        phone=(phone or "").strip() or None,
        password_hash=generate_password_hash(password),
        role="receptionist",
        is_active=True,
    )
    try:
        db.session.add(user)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise EmailTaken("Email đã được sử dụng.") from None
    except Exception:
        db.session.rollback()
        raise
    return user


def update_user(user, actor, full_name, role, is_active) -> User:
    """Sửa họ tên, vai trò, trạng thái. Admin không tự hạ vai trò hoặc khóa chính mình."""
    if role not in VALID_ROLES:
        raise ValueError("Vai trò không hợp lệ.")
    if user.id == actor.id and (role != user.role or not is_active):
        raise PermissionError(SELF_PROTECT_MSG)
    try:
        user.full_name = full_name.strip()
        user.role = role
        user.is_active = bool(is_active)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return user


def set_user_active(user, actor, active) -> User:
    """Khóa/mở tài khoản. Tài khoản bị khóa không đăng nhập được, phiên đang mở cũng mất hiệu lực."""
    if user.id == actor.id and not active:
        raise PermissionError(SELF_PROTECT_MSG)
    try:
        user.is_active = bool(active)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return user