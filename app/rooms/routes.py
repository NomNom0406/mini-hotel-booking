from flask import Blueprint, render_template, request
from datetime import date
from ..models import Room, RoomType, Hotel, Booking
from ..utils.dates import is_valid_date_range

rooms_bp = Blueprint("rooms", __name__)

def _get_booked_room_ids(check_in: date, check_out: date) -> list[int]:
    """Trả về danh sách room_id đã dược đặt trong khoảng ngày."""
    booked = Booking.query.filter(
        Booking.status.in_(["Pending", "Confirmed"]),
        Booking.check_in < check_out,
        Booking.check_out > check_in,
    ).with_entities(Booking.room_id).all()
    return [b.room_id for b in booked]
    
@rooms_bp.route("/")
def index():
    """Danh sách phòng trống theo khách sạn và ngày."""
    hotel_id = request.args.get("hotel_id", type=int)
    check_in = request.args.get("check_in")
    check_out = request.args.get("check_out")
    guests = request.args.get("guests", 1, type=int)

    rooms = []
    error = None

    if hotel_id and check_in and check_out:
        try:
            ci = date.fromisoformat(check_in)
            co = date.fromisoformat(check_out)
            if not is_valid_date_range(ci, co):
                error = "Ngày không hợp lệ. Check-out phải sau check-in và check-in không được trong quá khứ."
            else:
                booked_ids = _get_booked_room_ids(ci, co)
                rooms = (
                    Room.query.join(RoomType).filter(
                        Room.hotel_id == hotel_id,
                        Room.is_active == True,
                        Room.id.notin_(booked_ids),
                        RoomType.capacity >= guests,).order_by(RoomType.base_price).all()
                )
                if not rooms:
                    error = "Không có phòng trống cho ngày và số khách đã chọn."
        except ValueError:
            error = "Định dạng ngày không hợp lệ."
    hotel = Hotel.query.get(hotel_id) if hotel_id else None

    return render_template("rooms/index.html", rooms=rooms, hotel=hotel, check_in=check_in, check_out=check_out, guests=guests, error=error)

@rooms_bp.route("/<int:room_id>")
def detail(room_id):
    """Chi tiết phòng."""
    room = Room.query.filter_by(id=room_id, is_active=True).first_or_404()
    return  render_template("rooms/detail.html", room=room)