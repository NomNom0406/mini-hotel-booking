from datetime import date, timedelta
from uuid import uuid4

import pytest
from flask import g
from sqlalchemy import delete, select

from app.bookings.services import AUTO_CANCEL_REASON
from app.extensions import db
from app.models import Booking, Room, User
from app.utils.dates import MAX_NIGHTS
from tests.conftest import _get_csrf

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


# ─── Helper ─────────────────────────────────────────────────────────────────

def _user(email):
    return db.session.execute(select(User).filter_by(email=email)).scalar_one()


def _room(index=0):
    rooms = db.session.execute(select(Room).order_by(Room.id)).scalars().all()
    return rooms[index]


def _future(days):
    return date.today() + timedelta(days=days)


def _make_booking(user, room, check_in, check_out, status="Pending",
                  note=None, guest_name="Khách Test"):
    """Chèn booking trực tiếp để dựng trạng thái bất kỳ."""
    booking = Booking(
        code="BKR" + uuid4().hex[:8].upper(),
        user_id=user.id,
        room_id=room.id,
        check_in=check_in,
        check_out=check_out,
        guests=1,
        guest_name=guest_name,
        guest_phone="0900000099",
        guest_email="t@test.com",
        note=note,
        total_price=1000000,
        status=status,
    )
    db.session.add(booking)
    db.session.commit()
    return booking


def _reload(booking_id):
    db.session.expire_all()
    return db.session.get(Booking, booking_id)


def _anon(app):
    """Client chưa đăng nhập. Xóa người dùng còn sót trong g (app context dùng chung)."""
    g.pop("_login_user", None)
    return app.test_client()


def _login(app, email):
    """Đăng nhập, trả về (client, csrf_token). Token lấy trước khi đăng nhập
    vẫn dùng được cho mọi form POST trong cùng phiên."""
    g.pop("_login_user", None)
    client = app.test_client()
    token = _get_csrf(client, "/auth/login")
    client.post("/auth/login", data={
        "email": email,
        "password": "Password123!",
        "csrf_token": token,
    }, follow_redirects=True)
    return client, token


def _post(client, url, token, data=None, **kwargs):
    payload = dict(data or {})
    payload["csrf_token"] = token
    return client.post(url, data=payload, **kwargs)


def _draft(room, check_in, check_out, with_guest=True):
    draft = {
        "room_id": room.id,
        "hotel_id": room.hotel_id,
        "check_in": check_in.isoformat(),
        "check_out": check_out.isoformat(),
        "guests": 1,
    }
    if with_guest:
        draft.update({
            "guest_name": "Khách Draft",
            "guest_phone": "0912345678",
            "guest_email": "draft@test.com",
            "note": "ghi chú từ draft",
        })
    return draft


def _set_draft(client, draft):
    with client.session_transaction() as sess:
        sess["booking_draft"] = draft


def _get_draft(client):
    with client.session_transaction() as sess:
        return sess.get("booking_draft")


# ─── /my-bookings ───────────────────────────────────────────────────────────

def test_my_bookings_requires_login(app):
    resp = _anon(app).get("/my-bookings")
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]


def test_my_bookings_lists_only_own_bookings(app):
    customer, other, room = _user(CUSTOMER), _user(CUSTOMER2), _room(0)
    mine = _make_booking(customer, room, _future(30), _future(32))
    theirs = _make_booking(other, room, _future(60), _future(62))
    client, _ = _login(app, CUSTOMER)
    resp = client.get("/my-bookings")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert mine.code in body
    assert theirs.code not in body


# ─── /book/success/<code> ───────────────────────────────────────────────────

def test_success_page_visible_to_owner(app):
    customer, room = _user(CUSTOMER), _room(0)
    b = _make_booking(customer, room, _future(30), _future(32))
    client, _ = _login(app, CUSTOMER)
    resp = client.get(f"/book/success/{b.code}")
    assert resp.status_code == 200
    assert b.code in resp.get_data(as_text=True)


def test_success_page_forbidden_for_other_customer(app):
    owner, room = _user(CUSTOMER2), _room(0)
    b = _make_booking(owner, room, _future(30), _future(32))
    client, _ = _login(app, CUSTOMER)
    assert client.get(f"/book/success/{b.code}").status_code == 403


def test_success_page_visible_to_staff(app):
    customer, room = _user(CUSTOMER), _room(0)
    b = _make_booking(customer, room, _future(30), _future(32))
    client, _ = _login(app, STAFF)
    assert client.get(f"/book/success/{b.code}").status_code == 200


