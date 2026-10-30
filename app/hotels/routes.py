from flask import Blueprint, render_template, request
from ..models import Hotel, RoomType
from ..extensions import db
from .forms import HotelSearchForm
hotels_bp = Blueprint("hotels", __name__)

@hotels_bp.get("/")
def index():
    """Danh sách khách sạn, có lọc theo tỉnh và số sao."""
    form = HotelSearchForm(request.args, meta={"csrf": False})

    province = request.args.get("province", "").strip()
    star = request.args.get("star", type=int)
    q = request.args.get("q", "").strip()

    query = Hotel.query.filter_by(is_active=True)

    if province:
        query = query.filter(Hotel.province == province)
    if star:
        query = query.filter(Hotel.star_rating == star)
    if q:
        query = query.filter(Hotel.name.ilike(f"%{q}%"))

    hotels = query.order_by(Hotel.star_rating.desc(), Hotel.name).all()
    provinces = db.session.execute(db.select(Hotel.province).distinct().order_by(Hotel.province)).scalars().all()

    # Điền choices cho SelectField tỉnh
    form.province.choices = [("", "Tất cả")] + [(p, p) for p in provinces]

    return render_template("hotels/index.html", form=form, hotels=hotels, provinces=provinces)

@hotels_bp.route("/<int:hotel_id>")
def detail(hotel_id):
    """Chi tiết khách sạn + danh sách loại phòng."""
    hotel = Hotel.query.filter_by(id=hotel_id, is_active=True).first_or_404()
    room_types = RoomType.query.filter_by(hotel_id=hotel_id).all()

    return render_template("hotels/detail.html", hotel=hotel, room_types=room_types)
