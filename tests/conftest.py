import pytest
from app import create_app
from app.extensions import db as _db
from app.models import User, Hotel, RoomType, Room, Amenity
from werkzeug.security import generate_password_hash


@pytest.fixture(scope="session")
def app():
    app = create_app("testing")
    with app.app_context():
        _db.create_all()
        _seed_test_data()
        yield app
        _db.drop_all()


@pytest.fixture(scope="session")
def client(app):
    return app.test_client()


@pytest.fixture(scope="function")
def auth_client(client, app):
    """Client đã đăng nhập là customer."""
    with app.app_context():
        with client.session_transaction() as sess:
            pass
    client.post("/auth/login", data={
        "email": "customer@test.com",
        "password": "Password123!",
        "csrf_token": _get_csrf(client, "/auth/login"),
    }, follow_redirects=True)
    return client


@pytest.fixture(scope="function")
def admin_client(client):
    """Client đã đăng nhập là admin."""
    client.post("/auth/login", data={
        "email": "admin@test.com",
        "password": "Password123!",
        "csrf_token": _get_csrf(client, "/auth/login"),
    }, follow_redirects=True)
    return client


def _get_csrf(client, url):
    """Lấy CSRF token từ form."""
    from bs4 import BeautifulSoup
    resp = client.get(url)
    soup = BeautifulSoup(resp.data, "html.parser")
    token = soup.find("input", {"name": "csrf_token"})
    return token["value"] if token else ""


def _seed_test_data():
    """Tạo dữ liệu test tối thiểu."""
    # Users
    users = [
        User(full_name="Admin Test",    email="admin@test.com",
             phone="0900000001", role="admin",
             password_hash=generate_password_hash("Password123!")),
        User(full_name="Staff Test",    email="staff@test.com",
             phone="0900000002", role="receptionist",
             password_hash=generate_password_hash("Password123!")),
        User(full_name="Customer Test", email="customer@test.com",
             phone="0900000003", role="customer",
             password_hash=generate_password_hash("Password123!")),
        User(full_name="Customer 2",    email="customer2@test.com",
             phone="0900000004", role="customer",
             password_hash=generate_password_hash("Password123!")),
    ]
    for u in users:
        _db.session.add(u)
    _db.session.flush()

    # Amenity
    wifi = Amenity(name="WiFi miễn phí", icon="bi-wifi")
    _db.session.add(wifi)
    _db.session.flush()

    # Hotel
    hotel = Hotel(
        name="Test Hotel", province="Hà Nội",
        address="1 Test Street", star_rating=3,
        description="Test hotel", is_active=True,
    )
    hotel.amenities = [wifi]
    _db.session.add(hotel)
    _db.session.flush()

    # RoomType
    rt = RoomType(
        hotel_id=hotel.id, name="Standard",
        base_price=500000, capacity=2,
        description="Standard room",
    )
    _db.session.add(rt)
    _db.session.flush()

    # Rooms
    for i in range(1, 4):
        r = Room(
            hotel_id=hotel.id, room_number=f"10{i}",
            floor=1, room_type_id=rt.id, is_active=True,
        )
        _db.session.add(r)

    _db.session.commit()
