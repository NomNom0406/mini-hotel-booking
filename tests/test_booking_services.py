from datetime import date, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm.exc import StaleDataError

from app.bookings.services import (
    ALLOWED_TRANSITIONS,
    AUTO_CANCEL_REASON,
    RoomUnavailable,
    _parse_date,
    _unique_code,
    auto_update_bookings,
    change_status,
    create_booking,
    get_calendar_data,
    list_bookings,
    parse_month,
    update_booking_info,
)
from app.extensions import db
from app.models import Booking, Room, User
from app.utils.dates import MAX_NIGHTS

CUSTOMER = "customer@test.com"
CUSTOMER2 = "customer2@test.com"
STAFF = "staff@test.com"
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


def _user(email):
    return db.session.execute(select(User).filter_by(email=email)).scalar_one()


def _room(index=0):
    rooms = db.session.execute(select(Room).order_by(Room.id)).scalars().all()
    return rooms[index]


def _future(days):
    return date.today() + timedelta(days=days)


def _make_booking(user, room, check_in, check_out, status="Pending",
                  guest_name="Khách Test"):
    """Chèn booking trực tiếp (bỏ qua create_booking) để dựng trạng thái bất kỳ."""
    booking = Booking(
        code="BKT" + uuid4().hex[:8].upper(),
        user_id=user.id,
        room_id=room.id,
        check_in=check_in,
        check_out=check_out,
        guests=1,
        guest_name=guest_name,
        guest_phone="0900000099",
        guest_email="t@test.com",
        total_price=1000000,
        status=status,
    )
    db.session.add(booking)
    db.session.commit()
    return booking


def _reload(booking_id):
    db.session.expire_all()
    return db.session.get(Booking, booking_id)


# ─── create_booking ─────────────────────────────────────────────────────────

def test_create_booking_success():
    user, room = _user(CUSTOMER), _room(0)
    b = create_booking(user.id, room.id, _future(30), _future(32), 2,
                       "Khách A", "0900000010", "a@test.com", note="ghi chú")
    assert b.status == "Pending"
    assert b.code.startswith("BK") and len(b.code) <= 20
    assert b.total_price == room.room_type.base_price * 2
    assert b.note == "ghi chú"


def test_create_booking_rejects_past_checkin():
    user, room = _user(CUSTOMER), _room(0)
    with pytest.raises(ValueError, match="quá khứ"):
        create_booking(user.id, room.id, _future(-1), _future(1), 1,
                       "Khách A", "0900000010", "a@test.com")


def test_create_booking_checkout_must_be_after_checkin():
    user, room = _user(CUSTOMER), _room(0)
    with pytest.raises(ValueError, match="sau ngày nhận"):
        create_booking(user.id, room.id, _future(30), _future(30), 1,
                       "Khách A", "0900000010", "a@test.com")


def test_create_booking_over_max_nights_rejected():
    user, room = _user(CUSTOMER), _room(0)
    with pytest.raises(ValueError, match="tối đa"):
        create_booking(user.id, room.id, _future(30), _future(30 + MAX_NIGHTS + 1), 1,
                       "Khách A", "0900000010", "a@test.com")


def test_create_booking_exactly_max_nights_ok():
    user, room = _user(CUSTOMER), _room(0)
    b = create_booking(user.id, room.id, _future(30), _future(30 + MAX_NIGHTS), 1,
                       "Khách A", "0900000010", "a@test.com")
    assert b.status == "Pending"


def test_create_booking_guests_over_capacity():
    user, room = _user(CUSTOMER), _room(0)
    with pytest.raises(ValueError, match="sức chứa"):
        create_booking(user.id, room.id, _future(30), _future(32), 3,
                       "Khách A", "0900000010", "a@test.com")


def test_create_booking_room_not_found():
    user = _user(CUSTOMER)
    with pytest.raises(RoomUnavailable, match="không khả dụng"):
        create_booking(user.id, 999999, _future(30), _future(32), 1,
                       "Khách A", "0900000010", "a@test.com")


