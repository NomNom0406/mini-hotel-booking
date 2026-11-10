from calendar import monthrange
from datetime import date, datetime, time, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

from app.admin.services import (
    BOOKING_STATUSES,
    MONTHS_WINDOW,
    _last_months,
    get_bookings_by_month,
    get_dashboard_data,
    get_hotel_choices,
    get_occupancy_by_month,
    get_occupancy_today,
    get_revenue_by_month,
)
from app.extensions import db
from app.models import Booking, Hotel, Room, User

CUSTOMER = "customer@test.com"
KEEP_CODE = "BKPERM001"  # booking do test_permissions tạo, không xóa


@pytest.fixture(autouse=True)
def _clean_bookings(app):
    """Dọn booking của file này trước và sau mỗi test (DB test dùng chung cả phiên)."""
    db.session.rollback()
    db.session.execute(delete(Booking).where(Booking.code != KEEP_CODE))
    db.session.commit()
    yield
    db.session.rollback()
    db.session.execute(delete(Booking).where(Booking.code != KEEP_CODE))
    db.session.commit()


# ─── Helper ─────────────────────────────────────────────────────────────────

def _user(email):
    return db.session.execute(select(User).filter_by(email=email)).scalar_one()


def _room(index=0):
    rooms = db.session.execute(select(Room).order_by(Room.id)).scalars().all()
    return rooms[index]


def _active_rooms():
    return db.session.execute(
        select(func.count(Room.id)).where(Room.is_active == True)  # noqa: E712
    ).scalar_one()


def _first_of_month(today, back=0):
    year, month = today.year, today.month
    for _ in range(back):
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return date(year, month, 1)


def _rate(nights, year, month, active):
    capacity = active * monthrange(year, month)[1]
    return round(nights / capacity * 100, 1) if capacity else 0.0


def _make_booking(user, room, check_in, check_out, status, total_price=1000000,
                  created_at=None):
    """Chèn booking trực tiếp để dựng đúng trạng thái và ngày cần đo."""
    extra = {"created_at": created_at} if created_at else {}
    booking = Booking(
        code="BKD" + uuid4().hex[:8].upper(),
        user_id=user.id,
        room_id=room.id,
        check_in=check_in,
        check_out=check_out,
        guests=1,
        guest_name="Khách Test",
        guest_phone="0900000099",
        guest_email="t@test.com",
        total_price=total_price,
        status=status,
        **extra,
    )
    db.session.add(booking)
    db.session.commit()
    return booking


# ─── _last_months ───────────────────────────────────────────────────────────

def test_last_months_returns_window_ending_with_current_month(app):
    today = date.today()
    months = _last_months()
    assert len(months) == MONTHS_WINDOW
    assert months[-1] == (today.year, today.month)
    assert months == sorted(months)
    assert _last_months(1) == [(today.year, today.month)]


def test_last_months_crosses_year_boundary(monkeypatch):
    class FakeDate(date):
        @classmethod
        def today(cls):
            return date(2027, 2, 15)

    monkeypatch.setattr("app.admin.services.date", FakeDate)
    assert _last_months() == [
        (2026, 9), (2026, 10), (2026, 11), (2026, 12), (2027, 1), (2027, 2),
    ]
    assert _last_months(1) == [(2027, 2)]


# ─── Doanh thu theo tháng ───────────────────────────────────────────────────

def test_revenue_counts_only_confirmed_and_completed(app):
    customer, room = _user(CUSTOMER), _room(0)
    today = date.today()
    cur = _first_of_month(today)
    end = cur + timedelta(days=2)
    _make_booking(customer, room, cur, end, "Confirmed", total_price=1000000)
    _make_booking(customer, room, cur, end, "Completed", total_price=2000000)
    _make_booking(customer, room, cur, end, "Pending", total_price=5000000)
    _make_booking(customer, room, cur, end, "Cancelled", total_price=5000000)

    result = get_revenue_by_month()
    assert len(result) == MONTHS_WINDOW
    assert result[-1]["month"] == f"{today.year}-{today.month:02d}"
    assert result[-1]["revenue"] == 3000000.0


