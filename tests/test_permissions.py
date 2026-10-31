def test_customer_cannot_access_admin(client, app):
    """Customer không được vào /admin/."""
    # Login là customer
    from tests.conftest import _get_csrf
    client.post("/auth/login", data={
        "email": "customer@test.com",
        "password": "Password123!",
        "csrf_token": _get_csrf(client, "/auth/login"),
    }, follow_redirects=True)

    resp = client.get("/admin/")
    assert resp.status_code == 403


def test_anonymous_cannot_access_bookings(client):
    """Chưa login không vào được /bookings/."""
    # Logout trước
    client.get("/auth/logout")
    resp = client.get("/bookings/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]


def test_customer_cannot_see_others_booking(client, app):
    """Customer không xem được booking của người khác."""
    from app.models import Booking, Room, User
    from datetime import date

    with app.app_context():
        # Tạo booking của customer2
        room      = Room.query.first()
        customer2 = User.query.filter_by(email="customer2@test.com").first()
        from app.extensions import db
        b = Booking(
            code="BKPERM001", user_id=customer2.id, room_id=room.id,
            check_in=date(2027, 3, 1), check_out=date(2027, 3, 3),
            guests=1, guest_name="Customer 2", guest_phone="0900000004",
            guest_email="customer2@test.com", total_price=1000000,
            status="Pending",
        )
        db.session.add(b)
        db.session.commit()
        booking_id = b.id

    # Login là customer1
    from tests.conftest import _get_csrf
    client.post("/auth/login", data={
        "email": "customer@test.com",
        "password": "Password123!",
        "csrf_token": _get_csrf(client, "/auth/login"),
    }, follow_redirects=True)

    # Thử xem booking của customer2
    resp = client.get(f"/bookings/{booking_id}")
    assert resp.status_code == 403


def test_staff_can_access_admin(client):
    """Receptionist vào được /admin/."""
    from tests.conftest import _get_csrf
    client.post("/auth/login", data={
        "email": "staff@test.com",
        "password": "Password123!",
        "csrf_token": _get_csrf(client, "/auth/login"),
    }, follow_redirects=True)

    resp = client.get("/admin/")
    assert resp.status_code == 200
