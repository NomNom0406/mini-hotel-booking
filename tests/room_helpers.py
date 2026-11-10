import shutil
from datetime import date, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from flask import g
from sqlalchemy import delete, select

from app.extensions import db
from app.models import Amenity, Booking, Hotel, Room, RoomType, User
from tests.conftest import _get_csrf

PASSWORD = "Password123!"
KEEP_CODE = "BKPERM001"  # booking do test_permissions tạo, không xóa


# ─── Dữ liệu tạm: mọi thứ gắn với khách sạn tạm và được xóa sạch khi test xong ──

class Scratch:
    def __init__(self):
        self.hotel_ids = []
        self.amenity_ids = []
        self.dirs = []  # thư mục thật dưới static/ cần xóa

    def hotel(self, active=True, with_type=True, with_room=True, capacity=2, price=500000):
        name = "Tmp Hotel " + uuid4().hex[:8]
        hotel = Hotel(name=name, province="Hà Nội", address="9 Tmp Street",
                      star_rating=3, description="tạm", is_active=active)
        db.session.add(hotel)
        db.session.flush()
        self.hotel_ids.append(hotel.id)
        info = SimpleNamespace(hotel_id=hotel.id, hotel_name=name, type_id=None,
                               type_name=None, room_id=None, room_number=None)
        if with_type:
            room_type = RoomType(hotel_id=hotel.id, name="Tmp Type", base_price=price,
                                 capacity=capacity, description="loại tạm")
            db.session.add(room_type)
            db.session.flush()
            info.type_id, info.type_name = room_type.id, "Tmp Type"
            if with_room:
                room = Room(hotel_id=hotel.id, room_type_id=room_type.id,
                            room_number="T101", floor=1, is_active=True)
                db.session.add(room)
                db.session.flush()
                info.room_id, info.room_number = room.id, "T101"
        db.session.commit()
        return info

    def amenity(self):
        name = "Tmp Amenity " + uuid4().hex[:8]
        amenity = Amenity(name=name, icon="bi-star")
        db.session.add(amenity)
        db.session.commit()
        self.amenity_ids.append(amenity.id)
        return SimpleNamespace(id=amenity.id, name=name)

    def cleanup(self):
        db.session.rollback()
        for hotel_id in self.hotel_ids:
            room_ids = select(Room.id).where(Room.hotel_id == hotel_id)
            db.session.execute(delete(Booking).where(Booking.room_id.in_(room_ids)))
            for room_type in db.session.execute(
                    select(RoomType).where(RoomType.hotel_id == hotel_id)).scalars():
                room_type.amenities = []
            hotel = db.session.get(Hotel, hotel_id)
            if hotel is not None:
                hotel.amenities = []
            db.session.commit()
            db.session.execute(delete(Room).where(Room.hotel_id == hotel_id))
            db.session.execute(delete(RoomType).where(RoomType.hotel_id == hotel_id))
            db.session.execute(delete(Hotel).where(Hotel.id == hotel_id))
            db.session.commit()
        for amenity_id in self.amenity_ids:
            for room_type in db.session.execute(select(RoomType).where(
                    RoomType.amenities.any(Amenity.id == amenity_id))).scalars():
                room_type.amenities = [a for a in room_type.amenities if a.id != amenity_id]
            for hotel in db.session.execute(select(Hotel).where(
                    Hotel.amenities.any(Amenity.id == amenity_id))).scalars():
                hotel.amenities = [a for a in hotel.amenities if a.id != amenity_id]
            db.session.commit()
            db.session.execute(delete(Amenity).where(Amenity.id == amenity_id))
            db.session.commit()
        for directory in self.dirs:
            shutil.rmtree(directory, ignore_errors=True)


@pytest.fixture
def scratch(app):
    data = Scratch()
    yield data
    data.cleanup()


@pytest.fixture(autouse=True)
def clean_bookings(app):
    """Dọn booking của các test này trước và sau mỗi test (DB test dùng chung cả phiên)."""
    db.session.rollback()
    db.session.execute(delete(Booking).where(Booking.code != KEEP_CODE))
    db.session.commit()
    yield
    db.session.rollback()
    db.session.execute(delete(Booking).where(Booking.code != KEEP_CODE))
    db.session.commit()


# ─── Helper dữ liệu ─────────────────────────────────────────────────────────

def future(days):
    return date.today() + timedelta(days=days)


def get_user(email):
    return db.session.execute(select(User).filter_by(email=email)).scalar_one()


def add_room(info, number, active=True, floor=1):
    room = Room(hotel_id=info.hotel_id, room_type_id=info.type_id,
                room_number=number, floor=floor, is_active=active)
    db.session.add(room)
    db.session.commit()
    return room.id


def make_booking(room_id, check_in, check_out, status="Pending",
                 email="customer@test.com"):
    booking = Booking(
        code="BKS" + uuid4().hex[:8].upper(),
        user_id=get_user(email).id,
        room_id=room_id,
        check_in=check_in,
        check_out=check_out,
        guests=1,
        guest_name="Khách Test",
        guest_phone="0900000099",
        guest_email="t@test.com",
        total_price=1000000,
        status=status,
    )
    db.session.add(booking)
    db.session.commit()
    return booking


def get_room(room_id):
    db.session.expire_all()
    return db.session.get(Room, room_id)


def get_type(type_id):
    db.session.expire_all()
    return db.session.get(RoomType, type_id)


def get_amenity(amenity_id):
    db.session.expire_all()
    return db.session.get(Amenity, amenity_id)


# ─── Helper client ──────────────────────────────────────────────────────────

def anon(app):
    """Client chưa đăng nhập. Xóa người dùng còn sót trong g (app context dùng chung)."""
    g.pop("_login_user", None)
    return app.test_client()


def login(app, email):
    """Đăng nhập, trả về (client, csrf_token)."""
    g.pop("_login_user", None)
    client = app.test_client()
    token = _get_csrf(client, "/auth/login")
    client.post("/auth/login", data={
        "email": email, "password": PASSWORD, "csrf_token": token,
    }, follow_redirects=True)
    return client, token


def post(client, url, token, data=None, **kwargs):
    payload = dict(data or {})
    payload["csrf_token"] = token
    return client.post(url, data=payload, **kwargs)