def test_success_page_unknown_code_is_404(app):
    client, _ = _login(app, CUSTOMER)
    assert client.get("/book/success/BKKHONGTONTAI").status_code == 404


# ─── Bước 1: chọn ngày ──────────────────────────────────────────────────────

def test_step_dates_requires_login(app):
    room = _room(0)
    resp = _anon(app).get(f"/book/{room.id}/dates")
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]


def test_step_dates_forbidden_for_staff(app):
    room = _room(0)
    client, _ = _login(app, STAFF)
    assert client.get(f"/book/{room.id}/dates").status_code == 403


def test_step_dates_unknown_room_is_404(app):
    client, _ = _login(app, CUSTOMER)
    assert client.get("/book/999999/dates").status_code == 404


def test_step_dates_get_prefills_from_query_string(app):
    room = _room(0)
    client, _ = _login(app, CUSTOMER)
    url = (f"/book/{room.id}/dates?checkin={_future(40).isoformat()}"
           f"&checkout={_future(42).isoformat()}&guests=2")
    resp = client.get(url)
    assert resp.status_code == 200
    assert _future(40).isoformat() in resp.get_data(as_text=True)


def test_step_dates_get_ignores_invalid_query_dates(app):
    room = _room(0)
    client, _ = _login(app, CUSTOMER)
    resp = client.get(f"/book/{room.id}/dates?checkin=abc&checkout=xyz&guests=-5")
    assert resp.status_code == 200


def test_step_dates_post_valid_saves_draft_and_redirects(app):
    room = _room(0)
    client, token = _login(app, CUSTOMER)
    ci, co = _future(100), _future(102)
    resp = _post(client, f"/book/{room.id}/dates", token, {
        "room_id": str(room.id),
        "hotel_id": str(room.hotel_id),
        "guests": "2",
        "check_in": ci.isoformat(),
        "check_out": co.isoformat(),
    })
    assert resp.status_code == 302
    assert f"/book/{room.id}/guest" in resp.headers["Location"]
    draft = _get_draft(client)
    assert draft["check_in"] == ci.isoformat()
    assert draft["check_out"] == co.isoformat()
    assert draft["guests"] == 2
    assert draft["room_id"] == room.id


@pytest.mark.parametrize("ci_offset, co_offset, guests", [
    (-2, 1, 1),                    # nhận phòng trong quá khứ
    (30, 30, 1),                   # trả phòng cùng ngày nhận
    (30, 30 + MAX_NIGHTS + 1, 1),  # vượt số đêm tối đa
    (30, 32, 3),                   # vượt sức chứa (loại phòng test có capacity 2)
])
def test_step_dates_post_rejects_invalid_input(app, ci_offset, co_offset, guests):
    room = _room(0)
    client, token = _login(app, CUSTOMER)
    resp = _post(client, f"/book/{room.id}/dates", token, {
        "room_id": str(room.id),
        "hotel_id": str(room.hotel_id),
        "guests": str(guests),
        "check_in": _future(ci_offset).isoformat(),
        "check_out": _future(co_offset).isoformat(),
    })
    assert resp.status_code == 200
    assert _get_draft(client) is None


def test_step_dates_post_rejects_conflicting_dates(app):
    room = _room(0)
    other = _user(CUSTOMER2)
    _make_booking(other, room, _future(100), _future(103))
    client, token = _login(app, CUSTOMER)
    resp = _post(client, f"/book/{room.id}/dates", token, {
        "room_id": str(room.id),
        "hotel_id": str(room.hotel_id),
        "guests": "1",
        "check_in": _future(101).isoformat(),
        "check_out": _future(104).isoformat(),
    })
    assert resp.status_code == 200
    assert _get_draft(client) is None


# ─── Bước 2: thông tin khách ────────────────────────────────────────────────

def test_step_guest_without_draft_redirects_to_step_one(app):
    room = _room(0)
    client, _ = _login(app, CUSTOMER)
    resp = client.get(f"/book/{room.id}/guest")
    assert resp.status_code == 302
    assert f"/book/{room.id}/dates" in resp.headers["Location"]


def test_step_guest_draft_of_other_room_redirects(app):
    room, other_room = _room(0), _room(1)
    client, _ = _login(app, CUSTOMER)
    _set_draft(client, _draft(other_room, _future(30), _future(32), with_guest=False))
    resp = client.get(f"/book/{room.id}/guest")
    assert resp.status_code == 302
    assert f"/book/{room.id}/dates" in resp.headers["Location"]