def test_revenue_groups_by_checkin_month_and_ignores_outside_window(app):
    customer, room = _user(CUSTOMER), _room(0)
    today = date.today()
    cur = _first_of_month(today)
    prev = _first_of_month(today, back=1)
    old = date(today.year - 2, 1, 10)
    _make_booking(customer, room, cur, cur + timedelta(days=1), "Confirmed",
                  total_price=1000000)
    _make_booking(customer, room, prev, prev + timedelta(days=1), "Completed",
                  total_price=500000)
    _make_booking(customer, room, old, old + timedelta(days=1), "Confirmed",
                  total_price=7000000)

    result = get_revenue_by_month()
    assert result[-1]["revenue"] == 1000000.0
    assert result[-2]["revenue"] == 500000.0
    assert sum(item["revenue"] for item in result) == 1500000.0


def test_revenue_hotel_filter(app):
    customer, room = _user(CUSTOMER), _room(0)
    cur = _first_of_month(date.today())
    _make_booking(customer, room, cur, cur + timedelta(days=1), "Confirmed",
                  total_price=1000000)

    own = get_revenue_by_month(room.hotel_id)
    assert own[-1]["revenue"] == 1000000.0
    other = get_revenue_by_month(999999)
    assert [item["revenue"] for item in other] == [0.0] * MONTHS_WINDOW


# ─── Công suất phòng ────────────────────────────────────────────────────────

def test_occupancy_by_month_counts_nights_inside_each_month(app):
    customer, room = _user(CUSTOMER), _room(0)
    today = date.today()
    cur = _first_of_month(today)
    prev = _first_of_month(today, back=1)
    _make_booking(customer, room, cur, cur + timedelta(days=2), "Confirmed")
    # Ở qua ranh giới tháng: 1 đêm tháng trước + 1 đêm tháng này
    _make_booking(customer, room, cur - timedelta(days=1), cur + timedelta(days=1),
                  "Completed")
    # Hai booking này không được tính
    _make_booking(customer, room, cur, cur + timedelta(days=10), "Cancelled")
    _make_booking(customer, room, cur, cur + timedelta(days=10), "Pending")

    active = _active_rooms()
    result = get_occupancy_by_month()
    assert len(result) == MONTHS_WINDOW
    assert result[-1]["month"] == f"{today.year}-{today.month:02d}"
    assert result[-1]["occupancy"] == _rate(3, cur.year, cur.month, active)
    assert result[-2]["occupancy"] == _rate(1, prev.year, prev.month, active)


def test_occupancy_by_month_unknown_hotel_is_zero(app):
    customer, room = _user(CUSTOMER), _room(0)
    cur = _first_of_month(date.today())
    _make_booking(customer, room, cur, cur + timedelta(days=2), "Confirmed")
    result = get_occupancy_by_month(999999)
    assert [item["occupancy"] for item in result] == [0.0] * MONTHS_WINDOW


def test_occupancy_today_counts_distinct_rooms_with_confirmed_stay(app):
    customer, room0, room1 = _user(CUSTOMER), _room(0), _room(1)
    today = date.today()
    day = timedelta(days=1)
    _make_booking(customer, room0, today, today + day, "Confirmed")
    _make_booking(customer, room0, today - day, today + 2 * day, "Confirmed")  # cùng phòng
    _make_booking(customer, room1, today - day, today, "Confirmed")  # trả phòng hôm nay
    _make_booking(customer, room1, today, today + day, "Pending")
    _make_booking(customer, room1, today, today + day, "Completed")
    _make_booking(customer, room1, today, today + day, "Cancelled")

    active = _active_rooms()
    result = get_occupancy_today()
    assert result == {"occupied": 1, "active_rooms": active,
                      "rate": round(1 / active * 100, 1)}

    _make_booking(customer, room1, today, today + day, "Confirmed")
    result = get_occupancy_today()
    assert result["occupied"] == 2
    assert result["rate"] == round(2 / active * 100, 1)


