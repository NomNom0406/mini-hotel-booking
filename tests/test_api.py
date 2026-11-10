from datetime import date, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.extensions import db
from app.models import Booking, Room, User
from app.utils.dates import MAX_NIGHTS

CUSTOMER = "customer@test.com"
CUSTOMER2 = "customer2@test.com"
STAFF = "staff@test.com"
ADMIN = "admin@test.com"
PASSWORD = "Password123!"
KEEP_CODE = "BKPERM001"  # booking do test_permissions tạo, không xóa

_TOKENS = {}  # cache token theo email để không phải băm mật khẩu ở mọi test


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


def _make_booking(user, room, check_in, check_out, status="Pending", note=None):
    """Chèn booking trực tiếp để dựng trạng thái bất kỳ."""
    booking = Booking(
        code="BKA" + uuid4().hex[:8].upper(),
        user_id=user.id,
        room_id=room.id,
        check_in=check_in,
        check_out=check_out,
        guests=1,
        guest_name="Khách Test",
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


def _api(app, email):
    """Trả về (client, headers Bearer) của người dùng đã đăng nhập qua API."""
    client = app.test_client()
    if email not in _TOKENS:
        resp = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
        _TOKENS[email] = resp.get_json()["data"]["access_token"]
    return client, {"Authorization": f"Bearer {_TOKENS[email]}"}


def _payload(room, ci_offset=30, co_offset=32, **overrides):
    data = {
        "room_id": room.id,
        "checkin": _future(ci_offset).isoformat(),
        "checkout": _future(co_offset).isoformat(),
        "guests": 1,
        "guest_name": "Khách API",
        "guest_phone": "0912345678",
        "guest_email": "api@test.com",
        "note": "Tạo qua API",
    }
    data.update(overrides)
    return data


# ─── GET /api/ và POST /api/auth/login ──────────────────────────────────────

def test_api_index(app):
    resp = app.test_client().get("/api/")
    assert resp.status_code == 200
    assert resp.get_json()["data"]["service"] == "Mini Hotel Booking API"


def test_login_success_returns_bearer_token(app):
    resp = app.test_client().post("/api/auth/login",
                                  json={"email": CUSTOMER, "password": PASSWORD})
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["token_type"] == "Bearer"
    assert data["access_token"]
    assert data["expires_in"] > 0
    assert data["user"]["role"] == "customer"


def test_login_missing_fields_returns_400_with_field_errors(app):
    resp = app.test_client().post("/api/auth/login", json={})
    assert resp.status_code == 400
    fields = resp.get_json()["error"]["fields"]
    assert "email" in fields
    assert "password" in fields


def test_login_wrong_password_returns_401(app):
    resp = app.test_client().post("/api/auth/login",
                                  json={"email": CUSTOMER, "password": "SaiMatKhau1!"})
    assert resp.status_code == 401


def test_login_unknown_email_returns_401(app):
    resp = app.test_client().post("/api/auth/login",
                                  json={"email": "khong@ton.tai", "password": PASSWORD})
    assert resp.status_code == 401


def test_login_non_json_body_is_rejected(app):
    resp = app.test_client().post("/api/auth/login", data="không phải json",
                                  content_type="text/plain")
    assert resp.status_code in (400, 415)


# ─── GET /api/rooms/available ───────────────────────────────────────────────

def test_rooms_available_returns_rooms_and_total_price(app):
    room = _room(0)
    resp = app.test_client().get("/api/rooms/available", query_string={
        "checkin": _future(30).isoformat(), "checkout": _future(32).isoformat()})
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["nights"] == 2
    ids = [r["id"] for r in data["rooms"]]
    assert room.id in ids
    first = next(r for r in data["rooms"] if r["id"] == room.id)
    assert first["total_price"] == first["price_per_night"] * 2


def test_rooms_available_excludes_booked_room(app):
    customer, booked, free = _user(CUSTOMER), _room(0), _room(1)
    _make_booking(customer, booked, _future(30), _future(33))
    resp = app.test_client().get("/api/rooms/available", query_string={
        "checkin": _future(31).isoformat(), "checkout": _future(34).isoformat()})
    ids = [r["id"] for r in resp.get_json()["data"]["rooms"]]
    assert booked.id not in ids
    assert free.id in ids


@pytest.mark.parametrize("query", [
    {},                                                              # thiếu cả hai ngày
    {"checkin": "abc", "checkout": "xyz"},                           # sai định dạng
    {"checkin": "2027-03-05", "checkout": "2027-03-01"},             # trả trước nhận
    {"checkin": "2020-01-01", "checkout": "2020-01-03"},             # trong quá khứ
])
def test_rooms_available_rejects_invalid_dates(app, query):
    resp = app.test_client().get("/api/rooms/available", query_string=query)
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_rooms_available_rejects_invalid_guests(app):
    resp = app.test_client().get("/api/rooms/available", query_string={
        "checkin": _future(30).isoformat(), "checkout": _future(32).isoformat(),
        "guests": "abc"})
    assert resp.status_code == 400


def test_rooms_available_filters(app):
    room = _room(0)
    base = {"checkin": _future(30).isoformat(), "checkout": _future(32).isoformat()}
    client = app.test_client()

    by_hotel = client.get("/api/rooms/available",
                          query_string={**base, "hotel_id": room.hotel_id})
    assert room.id in [r["id"] for r in by_hotel.get_json()["data"]["rooms"]]

    wrong_hotel = client.get("/api/rooms/available",
                             query_string={**base, "hotel_id": 999999})
    assert wrong_hotel.get_json()["data"]["rooms"] == []

    by_type = client.get("/api/rooms/available",
                         query_string={**base, "room_type": room.room_type_id})
    assert room.id in [r["id"] for r in by_type.get_json()["data"]["rooms"]]

    too_cheap = client.get("/api/rooms/available",
                           query_string={**base, "max_price": 1000})
    assert too_cheap.get_json()["data"]["rooms"] == []

    too_many_guests = client.get("/api/rooms/available",
                                 query_string={**base, "guests": 10})
    assert too_many_guests.get_json()["data"]["rooms"] == []


# ─── GET /api/rooms/<id> ────────────────────────────────────────────────────

def test_room_detail_without_dates(app):
    room = _room(0)
    resp = app.test_client().get(f"/api/rooms/{room.id}")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["id"] == room.id
    assert data["hotel"]["id"] == room.hotel_id
    assert "available" not in data


def test_room_detail_with_dates_reports_availability(app):
    customer, room = _user(CUSTOMER), _room(0)
    client = app.test_client()
    dates = {"checkin": _future(30).isoformat(), "checkout": _future(32).isoformat()}

    free = client.get(f"/api/rooms/{room.id}", query_string=dates).get_json()["data"]
    assert free["available"] is True
    assert free["nights"] == 2
    assert free["total_price"] == free["price_per_night"] * 2

    _make_booking(customer, room, _future(30), _future(32))
    busy = client.get(f"/api/rooms/{room.id}", query_string=dates).get_json()["data"]
    assert busy["available"] is False


def test_room_detail_unknown_room_is_404(app):
    assert app.test_client().get("/api/rooms/999999").status_code == 404


# ─── GET /api/hotels, GET /api/hotels/<id> ──────────────────────────────────

def test_hotels_list_returns_active_hotels(app):
    resp = app.test_client().get("/api/hotels")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert "Test Hotel" in [h["name"] for h in data["hotels"]]
    assert data["total"] >= 1
    assert data["page"] == 1


def test_hotels_list_filters_by_province(app):
    client = app.test_client()
    found = client.get("/api/hotels", query_string={"province": "Hà Nội"})
    assert "Test Hotel" in [h["name"] for h in found.get_json()["data"]["hotels"]]
    missing = client.get("/api/hotels", query_string={"province": "Không Tồn Tại"})
    assert missing.get_json()["data"]["hotels"] == []


def test_hotels_list_rejects_reversed_dates(app):
    resp = app.test_client().get("/api/hotels", query_string={
        "checkin": "2027-03-05", "checkout": "2027-03-01"})
    assert resp.status_code == 400


def test_hotel_detail_returns_room_types(app):
    room = _room(0)
    resp = app.test_client().get(f"/api/hotels/{room.hotel_id}")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["name"] == "Test Hotel"
    assert len(data["room_types"]) >= 1
    assert len(data["room_types"][0]["rooms"]) >= 1


def test_hotel_detail_with_dates_and_guests(app):
    room = _room(0)
    resp = app.test_client().get(f"/api/hotels/{room.hotel_id}", query_string={
        "checkin": _future(30).isoformat(), "checkout": _future(32).isoformat(),
        "guests": 2})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["nights"] == 2


def test_hotel_detail_unknown_hotel_is_404(app):
    assert app.test_client().get("/api/hotels/999999").status_code == 404


# ─── GET /api/bookings ──────────────────────────────────────────────────────

def test_bookings_list_requires_token(app):
    assert app.test_client().get("/api/bookings").status_code == 401


def test_bookings_list_rejects_garbage_token(app):
    resp = app.test_client().get("/api/bookings",
                                 headers={"Authorization": "Bearer khong-phai-token"})
    assert resp.status_code in (401, 422)


def test_bookings_list_customer_sees_only_own(app):
    customer, other, room = _user(CUSTOMER), _user(CUSTOMER2), _room(0)
    mine = _make_booking(customer, room, _future(30), _future(32))
    theirs = _make_booking(other, room, _future(60), _future(62))
    client, headers = _api(app, CUSTOMER)
    resp = client.get("/api/bookings", headers=headers)
    assert resp.status_code == 200
    codes = [b["code"] for b in resp.get_json()["data"]["bookings"]]
    assert mine.code in codes
    assert theirs.code not in codes


def test_bookings_list_staff_sees_everyones(app):
    customer, other, room = _user(CUSTOMER), _user(CUSTOMER2), _room(0)
    mine = _make_booking(customer, room, _future(30), _future(32))
    theirs = _make_booking(other, room, _future(60), _future(62))
    client, headers = _api(app, STAFF)
    codes = [b["code"] for b in
             client.get("/api/bookings", headers=headers).get_json()["data"]["bookings"]]
    assert mine.code in codes
    assert theirs.code in codes


def test_bookings_list_filters_by_status_and_validates_it(app):
    customer, room = _user(CUSTOMER), _room(0)
    pending = _make_booking(customer, room, _future(30), _future(32))
    cancelled = _make_booking(customer, room, _future(60), _future(62), status="Cancelled")
    client, headers = _api(app, CUSTOMER)

    resp = client.get("/api/bookings", headers=headers, query_string={"status": "Cancelled"})
    codes = [b["code"] for b in resp.get_json()["data"]["bookings"]]
    assert codes == [cancelled.code]
    assert pending.code not in codes

    bad = client.get("/api/bookings", headers=headers, query_string={"status": "Bogus"})
    assert bad.status_code == 400
    assert "status" in bad.get_json()["error"]["fields"]


def test_bookings_list_pagination_params(app):
    client, headers = _api(app, CUSTOMER)
    resp = client.get("/api/bookings", headers=headers, query_string={"page": 2})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["page"] == 2
    assert client.get("/api/bookings", headers=headers,
                      query_string={"page": "abc"}).status_code == 400


# ─── GET /api/bookings/<id> ─────────────────────────────────────────────────

def test_booking_detail_owner_and_staff_can_view(app):
    customer, room = _user(CUSTOMER), _room(0)
    b = _make_booking(customer, room, _future(30), _future(32), note="ghi chú")
    for email in (CUSTOMER, STAFF):
        client, headers = _api(app, email)
        resp = client.get(f"/api/bookings/{b.id}", headers=headers)
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["code"] == b.code
        assert data["nights"] == 2
        assert data["note"] == "ghi chú"


def test_booking_detail_other_customer_is_403(app):
    owner, room = _user(CUSTOMER2), _room(0)
    b = _make_booking(owner, room, _future(30), _future(32))
    client, headers = _api(app, CUSTOMER)
    assert client.get(f"/api/bookings/{b.id}", headers=headers).status_code == 403


def test_booking_detail_unknown_is_404_and_needs_token(app):
    client, headers = _api(app, CUSTOMER)
    assert client.get("/api/bookings/999999", headers=headers).status_code == 404
    assert app.test_client().get("/api/bookings/1").status_code == 401


# ─── POST /api/bookings ─────────────────────────────────────────────────────

def test_create_booking_success_returns_201(app):
    room = _room(0)
    client, headers = _api(app, CUSTOMER)
    resp = client.post("/api/bookings", headers=headers, json=_payload(room))
    assert resp.status_code == 201
    data = resp.get_json()["data"]
    assert data["status"] == "Pending"
    assert data["nights"] == 2
    assert data["total_price"] == 1000000.0
    assert data["note"] == "Tạo qua API"
    assert data["code"].startswith("BK")


def test_create_booking_requires_token(app):
    resp = app.test_client().post("/api/bookings", json=_payload(_room(0)))
    assert resp.status_code == 401


def test_create_booking_forbidden_for_staff(app):
    client, headers = _api(app, STAFF)
    resp = client.post("/api/bookings", headers=headers, json=_payload(_room(0)))
    assert resp.status_code == 403


@pytest.mark.parametrize("overrides", [
    {"guest_name": ""},
    {"guest_phone": "123"},
    {"guest_email": "khong-phai-email"},
    {"guests": 0},
    {"room_id": "abc"},
    {"checkin": "abc"},
    {"checkin": "2020-01-01", "checkout": "2020-01-03"},
])
def test_create_booking_rejects_invalid_payload(app, overrides):
    customer, room = _user(CUSTOMER), _room(0)
    client, headers = _api(app, CUSTOMER)
    resp = client.post("/api/bookings", headers=headers,
                       json=_payload(room, **overrides))
    assert resp.status_code == 400
    assert "error" in resp.get_json()
    created = db.session.execute(
        select(Booking.id).where(Booking.user_id == customer.id)).first()
    assert created is None


def test_create_booking_missing_required_field_lists_it(app):
    room = _room(0)
    payload = _payload(room)
    del payload["guest_name"]
    client, headers = _api(app, CUSTOMER)
    resp = client.post("/api/bookings", headers=headers, json=payload)
    assert resp.status_code == 400
    assert "guest_name" in resp.get_json()["error"]["fields"]


def test_create_booking_over_capacity_or_max_nights_is_400(app):
    room = _room(0)
    client, headers = _api(app, CUSTOMER)
    over_capacity = client.post("/api/bookings", headers=headers,
                                json=_payload(room, guests=3))
    assert over_capacity.status_code == 400
    too_long = client.post("/api/bookings", headers=headers,
                           json=_payload(room, 30, 30 + MAX_NIGHTS + 1))
    assert too_long.status_code == 400


def test_create_booking_conflict_returns_409(app):
    other, room = _user(CUSTOMER2), _room(0)
    _make_booking(other, room, _future(30), _future(33))
    client, headers = _api(app, CUSTOMER)
    resp = client.post("/api/bookings", headers=headers,
                       json=_payload(room, 31, 34))
    assert resp.status_code == 409


# ─── PATCH /api/bookings/<id> ───────────────────────────────────────────────

def test_patch_booking_owner_updates_note_while_pending(app):
    customer, room = _user(CUSTOMER), _room(0)
    b = _make_booking(customer, room, _future(30), _future(32))
    client, headers = _api(app, CUSTOMER)
    resp = client.patch(f"/api/bookings/{b.id}", headers=headers,
                        json={"note": "Lấy phòng trễ"})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["note"] == "Lấy phòng trễ"
    assert _reload(b.id).note == "Lấy phòng trễ"


def test_patch_booking_other_customer_and_staff_are_403(app):
    owner, room = _user(CUSTOMER), _room(0)
    b = _make_booking(owner, room, _future(30), _future(32))
    for email in (CUSTOMER2, STAFF):
        client, headers = _api(app, email)
        resp = client.patch(f"/api/bookings/{b.id}", headers=headers, json={"note": "x"})
        assert resp.status_code == 403
    assert _reload(b.id).note is None


def test_patch_booking_validation_and_state_errors(app):
    customer, room = _user(CUSTOMER), _room(0)
    pending = _make_booking(customer, room, _future(30), _future(32))
    confirmed = _make_booking(customer, room, _future(60), _future(62), status="Confirmed")
    client, headers = _api(app, CUSTOMER)

    empty = client.patch(f"/api/bookings/{pending.id}", headers=headers, json={})
    assert empty.status_code == 400
    assert "body" in empty.get_json()["error"]["fields"]

    bad_phone = client.patch(f"/api/bookings/{pending.id}", headers=headers,
                             json={"guest_phone": "123"})
    assert bad_phone.status_code == 400

    not_pending = client.patch(f"/api/bookings/{confirmed.id}", headers=headers,
                               json={"note": "x"})
    assert not_pending.status_code == 409

    unknown = client.patch("/api/bookings/999999", headers=headers, json={"note": "x"})
    assert unknown.status_code == 404


# ─── PUT /api/bookings/<id>/status ──────────────────────────────────────────

def test_put_status_staff_confirms_pending(app):
    customer, room = _user(CUSTOMER), _room(0)
    b = _make_booking(customer, room, _future(30), _future(32))
    client, headers = _api(app, STAFF)
    resp = client.put(f"/api/bookings/{b.id}/status", headers=headers,
                      json={"status": "Confirmed"})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["status"] == "Confirmed"
    assert _reload(b.id).status == "Confirmed"


def test_put_status_admin_can_also_change_status(app):
    customer, room = _user(CUSTOMER), _room(0)
    b = _make_booking(customer, room, _future(30), _future(32))
    client, headers = _api(app, ADMIN)
    resp = client.put(f"/api/bookings/{b.id}/status", headers=headers,
                      json={"status": "Confirmed"})
    assert resp.status_code == 200


def test_put_status_forbidden_for_customer_and_anonymous(app):
    customer, room = _user(CUSTOMER), _room(0)
    b = _make_booking(customer, room, _future(30), _future(32))
    client, headers = _api(app, CUSTOMER)
    assert client.put(f"/api/bookings/{b.id}/status", headers=headers,
                      json={"status": "Confirmed"}).status_code == 403
    assert app.test_client().put(f"/api/bookings/{b.id}/status",
                                 json={"status": "Confirmed"}).status_code == 401
    assert _reload(b.id).status == "Pending"


def test_put_status_cancel_requires_reason(app):
    customer, room = _user(CUSTOMER), _room(0)
    b = _make_booking(customer, room, _future(30), _future(32))
    client, headers = _api(app, STAFF)
    resp = client.put(f"/api/bookings/{b.id}/status", headers=headers,
                      json={"status": "Cancelled"})
    assert resp.status_code == 400
    assert "reason" in resp.get_json()["error"]["fields"]
    assert _reload(b.id).status == "Pending"


def test_put_status_cancel_with_reason(app):
    customer, room = _user(CUSTOMER), _room(0)
    b = _make_booking(customer, room, _future(30), _future(32))
    client, headers = _api(app, STAFF)
    resp = client.put(f"/api/bookings/{b.id}/status", headers=headers,
                      json={"status": "Cancelled", "reason": "Khách gọi hủy"})
    assert resp.status_code == 200
    done = _reload(b.id)
    assert done.status == "Cancelled"
    assert done.cancel_reason == "Khách gọi hủy"


def test_put_status_invalid_input_and_transition(app):
    customer, room = _user(CUSTOMER), _room(0)
    b = _make_booking(customer, room, _future(30), _future(32))
    client, headers = _api(app, STAFF)
    url = f"/api/bookings/{b.id}/status"

    assert client.put(url, headers=headers, json={"status": "Bogus"}).status_code == 400
    assert client.put(url, headers=headers, json={}).status_code == 400
    assert client.put(url, headers=headers,
                      json={"status": "Completed"}).status_code == 409
    assert client.put("/api/bookings/999999/status", headers=headers,
                      json={"status": "Confirmed"}).status_code == 404
    assert _reload(b.id).status == "Pending"


# ─── DELETE /api/bookings/<id> ──────────────────────────────────────────────

def test_delete_booking_owner_cancels_own_future_booking(app):
    customer, room = _user(CUSTOMER), _room(0)
    b = _make_booking(customer, room, _future(30), _future(32))
    client, headers = _api(app, CUSTOMER)
    resp = client.delete(f"/api/bookings/{b.id}", headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["data"]["status"] == "Cancelled"
    assert _reload(b.id).status == "Cancelled"  # không xóa dòng, chỉ đổi trạng thái


def test_delete_booking_other_customer_is_403(app):
    owner, room = _user(CUSTOMER2), _room(0)
    b = _make_booking(owner, room, _future(30), _future(32))
    client, headers = _api(app, CUSTOMER)
    assert client.delete(f"/api/bookings/{b.id}", headers=headers).status_code == 403
    assert _reload(b.id).status == "Pending"


def test_delete_booking_customer_cannot_cancel_on_checkin_day(app):
    customer, room = _user(CUSTOMER), _room(0)
    b = _make_booking(customer, room, date.today(), _future(1))
    client, headers = _api(app, CUSTOMER)
    assert client.delete(f"/api/bookings/{b.id}", headers=headers).status_code == 409
    assert _reload(b.id).status == "Pending"


def test_delete_booking_staff_needs_reason(app):
    customer, room = _user(CUSTOMER), _room(0)
    b = _make_booking(customer, room, _future(30), _future(32))
    client, headers = _api(app, STAFF)
    resp = client.delete(f"/api/bookings/{b.id}", headers=headers)
    assert resp.status_code == 400
    assert "reason" in resp.get_json()["error"]["fields"]
    assert _reload(b.id).status == "Pending"


def test_delete_booking_staff_reason_in_body_or_query(app):
    customer, room = _user(CUSTOMER), _room(0)
    by_body = _make_booking(customer, room, _future(30), _future(32))
    by_query = _make_booking(customer, room, _future(60), _future(62))
    client, headers = _api(app, STAFF)

    resp = client.delete(f"/api/bookings/{by_body.id}", headers=headers,
                         json={"reason": "Hết phòng"})
    assert resp.status_code == 200
    assert _reload(by_body.id).cancel_reason == "Hết phòng"

    resp = client.delete(f"/api/bookings/{by_query.id}", headers=headers,
                         query_string={"reason": "Bảo trì"})
    assert resp.status_code == 200
    assert _reload(by_query.id).cancel_reason == "Bảo trì"


def test_delete_booking_unknown_is_404_and_needs_token(app):
    client, headers = _api(app, CUSTOMER)
    assert client.delete("/api/bookings/999999", headers=headers).status_code == 404
    assert app.test_client().delete("/api/bookings/1").status_code == 401