def test_step_guest_get_with_draft_renders(app):
    room = _room(0)
    client, _ = _login(app, CUSTOMER)
    _set_draft(client, _draft(room, _future(30), _future(32), with_guest=False))
    assert client.get(f"/book/{room.id}/guest").status_code == 200


def test_step_guest_post_valid_updates_draft(app):
    room = _room(0)
    client, token = _login(app, CUSTOMER)
    _set_draft(client, _draft(room, _future(30), _future(32), with_guest=False))
    resp = _post(client, f"/book/{room.id}/guest", token, {
        "guest_name": "Nguyễn Văn A",
        "guest_phone": "0912345678",
        "guest_email": "A@Test.com",
        "note": "Lấy phòng trễ",
    })
    assert resp.status_code == 302
    assert f"/book/{room.id}/confirm" in resp.headers["Location"]
    draft = _get_draft(client)
    assert draft["guest_name"] == "Nguyễn Văn A"
    assert draft["guest_phone"] == "0912345678"
    assert draft["guest_email"] == "a@test.com"
    assert "Lấy phòng trễ" in draft["note"]


def test_step_guest_post_invalid_phone_stays_on_page(app):
    room = _room(0)
    client, token = _login(app, CUSTOMER)
    _set_draft(client, _draft(room, _future(30), _future(32), with_guest=False))
    resp = _post(client, f"/book/{room.id}/guest", token, {
        "guest_name": "Nguyễn Văn A",
        "guest_phone": "123",
        "guest_email": "a@test.com",
        "note": "",
    })
    assert resp.status_code == 200
    assert "guest_name" not in _get_draft(client)


# ─── Bước 3: xác nhận ───────────────────────────────────────────────────────

def test_step_confirm_without_draft_redirects(app):
    room = _room(0)
    client, _ = _login(app, CUSTOMER)
    resp = client.get(f"/book/{room.id}/confirm")
    assert resp.status_code == 302
    assert f"/book/{room.id}/dates" in resp.headers["Location"]


def test_step_confirm_draft_without_guest_info_redirects(app):
    room = _room(0)
    client, _ = _login(app, CUSTOMER)
    _set_draft(client, _draft(room, _future(30), _future(32), with_guest=False))
    resp = client.get(f"/book/{room.id}/confirm")
    assert resp.status_code == 302
    assert f"/book/{room.id}/dates" in resp.headers["Location"]


def test_step_confirm_get_renders_summary(app):
    room = _room(0)
    client, _ = _login(app, CUSTOMER)
    _set_draft(client, _draft(room, _future(30), _future(32)))
    resp = client.get(f"/book/{room.id}/confirm")
    assert resp.status_code == 200
    assert "Khách Draft" in resp.get_data(as_text=True)


def test_step_confirm_post_creates_booking_and_clears_draft(app):
    room = _room(0)
    client, token = _login(app, CUSTOMER)
    _set_draft(client, _draft(room, _future(30), _future(32)))
    resp = _post(client, f"/book/{room.id}/confirm", token)
    assert resp.status_code == 302
    db.session.expire_all()
    booking = db.session.execute(
        select(Booking).filter_by(guest_name="Khách Draft")
    ).scalar_one()
    assert booking.status == "Pending"
    assert booking.note == "ghi chú từ draft"
    assert f"/book/success/{booking.code}" in resp.headers["Location"]
    assert _get_draft(client) is None


def test_step_confirm_post_room_taken_redirects_and_creates_nothing(app):
    room = _room(0)
    other = _user(CUSTOMER2)
    _make_booking(other, room, _future(30), _future(33))
    client, token = _login(app, CUSTOMER)
    _set_draft(client, _draft(room, _future(31), _future(34)))
    resp = _post(client, f"/book/{room.id}/confirm", token)
    assert resp.status_code == 302
    assert _get_draft(client) is None
    db.session.expire_all()
    created = db.session.execute(
        select(Booking.id).filter_by(guest_name="Khách Draft")
    ).first()
    assert created is None


def test_step_confirm_post_past_dates_goes_back_to_step_one(app):
    room = _room(0)
    client, token = _login(app, CUSTOMER)
    _set_draft(client, _draft(room, _future(-3), _future(-1)))
    resp = _post(client, f"/book/{room.id}/confirm", token)
    assert resp.status_code == 302
    assert f"/book/{room.id}/dates" in resp.headers["Location"]
    assert _get_draft(client) is None


# ─── Hủy booking ────────────────────────────────────────────────────────────