def test_occupancy_today_unknown_hotel(app):
    assert get_occupancy_today(999999) == {"occupied": 0, "active_rooms": 0, "rate": 0.0}


# ─── Booking theo tháng và tỷ lệ trạng thái ─────────────────────────────────

def test_bookings_by_month_counts_by_created_at_and_status(app):
    customer, room = _user(CUSTOMER), _room(0)
    today = date.today()
    cur_dt = datetime.combine(_first_of_month(today), time(12, 0))
    prev_dt = datetime.combine(_first_of_month(today, back=1), time(12, 0))
    old_dt = datetime(today.year - 2, 1, 1, 12, 0)
    cur = _first_of_month(today)
    stay = cur + timedelta(days=1)

    base = get_bookings_by_month()
    _make_booking(customer, room, cur, stay, "Pending", created_at=cur_dt)
    _make_booking(customer, room, cur, stay, "Pending", created_at=cur_dt)
    _make_booking(customer, room, cur, stay, "Cancelled", created_at=cur_dt)
    _make_booking(customer, room, cur, stay, "Confirmed", created_at=prev_dt)
    _make_booking(customer, room, cur, stay, "Completed", created_at=old_dt)  # ngoài cửa sổ

    result = get_bookings_by_month()
    assert len(result["months"]) == MONTHS_WINDOW
    assert result["months"][-1] == f"{today.year}-{today.month:02d}"
    assert set(result["series"]) == set(BOOKING_STATUSES)
    assert result["series"]["Pending"][-1] - base["series"]["Pending"][-1] == 2
    assert result["series"]["Cancelled"][-1] - base["series"]["Cancelled"][-1] == 1
    assert result["series"]["Confirmed"][-2] - base["series"]["Confirmed"][-2] == 1
    assert result["series"]["Completed"] == base["series"]["Completed"]
    assert 99.7 <= sum(result["ratio"].values()) <= 100.3
    assert get_bookings_by_month(room.hotel_id) == result


def test_bookings_by_month_unknown_hotel_has_zero_ratio(app):
    result = get_bookings_by_month(999999)
    assert all(values == [0] * MONTHS_WINDOW for values in result["series"].values())
    assert all(value == 0.0 for value in result["ratio"].values())


# ─── Hàm gộp và danh sách khách sạn ─────────────────────────────────────────

def test_dashboard_data_combines_all_parts(app):
    customer, room = _user(CUSTOMER), _room(0)
    cur = _first_of_month(date.today())
    _make_booking(customer, room, cur, cur + timedelta(days=2), "Confirmed",
                  total_price=1000000)

    data = get_dashboard_data()
    assert set(data) == {"revenue", "revenue_total", "occupancy", "occupancy_today",
                         "bookings", "bookings_total"}
    assert data["revenue_total"] == sum(item["revenue"] for item in data["revenue"])
    assert data["revenue_total"] == 1000000.0
    assert data["bookings_total"] == sum(
        sum(values) for values in data["bookings"]["series"].values())
    assert len(data["occupancy"]) == MONTHS_WINDOW
    assert set(data["occupancy_today"]) == {"occupied", "active_rooms", "rate"}


def test_hotel_choices_lists_only_active_hotels(app):
    room = _room(0)
    hidden = Hotel(name="Hidden Hotel", province="Hà Nội", address="2 Test Street",
                   star_rating=3, description="ẩn", is_active=False)
    db.session.add(hidden)
    db.session.commit()
    hidden_id = hidden.id
    try:
        choices = [tuple(row) for row in get_hotel_choices()]
        assert (room.hotel_id, "Test Hotel") in choices
        assert hidden_id not in [hotel_id for hotel_id, _ in choices]
    finally:
        db.session.rollback()
        db.session.execute(delete(Hotel).where(Hotel.id == hidden_id))
        db.session.commit()