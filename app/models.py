# Models sẽ được khai báo ở Bước 2
# Import ở đây để Flask-Migrate nhận biết khi migrate
from datetime import datetime, date
from flask_login import UserMixin
from sqlalchemy import (
    Column, Integer, String, UnicodeText, Boolean, DateTime, Date, Numeric,
    ForeignKey, Enum, Text, UniqueConstraint
)
from sqlalchemy.orm import relationship
from .extensions import  db, login_manager

# Bảng nối Many-to-Many: Hotel ↔ Amenity (cascade xóa theo hotel)
hotel_amenities = db.Table(
    "hotel_amenities",
    Column("hotel_id", Integer, ForeignKey("hotels.id", ondelete="CASCADE"), primary_key=True),
    Column("amenity_id", Integer, ForeignKey("amenities.id", ondelete="CASCADE"), primary_key=True),
)
room_type_amenities = db.Table(
    "room_type_amenities",
    Column("room_type_id", Integer, ForeignKey("room_types.id", ondelete="CASCADE"), primary_key=True),
    Column("amenity_id",   Integer, ForeignKey("amenities.id",  ondelete="CASCADE"), primary_key=True),
)

# User
class User(UserMixin, db.Model):
    __tablename__ ="users"

    id = Column(Integer, primary_key=True)
    full_name = Column(UnicodeText(100), nullable=False)
    email = Column(UnicodeText(120), nullable=False, unique=True)
    phone = Column(String(10), nullable=True)
    password_hash= Column(String(256), nullable=False)
    role = Column(
        Enum("admin", "receptionist", "customer",
            name = "user_role", native_enum=False, create_constraint=True),
        nullable=False, default="customer"
    )
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    

    bookings = relationship("Booking", back_populates="user", lazy="dynamic")

    def __repr__(self):
        return f"<User {self.email} [{self.role}]>"


@login_manager.user_loader
def load_user(user_id: str):
    return db.session.get(User, int(user_id))

# Amenity
class Amenity(db.Model):
    __tablename__ = "amenities"

    id   = Column(Integer, primary_key=True)
    name = Column(UnicodeText(80), nullable=False, unique=True)
    icon = Column(String(50), nullable=True)   # tên icon Bootstrap/Font Awesome

    def __repr__(self):
        return f"<Amenity {self.name}>"

# Hotel
class Hotel(db.Model):
    __tablename__ = "hotels"

    id             = Column(Integer, primary_key=True)
    name           = Column(UnicodeText(150), nullable=False)
    province       = Column(UnicodeText(80),  nullable=False)
    address        = Column(UnicodeText(255), nullable=False)
    star_rating    = Column(Integer, nullable=False, default=3)
    description    = Column(UnicodeText,      nullable=True)
    image_filename = Column(String(255),      nullable=True)
    map_url = Column(String(500), nullable=True)
    is_active      = Column(Boolean, nullable=False, default=True)
    created_at     = Column(DateTime, nullable=False, default=datetime.utcnow)
    room_types = relationship("RoomType", back_populates="hotel", lazy="dynamic")
    rooms      = relationship("Room",     back_populates="hotel", lazy="dynamic")
    amenities  = relationship("Amenity",  secondary=hotel_amenities, lazy="subquery")

    def __repr__(self):
        return f"<Hotel {self.name}>"

# RoomType
class RoomType(db.Model):
    __tablename__ = "room_types"

    id             = Column(Integer, primary_key=True)
    hotel_id       = Column(Integer, ForeignKey("hotels.id"), nullable=False)
    name           = Column(UnicodeText(100), nullable=False)
    description    = Column(UnicodeText,      nullable=True)
    base_price     = Column(Numeric(12, 2),   nullable=False)
    capacity       = Column(Integer, nullable=False, default=2)
    image_filename = Column(String(255),      nullable=True)
    amenities      = relationship("Amenity",  secondary=room_type_amenities, lazy="subquery")
    hotel = relationship("Hotel", back_populates="room_types")
    rooms = relationship("Room",  back_populates="room_type", lazy="dynamic")

    def __repr__(self):
        return f"<RoomType {self.name} - Hotel {self.hotel_id}>"

# Room  (khóa lạc quan bằng version)
class Room(db.Model):
    __tablename__ = "rooms"

    id           = Column(Integer, primary_key=True)
    hotel_id     = Column(Integer, ForeignKey("hotels.id"),      nullable=False)
    room_number  = Column(String(10),  nullable=False)
    floor        = Column(Integer,     nullable=False, default=1)
    room_type_id = Column(Integer, ForeignKey("room_types.id"),  nullable=False)
    is_active    = Column(Boolean, nullable=False, default=True)
    version      = Column(Integer, nullable=False, default=0)   # khóa lạc quan

    __table_args__ = (
        UniqueConstraint("hotel_id", "room_number", name="uq_hotel_room_number"),
    )

    hotel     = relationship("Hotel",    back_populates="rooms")
    room_type = relationship("RoomType", back_populates="rooms")
    bookings  = relationship("Booking",  back_populates="room", lazy="dynamic")

    def __repr__(self):
        return f"<Room {self.room_number} Floor {self.floor}>"

# Booking
class Booking(db.Model):
    __tablename__ = "bookings"

    id           = Column(Integer, primary_key=True)
    code         = Column(String(20),  nullable=False, unique=True)
    user_id      = Column(Integer, ForeignKey("users.id"),  nullable=False)
    room_id      = Column(Integer, ForeignKey("rooms.id"),  nullable=False)
    check_in     = Column(Date,    nullable=False)
    check_out    = Column(Date,    nullable=False)
    guests       = Column(Integer, nullable=False, default=1)
    guest_name   = Column(UnicodeText(100), nullable=False)
    guest_phone  = Column(String(10),       nullable=False)
    guest_email  = Column(String(120),      nullable=False)
    note         = Column(UnicodeText,      nullable=True)
    total_price  = Column(Numeric(12, 2),   nullable=False)
    status       = Column(
        Enum("Pending", "Confirmed", "Cancelled", "Completed",
            name="booking_status", native_enum=False, create_constraint=True),
        nullable=False, default="Pending"
    )
    cancel_reason = Column(UnicodeText, nullable=True)
    created_at    = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at    = Column(DateTime, nullable=False, default=datetime.utcnow,
                        onupdate=datetime.utcnow)

    user = relationship("User", back_populates="bookings")
    room = relationship("Room", back_populates="bookings")

    def __repr__(self):
        return f"<Booking {self.code} [{self.status}]>"