def test_create_booking_inactive_room():
    user, template_room = _user(CUSTOMER), _room(0)
    hidden = Room(hotel_id=template_room.hotel_id, room_number="X99", floor=9,
                  room_type_id=template_room.room_type_id, is_active=False)
    db.session.add(hidden)
    db.session.commit()
    hidden_id = hidden.id
    try:
        with pytest.raises(RoomUnavailable):
            create_booking(user.id, hidden_id, _future(30), _future(32), 1,
                           "Khách A", "0900000010", "a@test.com")
    finally:
        db.session.rollback()
        db.session.execute(delete(Room).where(Room.id == hidden_id))
        db.session.commit()


def test_create_booking_conflict_and_adjacent_dates():
    user, room = _user(CUSTOMER), _room(0)
    create_booking(user.id, room.id, _future(40), _future(43), 1,
                   "Khách A", "0900000010", "a@test.com")
    with pytest.raises(RoomUnavailable, match="đã được đặt"):
        create_booking(user.id, room.id, _future(41), _future(44), 1,
                       "Khách B", "0900000011", "b@test.com")
    # Ngày trả của booking này trùng ngày nhận của booking kia: hợp lệ
    adjacent = create_booking(user.id, room.id, _future(43), _future(45), 1,
                              "Khách C", "0900000012", "c@test.com")
    assert adjacent.status == "Pending"


def test_cancelled_booking_frees_the_room():
    user, room, staff = _user(CUSTOMER), _room(0), _user(STAFF)
    first = create_booking(user.id, room.id, _future(50), _future(53), 1,
                           "Khách A", "0900000010", "a@test.com")
    change_status(first, "Cancelled", staff, reason="Khách báo hủy")
    again = create_booking(user.id, room.id, _future(51), _future(52), 1,
                           "Khách B", "0900000011", "b@test.com")
    assert again.status == "Pending"


# ─── change_status ──────────────────────────────────────────────────────────

def test_allowed_transitions_terminal_states_are_empty():
    assert ALLOWED_TRANSITIONS["Cancelled"] == set()
    assert ALLOWED_TRANSITIONS["Completed"] == set()
    assert ALLOWED_TRANSITIONS["Pending"] == {"Confirmed", "Cancelled"}
    assert ALLOWED_TRANSITIONS["Confirmed"] == {"Completed", "Cancelled"}


def test_customer_can_cancel_own_future_booking():
    customer, room = _user(CUSTOMER), _room(0)
    b = _make_booking(customer, room, _future(30), _future(32))
    change_status(b, "Cancelled", customer)
    assert _reload(b.id).status == "Cancelled"


def test_customer_cannot_cancel_on_checkin_day():
    customer, room = _user(CUSTOMER), _room(0)
    b = _make_booking(customer, room, date.today(), _future(1))
    with pytest.raises(ValueError, match="trước ngày nhận"):
        change_status(b, "Cancelled", customer)
    assert _reload(b.id).status == "Pending"


def test_customer_cannot_cancel_someone_elses_booking():
    owner, other, room = _user(CUSTOMER), _user(CUSTOMER2), _room(0)
    b = _make_booking(owner, room, _future(30), _future(32))
    with pytest.raises(PermissionError):
        change_status(b, "Cancelled", other)
    assert _reload(b.id).status == "Pending"


def test_customer_cannot_confirm_own_booking():
    customer, room = _user(CUSTOMER), _room(0)
    b = _make_booking(customer, room, _future(30), _future(32))
    with pytest.raises(PermissionError):
        change_status(b, "Confirmed", customer)


def test_staff_cancel_requires_reason():
    customer, staff, room = _user(CUSTOMER), _user(STAFF), _room(0)
    b = _make_booking(customer, room, _future(30), _future(32))
    with pytest.raises(ValueError, match="lý do"):
        change_status(b, "Cancelled", staff)
    with pytest.raises(ValueError, match="lý do"):
        change_status(b, "Cancelled", staff, reason="   ")
    assert _reload(b.id).status == "Pending"


