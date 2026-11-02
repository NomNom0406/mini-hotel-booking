from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from ..decorators import permission_required
from ..extensions import db
from ..models import Hotel
from ..utils.security import save_image
from .forms import HotelForm, HotelSearchForm
from .services import (
    SORT_LABELS, HotelNameTaken, create_hotel, delete_image, get_amenity_choices,
    get_hotel_room_groups, get_provinces, list_hotels_admin, parse_dates,
    parse_search_args, search_hotels_page, search_query, set_hotel_active,
    update_hotel, upload_folder,
)

hotels_bp = Blueprint("hotels", __name__)


def _search_form(provinces, **data):
    form = HotelSearchForm(data=data)
    form.province.choices = [("", "Tất cả điểm đến")] + [(p, p) for p in provinces]
    return form


# ─── Công khai ──────────────────────────────────────────────────────────────

@hotels_bp.get("/")
def index():
    """Trang chủ: ô tìm kiếm + điểm đến phổ biến."""
    provinces = get_provinces()
    return render_template("hotels/home.html",
                           form=_search_form(provinces), provinces=provinces)


@hotels_bp.post("/hotels/search")
def search_post():
    """Nhận POST từ form tìm kiếm, redirect sang GET kết quả (PRG)."""
    provinces = get_provinces()
    form = _search_form(provinces)

    if form.validate_on_submit():
        return redirect(url_for("hotels.search_get",
                                province=form.province.data or "",
                                checkin=form.checkin.data or "",
                                checkout=form.checkout.data or "",
                                guests=form.guests.data or 1))
    return render_template("hotels/home.html", form=form, provinces=provinces), 422


@hotels_bp.get("/hotels/search")
def search_get():
    """Kết quả tìm kiếm từ query string: lọc, sắp xếp, phân trang."""
    params, errors = parse_search_args(request.args)
    for message in errors.values():
        flash(message, "warning")

    pagination, prices = search_hotels_page(params)
    provinces = get_provinces()
    return render_template(
        "hotels/search_results.html",
        pagination=pagination, prices=prices, params=params,
        query=search_query(params),
        form=_search_form(provinces, province=params["province"],
                          checkin=params["checkin"], checkout=params["checkout"],
                          guests=params["guests"]),
        amenities=get_amenity_choices(), sorts=SORT_LABELS,
    )


@hotels_bp.get("/hotels/<int:hotel_id>")
def detail(hotel_id):
    """Chi tiết khách sạn + phòng gom theo loại."""
    hotel = db.first_or_404(db.select(Hotel).filter_by(id=hotel_id, is_active=True))
    checkin = request.args.get("checkin", "").strip()
    checkout = request.args.get("checkout", "").strip()
    guests = max(request.args.get("guests", 1, type=int) or 1, 1)

    ci, co = parse_dates(checkin, checkout)
    groups = get_hotel_room_groups(hotel_id, checkin, checkout, guests)
    return render_template(
        "hotels/detail.html", hotel=hotel, groups=groups,
        has_dates=bool(ci and co),
        checkin=ci.isoformat() if ci else "",
        checkout=co.isoformat() if co else "",
        guests=guests,
    )


# ─── Quản lý khách sạn (Admin) ──────────────────────────────────────────────

def _hotel_data(form):
    return {
        "name": form.name.data,
        "province": form.province.data,
        "address": form.address.data,
        "star_rating": form.star_rating.data,
        "description": form.description.data,
        "map_url": form.map_url.data,
    }


def _save_uploaded_image(form):
    """(tên file | None, hợp lệ). Không chọn ảnh thì (None, True); ảnh sai thì (None, False) kèm lỗi ở form."""
    file = form.image.data
    if not file or not getattr(file, "filename", ""):
        return None, True
    filename = save_image(file, upload_folder())
    if filename is None:
        form.image.errors.append("Ảnh không hợp lệ (png, jpg, webp, tối đa 2 MB).")
        return None, False
    return filename, True


@hotels_bp.get("/admin/hotels")
@login_required
@permission_required("hotel.manage")
def admin_list():
    hotels, room_counts = list_hotels_admin()
    return render_template("admin/hotels.html", hotels=hotels, room_counts=room_counts)


@hotels_bp.route("/admin/hotels/new", methods=["GET", "POST"])
@login_required
@permission_required("hotel.manage")
def admin_create():
    form = HotelForm()
    form.amenity_ids.choices = get_amenity_choices()
    if form.validate_on_submit():
        image_filename, ok = _save_uploaded_image(form)
        if ok:
            try:
                hotel = create_hotel(_hotel_data(form), form.amenity_ids.data,
                                     image_filename=image_filename)
            except HotelNameTaken as e:
                delete_image(image_filename)  # tránh để lại ảnh mồ côi
                form.name.errors.append(str(e))
            else:
                flash(f"Đã thêm khách sạn {hotel.name}.", "success")
                return redirect(url_for("hotels.admin_list"))
    return render_template("admin/hotel_form.html", form=form, hotel=None)


@hotels_bp.route("/admin/hotels/<int:hotel_id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("hotel.manage")
def admin_edit(hotel_id):
    hotel = db.get_or_404(Hotel, hotel_id)
    form = HotelForm(obj=hotel)
    form.amenity_ids.choices = get_amenity_choices()
    if not form.is_submitted():
        form.amenity_ids.data = [a.id for a in hotel.amenities]
    if form.validate_on_submit():
        image_filename, ok = _save_uploaded_image(form)
        if ok:
            try:
                update_hotel(hotel, _hotel_data(form), form.amenity_ids.data,
                             image_filename=image_filename)
            except HotelNameTaken as e:
                delete_image(image_filename)
                form.name.errors.append(str(e))
            else:
                flash(f"Đã cập nhật khách sạn {hotel.name}.", "success")
                return redirect(url_for("hotels.admin_list"))
    return render_template("admin/hotel_form.html", form=form, hotel=hotel)


@hotels_bp.post("/admin/hotels/<int:hotel_id>/toggle")
@login_required
@permission_required("hotel.manage")
def admin_toggle(hotel_id):
    hotel = db.get_or_404(Hotel, hotel_id)
    set_hotel_active(hotel, not hotel.is_active)
    flash(f"Đã {'hiện' if hotel.is_active else 'ẩn'} khách sạn {hotel.name}.", "info")
    return redirect(url_for("hotels.admin_list"))