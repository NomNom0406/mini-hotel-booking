from flask import Blueprint, render_template, request, redirect, url_for
from ..models import Hotel, RoomType
from .forms import HotelSearchForm
from .services import search_hotels, get_provinces


hotels_bp = Blueprint("hotels", __name__)


@hotels_bp.get("/")
def index():
    """Trang chủ — ô tìm kiếm + điểm đến phổ biến."""
    form = HotelSearchForm()
    provinces = get_provinces()
    form.province.choices = [("", "Tất cả điểm đến")] + [(p, p) for p in provinces]
    return render_template("hotels/home.html", form=form, provinces=provinces)


@hotels_bp.post("/hotels/search")
def search_post():
    """Nhận POST từ form tìm kiếm, redirect sang GET kết quả (PRG)."""
    form = HotelSearchForm()
    provinces = get_provinces()
    form.province.choices = [("", "Tất cả điểm đến")] + [(p, p) for p in provinces]

    if form.validate_on_submit():
        return redirect(url_for("hotels.search_get",
                                province=form.province.data or "",
                                checkin=form.checkin.data or "",
                                checkout=form.checkout.data or "",
                                guests=form.guests.data or 1))
    # Validate lỗi → về trang chủ với form lỗi
    return render_template("hotels/home.html", form=form, provinces=provinces), 422


@hotels_bp.get("/hotels/search")
def search_get():
    """Hiển thị kết quả tìm kiếm từ query string."""
    province = request.args.get("province", "").strip()
    checkin  = request.args.get("checkin", "").strip()
    checkout = request.args.get("checkout", "").strip()
    guests   = request.args.get("guests", 1, type=int)

    hotels = search_hotels(province=province, checkin=checkin,
                        checkout=checkout, guests=guests)
    provinces = get_provinces()
    return render_template("hotels/search_results.html",
                        hotels=hotels, provinces=provinces,
                        province=province, checkin=checkin,
                        checkout=checkout, guests=guests)


@hotels_bp.get("/hotels/<int:hotel_id>")
def detail(hotel_id):
    """Chi tiết khách sạn + danh sách loại phòng."""
    hotel = Hotel.query.filter_by(id=hotel_id, is_active=True).first_or_404()
    room_types = RoomType.query.filter_by(hotel_id=hotel_id).all()
    return render_template("hotels/detail.html", hotel=hotel, room_types=room_types)
