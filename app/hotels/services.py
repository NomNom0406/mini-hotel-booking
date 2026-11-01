from datetime import date as date_type
from ..models import Hotel, Room, Booking, RoomType
from ..extensions import db
from ..utils.dates import has_conflict

def search_hotels(province=None, checkin=None, checkout=None, guests=1):
    """
    Tìm khách sạn đang hoạt động.
    - Nếu có checkin+checkout: chỉ trả khách sạn có ít nhất 1 phòng còn trống
      đủ sức chứa guests và không trùng lịch.
    - Nếu không có ngày: trả tất cả khách sạn đang hoạt động theo tỉnh.
    """
    query = Hotel.query.filter_by(is_active=True)
    if province:
        query = query.filter(Hotel.province == province)

    hotels = query.order_by(Hotel.star_rating.desc(), Hotel.name).all()

    # Nếu có ngày → lọc thêm khách sạn còn phòng
    if checkin and checkout:
        try:
            ci = date_type.fromisoformat(checkin)
            co = date_type.fromisoformat(checkout)
        except ValueError:
            return hotels  # ngày sai format → trả tất cả, validate ở form

        result = []
        for hotel in hotels:
            rooms = (Room.query.join(RoomType).filter(Room.hotel_id == hotel.id, Room.is_active == True, RoomType.capacity >= guests,).all())
            for room in rooms:
                if not has_conflict(room.id, ci, co):
                    result.append(hotel)
                    break  # đủ 1 phòng là khách sạn xuất hiện
        return result

    return hotels

def get_provinces():
    return db.session.execute(
        db.select(Hotel.province).distinct().order_by(Hotel.province)
    ).scalars().all()