def test_staff_cancel_stores_trimmed_reason():
    customer, staff, room = _user(CUSTOMER), _user(STAFF), _room(0)
    b = _make_booking(customer, room, _future(30), _future(32))
    change_status(b, "Cancelled", staff, reason="  Hết phòng  ")
    done = _reload(b.id)
    assert done.status == "Cancelled"
    assert done.cancel_reason == "Hết phòng"


def test_invalid_transitions_are_rejected():
    customer, staff, room = _user(CUSTOMER), _user(STAFF), _room(0)
    pending = _make_booking(customer, room, _future(30), _future(32))
    with pytest.raises(ValueError, match="Không thể chuyển"):
        change_status(pending, "Completed", staff)
    cancelled = _make_booking(customer, room, _future(60), _future(62),
                              status="Cancelled")
    with pytest.raises(ValueError, match="Không thể chuyển"):
        change_status(cancelled, "Confirmed", staff)


def test_staff_can_confirm_pending_booking():
    customer, staff, room = _user(CUSTOMER), _user(STAFF), _room(0)
    b = _make_booking(customer, room, _future(30), _future(32))
    change_status(b, "Confirmed", staff)
    assert _reload(b.id).status == "Confirmed"


def test_confirm_rejected_when_another_booking_holds_the_room():
    customer, staff, room = _user(CUSTOMER), _user(STAFF), _room(0)
    first = _make_booking(customer, room, _future(30), _future(33))
    _make_booking(customer, room, _future(31), _future(34))
    with pytest.raises(ValueError, match="đã có booking khác"):
        change_status(first, "Confirmed", staff)
    assert _reload(first.id).status == "Pending"


def test_complete_before_checkout_rejected():
    customer, staff, room = _user(CUSTOMER), _user(STAFF), _room(0)
    b = _make_booking(customer, room, _future(-1), _future(2), status="Confirmed")
    with pytest.raises(ValueError, match="hoàn tất"):
        change_status(b, "Completed", staff)
    assert _reload(b.id).status == "Confirmed"


def test_complete_from_checkout_day_ok():
    customer, staff, room = _user(CUSTOMER), _user(STAFF), _room(0)
    b = _make_booking(customer, room, _future(-3), date.today(), status="Confirmed")
    change_status(b, "Completed", staff)
    assert _reload(b.id).status == "Completed"


# ─── update_booking_info ────────────────────────────────────────────────────

def test_owner_can_update_pending_booking_info():
    customer, room = _user(CUSTOMER), _room(0)
    b = _make_booking(customer, room, _future(30), _future(32))
    update_booking_info(b, customer, {"note": "Lấy phòng trễ", "guest_name": "Tên mới"})
    done = _reload(b.id)
    assert done.note == "Lấy phòng trễ"
    assert done.guest_name == "Tên mới"


def test_update_booking_info_ignores_unknown_fields():
    customer, room = _user(CUSTOMER), _room(0)
    b = _make_booking(customer, room, _future(30), _future(32))
    update_booking_info(b, customer, {"status": "Confirmed"})
    assert _reload(b.id).status == "Pending"


def test_update_booking_info_requires_owner():
    owner, other, room = _user(CUSTOMER), _user(CUSTOMER2), _room(0)
    b = _make_booking(owner, room, _future(30), _future(32))
    with pytest.raises(PermissionError):
        update_booking_info(b, other, {"note": "x"})


def test_update_booking_info_only_when_pending():
    customer, room = _user(CUSTOMER), _room(0)
    b = _make_booking(customer, room, _future(30), _future(32), status="Confirmed")
    with pytest.raises(ValueError, match="chờ xác nhận"):
        update_booking_info(b, customer, {"note": "x"})


# ─── auto_update_bookings ───────────────────────────────────────────────────

