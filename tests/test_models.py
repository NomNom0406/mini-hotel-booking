from app.models import User, Hotel, RoomType, Room, Booking, Amenity
from app.extensions import db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date


def test_user_create(app):
    with app.app_context():
        u = User.query.filter_by(email="customer@test.com").first()
        assert u is not None
        assert u.role == "customer"
        assert u.is_active is True


def test_password_hash(app):
    with app.app_context():
        u = User.query.filter_by(email="customer@test.com").first()
        assert check_password_hash(u.password_hash, "Password123!")
        assert not check_password_hash(u.password_hash, "wrongpassword")


def test_hotel_amenity_relationship(app):
    with app.app_context():
        hotel = Hotel.query.filter_by(name="Test Hotel").first()
        assert hotel is not None
        assert len(hotel.amenities) == 1
        assert hotel.amenities[0].name == "WiFi miễn phí"


def test_room_unique_constraint(app):
    with app.app_context():
        hotel = Hotel.query.filter_by(name="Test Hotel").first()
        rt    = RoomType.query.filter_by(hotel_id=hotel.id).first()
        # Room 101 đã tồn tại từ seed
        r = Room(
            hotel_id=hotel.id, room_number="101",
            floor=1, room_type_id=rt.id,
        )
        db.session.add(r)
        try:
            db.session.commit()
            assert False, "Phải raise lỗi unique"
        except Exception:
            db.session.rollback()


def test_booking_code_unique(app):
    with app.app_context():
        room     = Room.query.first()
        customer = User.query.filter_by(role="customer").first()
        b1 = Booking(
            code="BKTEST001", user_id=customer.id, room_id=room.id,
            check_in=date(2027, 1, 1), check_out=date(2027, 1, 3),
            guests=1, guest_name="Test", guest_phone="0900000099",
            guest_email="test@test.com", total_price=1000000,
            status="Pending",
        )
        b2 = Booking(
            code="BKTEST001",  # trùng code
            user_id=customer.id, room_id=room.id,
            check_in=date(2027, 2, 1), check_out=date(2027, 2, 3),
            guests=1, guest_name="Test", guest_phone="0900000099",
            guest_email="test@test.com", total_price=1000000,
            status="Pending",
        )
        db.session.add(b1)
        db.session.add(b2)
        try:
            db.session.commit()
            assert False, "Phải raise lỗi unique code"
        except Exception:
            db.session.rollback()