def test_owner_cancels_own_future_booking(app):
    customer, room = _user(CUSTOMER), _room(0)
    b = _make_booking(customer, room, _future(30), _future(32))
    client, token = _login(app, CUSTOMER)
    resp = _post(client, f"/book/{b.id}/cancel", token,
                 {"cancel_reason": "Đổi kế hoạch"})
    assert resp.status_code == 302
    assert "/my-bookings" in resp.headers["Location"]
    assert _reload(b.id).status == "Cancelled"


def test_other_customer_cannot_cancel(app):
    owner, room = _user(CUSTOMER2), _room(0)
    b = _make_booking(owner, room, _future(30), _future(32))
    client, token = _login(app, CUSTOMER)
    resp = _post(client, f"/book/{b.id}/cancel", token, {"cancel_reason": "x"})
    assert resp.status_code == 403
    assert _reload(b.id).status == "Pending"


def test_customer_cannot_cancel_on_checkin_day_via_route(app):
    customer, room = _user(CUSTOMER), _room(0)
    b = _make_booking(customer, room, date.today(), _future(1))
    client, token = _login(app, CUSTOMER)
    resp = _post(client, f"/book/{b.id}/cancel", token, {"cancel_reason": "x"})
    assert resp.status_code == 302
    assert _reload(b.id).status == "Pending"


def test_staff_cancel_with_reason_succeeds(app):
    customer, room = _user(CUSTOMER), _room(0)
    b = _make_booking(customer, room, _future(30), _future(32))
    client, token = _login(app, STAFF)
    resp = _post(client, f"/book/{b.id}/cancel", token, {"cancel_reason": "Hết phòng"})
    assert resp.status_code == 302
    done = _reload(b.id)
    assert done.status == "Cancelled"
    assert done.cancel_reason == "Hết phòng"


def test_staff_cancel_without_reason_is_rejected(app):
    customer, room = _user(CUSTOMER), _room(0)
    b = _make_booking(customer, room, _future(30), _future(32))
    client, token = _login(app, STAFF)
    resp = _post(client, f"/book/{b.id}/cancel", token, {"cancel_reason": ""})
    assert resp.status_code == 302
    assert _reload(b.id).status == "Pending"


# ─── /manage/bookings ───────────────────────────────────────────────────────

def test_manage_bookings_forbidden_for_customer(app):
    client, _ = _login(app, CUSTOMER)
    assert client.get("/manage/bookings").status_code == 403


def test_manage_bookings_requires_login(app):
    resp = _anon(app).get("/manage/bookings")
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]


def test_manage_bookings_shows_customer_note(app):
    customer, room = _user(CUSTOMER), _room(0)
    b = _make_booking(customer, room, _future(30), _future(32), note="Lấy phòng trễ")
    client, _ = _login(app, STAFF)
    body = client.get("/manage/bookings").get_data(as_text=True)
    assert b.code in body
    assert "Lấy phòng trễ" in body


def test_manage_bookings_filters_and_pagination_params(app):
    customer, room = _user(CUSTOMER), _room(0)
    keep = _make_booking(customer, room, _future(30), _future(32), guest_name="Alpha Guest")
    _make_booking(customer, room, _future(40), _future(42),
                  status="Cancelled", guest_name="Beta Guest")
    client, _ = _login(app, STAFF)

    by_name = client.get("/manage/bookings?q=alpha").get_data(as_text=True)
    assert keep.code in by_name
    assert "Beta Guest" not in by_name

    by_status = client.get("/manage/bookings?status=Cancelled").get_data(as_text=True)
    assert "Beta Guest" in by_status
    assert keep.code not in by_status

    assert client.get("/manage/bookings?hotel_id=abc&page=2").status_code == 200


def test_manage_bookings_triggers_auto_cancel_of_overdue_pending(app):
    customer, room = _user(CUSTOMER), _room(0)
    b = _make_booking(customer, room, _future(-1), _future(1))
    client, _ = _login(app, STAFF)
    assert client.get("/manage/bookings").status_code == 200
    done = _reload(b.id)
    assert done.status == "Cancelled"
    assert done.cancel_reason == AUTO_CANCEL_REASON


def test_manage_filter_post_redirects_with_query(app):
    client, token = _login(app, STAFF)
    resp = _post(client, "/manage/bookings/filter", token, {"q": "abc"})
    assert resp.status_code == 302
    assert "/manage/bookings" in resp.headers["Location"]
    assert "q=abc" in resp.headers["Location"]