def test_auto_cancel_pending_after_checkin_date():
    customer, room = _user(CUSTOMER), _room(0)
    b = _make_booking(customer, room, _future(-1), _future(1))
    result = auto_update_bookings()
    assert b.code in result["cancelled"]
    done = _reload(b.id)
    assert done.status == "Cancelled"
    assert done.cancel_reason == AUTO_CANCEL_REASON


def test_auto_cancel_does_not_touch_pending_on_checkin_day():
    customer, room = _user(CUSTOMER), _room(0)
    b = _make_booking(customer, room, date.today(), _future(1))
    result = auto_update_bookings()
    assert b.code not in result["cancelled"]
    assert _reload(b.id).status == "Pending"


def test_auto_complete_boundary_is_three_days_after_checkout():
    customer, room = _user(CUSTOMER), _room(0)
    due = _make_booking(customer, room, _future(-10), _future(-3), status="Confirmed")
    not_yet = _make_booking(customer, room, _future(-10), _future(-2), status="Confirmed")
    result = auto_update_bookings()
    assert due.code in result["completed"]
    assert not_yet.code not in result["completed"]
    assert _reload(due.id).status == "Completed"
    assert _reload(not_yet.id).status == "Confirmed"


def test_auto_update_dry_run_does_not_write():
    customer, room = _user(CUSTOMER), _room(0)
    b = _make_booking(customer, room, _future(-1), _future(1))
    result = auto_update_bookings(dry_run=True)
    assert b.code in result["cancelled"]
    assert _reload(b.id).status == "Pending"


def test_auto_update_leaves_terminal_bookings_alone():
    customer, room = _user(CUSTOMER), _room(0)
    cancelled = _make_booking(customer, room, _future(-10), _future(-8),
                              status="Cancelled")
    completed = _make_booking(customer, room, _future(-20), _future(-15),
                              status="Completed")
    result = auto_update_bookings()
    assert cancelled.code not in result["cancelled"] + result["completed"]
    assert completed.code not in result["cancelled"] + result["completed"]
    assert _reload(cancelled.id).status == "Cancelled"
    assert _reload(completed.id).status == "Completed"


# ─── list_bookings, parse_month, get_calendar_data ──────────────────────────

def test_list_bookings_filters_and_pagination():
    customer, room = _user(CUSTOMER), _room(0)
    alpha = _make_booking(customer, room, _future(30), _future(32),
                          guest_name="Alpha Guest")
    beta = _make_booking(customer, room, _future(40), _future(42),
                         status="Cancelled", guest_name="Beta Guest")

    by_status = list_bookings(status="Cancelled")
    assert [b.code for b in by_status.items] == [beta.code]

    by_name = list_bookings(q="alpha")
    assert [b.code for b in by_name.items] == [alpha.code]

    by_hotel = list_bookings(hotel_id=room.hotel_id)
    assert by_hotel.total == 2

    first_page = list_bookings(page=1, per_page=1)
    assert len(first_page.items) == 1
    assert first_page.total == 2


def test_parse_month():
    assert parse_month("2026-11") == date(2026, 11, 1)
    assert parse_month("abc") == date.today().replace(day=1)
    assert parse_month("") == date.today().replace(day=1)
    assert parse_month(None) == date.today().replace(day=1)


def test_calendar_data_marks_nights_and_prefers_active_booking():
    customer, room = _user(CUSTOMER), _room(0)
    month = date(2027, 2, 1)
    _make_booking(customer, room, date(2027, 2, 10), date(2027, 2, 12),
                  status="Cancelled")
    _make_booking(customer, room, date(2027, 2, 10), date(2027, 2, 13))

    data = get_calendar_data(room.hotel_id, month)
    assert data["days"] == 28
    assert data["month"] == "2027-02"
    row = next(r for r in data["rooms"] if r["id"] == room.id)
    assert set(row["cells"].keys()) == {10, 11, 12}  # đêm cuối là check_out - 1
    assert row["cells"][10]["status"] == "Pending"  # booking đang giữ phòng đè lên đã hủy

    

# ─── Nhánh lỗi: mã trùng, StaleDataError, rollback khi commit lỗi ───────────

def _boom():
    raise RuntimeError("commit lỗi giả lập")


def _stale():
    raise StaleDataError("phòng vừa bị người khác cập nhật")


def test_unique_code_raises_after_ten_collisions(monkeypatch):
    customer, room = _user(CUSTOMER), _room(0)
    existing = _make_booking(customer, room, _future(30), _future(32))
    monkeypatch.setattr("app.bookings.services.gen_code", lambda: existing.code)
    with pytest.raises(RuntimeError, match="mã booking"):
        _unique_code()


def test_create_booking_stale_data_becomes_room_unavailable(monkeypatch):
    user, room = _user(CUSTOMER), _room(0)
    user_id, room_id = user.id, room.id
    monkeypatch.setattr(db.session, "commit", _stale)
    with pytest.raises(RoomUnavailable, match="vừa được đặt"):
        create_booking(user_id, room_id, _future(30), _future(32), 1,
                       "Khách A", "0900000010", "a@test.com")
    monkeypatch.undo()
    db.session.expire_all()
    assert db.session.execute(select(Booking.id).where(Booking.guest_name == "Khách A")).first() is None


def test_change_status_rolls_back_and_reraises_when_commit_fails(monkeypatch):
    customer, staff, room = _user(CUSTOMER), _user(STAFF), _room(0)
    b = _make_booking(customer, room, _future(30), _future(32))
    booking_id = b.id
    monkeypatch.setattr(db.session, "commit", _boom)
    with pytest.raises(RuntimeError, match="commit lỗi"):
        change_status(b, "Confirmed", staff)
    monkeypatch.undo()
    assert _reload(booking_id).status == "Pending"


def test_update_booking_info_rolls_back_when_commit_fails(monkeypatch):
    customer, room = _user(CUSTOMER), _room(0)
    b = _make_booking(customer, room, _future(30), _future(32))
    booking_id = b.id
    monkeypatch.setattr(db.session, "commit", _boom)
    with pytest.raises(RuntimeError, match="commit lỗi"):
        update_booking_info(b, customer, {"note": "ghi chú không được lưu"})
    monkeypatch.undo()
    assert _reload(booking_id).note is None


def test_auto_update_rolls_back_when_commit_fails(monkeypatch):
    customer, room = _user(CUSTOMER), _room(0)
    b = _make_booking(customer, room, _future(-1), _future(1))
    booking_id = b.id
    monkeypatch.setattr(db.session, "commit", _boom)
    with pytest.raises(RuntimeError, match="commit lỗi"):
        auto_update_bookings()
    monkeypatch.undo()
    assert _reload(booking_id).status == "Pending"


# ─── _parse_date và các bộ lọc còn lại của list_bookings ────────────────────

def test_parse_date_handles_invalid_and_empty_values():
    assert _parse_date("2026-11-07") == date(2026, 11, 7)
    assert _parse_date("abc") is None
    assert _parse_date("") is None
    assert _parse_date(None) is None


def test_list_bookings_ignores_invalid_date_filter():
    customer, room = _user(CUSTOMER), _room(0)
    _make_booking(customer, room, _future(30), _future(32))
    result = list_bookings(date_from="không-phải-ngày", date_to="2026-99-99")
    assert result.total == 1


def test_list_bookings_filters_by_user_and_date_range():
    owner, other, room = _user(CUSTOMER), _user(CUSTOMER2), _room(0)
    early = _make_booking(owner, room, _future(30), _future(32))
    late = _make_booking(other, room, _future(60), _future(62))

    by_user = list_bookings(user_id=other.id)
    assert [b.code for b in by_user.items] == [late.code]

    from_cut = list_bookings(date_from=_future(45).isoformat())
    assert [b.code for b in from_cut.items] == [late.code]

    to_cut = list_bookings(date_to=_future(45).isoformat())
    assert [b.code for b in to_cut.items] == [early.code]