def test_manage_filter_post_forbidden_for_customer(app):
    client, token = _login(app, CUSTOMER)
    resp = _post(client, "/manage/bookings/filter", token, {"q": "abc"})
    assert resp.status_code == 403


# ─── /manage/bookings/<id>/status ───────────────────────────────────────────

def test_update_status_staff_confirms_pending(app):
    customer, room = _user(CUSTOMER), _room(0)
    b = _make_booking(customer, room, _future(30), _future(32))
    client, token = _login(app, STAFF)
    resp = _post(client, f"/manage/bookings/{b.id}/status", token, {"status": "Confirmed"})
    assert resp.status_code == 302
    assert _reload(b.id).status == "Confirmed"


def test_update_status_cancel_requires_reason(app):
    customer, room = _user(CUSTOMER), _room(0)
    b = _make_booking(customer, room, _future(30), _future(32))
    client, token = _login(app, STAFF)
    resp = _post(client, f"/manage/bookings/{b.id}/status", token,
                 {"status": "Cancelled", "cancel_reason": ""})
    assert resp.status_code == 302
    assert _reload(b.id).status == "Pending"


def test_update_status_cancel_with_reason(app):
    customer, room = _user(CUSTOMER), _room(0)
    b = _make_booking(customer, room, _future(30), _future(32))
    client, token = _login(app, STAFF)
    resp = _post(client, f"/manage/bookings/{b.id}/status", token,
                 {"status": "Cancelled", "cancel_reason": "Khách gọi hủy"})
    assert resp.status_code == 302
    done = _reload(b.id)
    assert done.status == "Cancelled"
    assert done.cancel_reason == "Khách gọi hủy"


def test_update_status_invalid_transition_keeps_status(app):
    customer, room = _user(CUSTOMER), _room(0)
    b = _make_booking(customer, room, _future(30), _future(32))
    client, token = _login(app, STAFF)
    resp = _post(client, f"/manage/bookings/{b.id}/status", token, {"status": "Completed"})
    assert resp.status_code == 302
    assert _reload(b.id).status == "Pending"


def test_update_status_forbidden_for_customer(app):
    customer, room = _user(CUSTOMER), _room(0)
    b = _make_booking(customer, room, _future(30), _future(32))
    client, token = _login(app, CUSTOMER)
    resp = _post(client, f"/manage/bookings/{b.id}/status", token, {"status": "Confirmed"})
    assert resp.status_code == 403
    assert _reload(b.id).status == "Pending"


def test_update_status_unknown_booking_is_404(app):
    client, token = _login(app, STAFF)
    resp = _post(client, "/manage/bookings/999999/status", token, {"status": "Confirmed"})
    assert resp.status_code == 404


# ─── Lịch booking ───────────────────────────────────────────────────────────

def test_calendar_page_for_staff_and_customer(app):
    room = _room(0)
    client, _ = _login(app, STAFF)
    assert client.get("/manage/bookings/calendar").status_code == 200
    assert client.get(
        f"/manage/bookings/calendar?hotel_id={room.hotel_id}&month=2027-02"
    ).status_code == 200
    assert client.get("/manage/bookings/calendar?month=abc").status_code == 200


def test_calendar_page_forbidden_for_customer(app):
    client, _ = _login(app, CUSTOMER)
    assert client.get("/manage/bookings/calendar").status_code == 403


def test_calendar_data_requires_hotel_id(app):
    client, _ = _login(app, STAFF)
    resp = client.get("/manage/bookings/calendar/data")
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["error"]["code"] == 400
    assert "hotel_id" in body["error"]["fields"]


def test_calendar_data_returns_grid_for_hotel(app):
    customer, room = _user(CUSTOMER), _room(0)
    _make_booking(customer, room, date(2027, 2, 10), date(2027, 2, 12))
    client, _ = _login(app, STAFF)
    resp = client.get(
        f"/manage/bookings/calendar/data?hotel_id={room.hotel_id}&month=2027-02"
    )
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["month"] == "2027-02"
    assert data["days"] == 28
    row = next(r for r in data["rooms"] if r["id"] == room.id)
    assert set(row["cells"].keys()) == {"10", "11"}


def test_calendar_data_forbidden_for_customer_and_anonymous(app):
    client, _ = _login(app, CUSTOMER)
    assert client.get("/manage/bookings/calendar/data?hotel_id=1").status_code == 403
    resp = _anon(app).get("/manage/bookings/calendar/data?hotel_id=1")
    assert resp.status_code == 302