from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import login_required

from ..decorators import permission_required
from ..extensions import db
from ..hotels.services import delete_image, get_amenity_choices, parse_dates, upload_folder
from ..models import Amenity, Hotel, Room, RoomType
from ..utils.dates import nights_between
from ..utils.security import save_image
from .forms import AmenityForm, RoomAdminForm, RoomFilterForm, RoomTypeAdminForm
from .services import room_type_gallery
from .services import (
    AmenityNameTaken, RoomNumberTaken, RoomTypeNameTaken, RuleViolation,
    all_hotel_choices, create_amenity, create_room, create_room_type,
    delete_amenity, get_active_room, hotel_room_type_choices,
    list_amenities_admin, list_hotel_rooms, list_room_types_admin,
    list_rooms_admin, room_is_free, room_type_choices, set_room_active,
    update_amenity, update_room, update_room_type,
)

rooms_bp = Blueprint("rooms", __name__)

_FILTER_KEYS = ("room_type_id", "price_min", "price_max", "checkin", "checkout", "guests")


# ─── Công khai: danh sách và chi tiết phòng ─────────────────────────────────

def _filter_form(hotel_id, params):
    form = RoomFilterForm(data={"hotel_id": hotel_id, **params})
    form.room_type_id.choices = [("", "Tất cả loại phòng")] + hotel_room_type_choices(hotel_id)
    return form


@rooms_bp.get("/rooms")
def index():
    """Phòng của một khách sạn (cần hotel_id), kèm bộ lọc và phân trang."""
    hotel_id = request.args.get("hotel_id", type=int)
    if not hotel_id:
        flash("Vui lòng chọn khách sạn để xem phòng.", "warning")
        return redirect(url_for("hotels.index"))
    hotel = db.first_or_404(db.select(Hotel).filter_by(id=hotel_id, is_active=True))

    params = {k: request.args.get(k, "").strip() for k in _FILTER_KEYS}
    params = {k: v for k, v in params.items() if v}
    guests = max(request.args.get("guests", 1, type=int) or 1, 1)
    ci, co = parse_dates(params.get("checkin", ""), params.get("checkout", ""))
    if ci and ci < date.today():
        flash("Ngày nhận không được trong quá khứ.", "warning")
        ci = co = None
        params.pop("checkin", None)
        params.pop("checkout", None)

    pagination = list_hotel_rooms(
        hotel_id=hotel_id,
        room_type_id=request.args.get("room_type_id", type=int),
        price_min=request.args.get("price_min", type=int),
        price_max=request.args.get("price_max", type=int),
        checkin=params.get("checkin"), checkout=params.get("checkout"),
        guests=guests, page=request.args.get("page", 1, type=int),
    )
    return render_template(
        "rooms/index.html", hotel=hotel, pagination=pagination,
        form=_filter_form(hotel_id, params), filters=params,
        has_dates=bool(ci and co), nights=nights_between(ci, co) if ci and co else None,
        checkin=ci.isoformat() if ci else "", checkout=co.isoformat() if co else "",
        guests=guests,
    )


@rooms_bp.post("/rooms/filter")
def filter_post():
    """Nhận POST từ bộ lọc, redirect sang URL GET có query string (PRG)."""
    hotel_id = request.form.get("hotel_id", type=int)
    if not hotel_id:
        abort(400)
    form = _filter_form(hotel_id, {})
    if not form.validate_on_submit():
        flash("Bộ lọc không hợp lệ.", "danger")
        return redirect(url_for("rooms.index", hotel_id=hotel_id))

    checkin = (form.checkin.data or "").strip()
    checkout = (form.checkout.data or "").strip()
    if checkin or checkout:
        ci, co = parse_dates(checkin, checkout)
        if not (ci and co):
            flash("Cần chọn đủ cả hai ngày và ngày trả phải sau ngày nhận.", "danger")
            checkin = checkout = ""

    params = {
        "room_type_id": form.room_type_id.data,
        "price_min": form.price_min.data, "price_max": form.price_max.data,
        "checkin": checkin, "checkout": checkout, "guests": form.guests.data,
    }
    params = {k: v for k, v in params.items() if v not in (None, "")}
    return redirect(url_for("rooms.index", hotel_id=hotel_id, **params))


@rooms_bp.get("/rooms/<int:room_id>")
def detail(room_id):
    room = get_active_room(room_id)
    checkin = request.args.get("checkin", "").strip()
    checkout = request.args.get("checkout", "").strip()
    guests = max(request.args.get("guests", 1, type=int) or 1, 1)

    ci, co = parse_dates(checkin, checkout)
    nights = nights_between(ci, co) if ci and co else None
    return render_template(
        "rooms/detail.html", room=room, guests=guests,
        checkin=ci.isoformat() if ci else "", checkout=co.isoformat() if co else "",
        nights=nights,
        total=room.room_type.base_price * nights if nights else None,
        available=room_is_free(room.id, ci, co) if ci and co else None,
        fits=guests <= room.room_type.capacity,
        gallery=room_type_gallery(room.room_type.image_filename),
    )


# ─── Admin: dùng chung ──────────────────────────────────────────────────────

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


# ─── Admin: phòng ───────────────────────────────────────────────────────────

def _room_form(room=None):
    form = RoomAdminForm(obj=room)
    form.hotel_id.choices = all_hotel_choices()
    form.room_type_id.choices = room_type_choices()
    return form


def _room_data(form):
    return {"hotel_id": form.hotel_id.data, "room_type_id": form.room_type_id.data,
            "room_number": form.room_number.data, "floor": form.floor.data}


@rooms_bp.get("/admin/rooms")
@login_required
@permission_required("room.manage")
def admin_rooms():
    hotel_id = request.args.get("hotel_id", type=int)
    pagination = list_rooms_admin(hotel_id, request.args.get("page", 1, type=int))
    return render_template("rooms/admin_rooms.html", pagination=pagination,
                           hotels=all_hotel_choices(), hotel_id=hotel_id)


@rooms_bp.route("/admin/rooms/new", methods=["GET", "POST"])
@login_required
@permission_required("room.manage")
def admin_room_new():
    form = _room_form()
    if form.validate_on_submit():
        try:
            room = create_room(_room_data(form))
        except RoomNumberTaken as e:
            form.room_number.errors.append(str(e))
        except RuleViolation as e:
            form.room_type_id.errors.append(str(e))
        else:
            flash(f"Đã thêm phòng {room.room_number}.", "success")
            return redirect(url_for("rooms.admin_rooms", hotel_id=room.hotel_id))
    return render_template("rooms/admin_room_form.html", form=form, room=None)


@rooms_bp.route("/admin/rooms/<int:room_id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("room.manage")
def admin_room_edit(room_id):
    room = db.get_or_404(Room, room_id)
    form = _room_form(room)
    if form.validate_on_submit():
        try:
            update_room(room, _room_data(form))
        except RoomNumberTaken as e:
            form.room_number.errors.append(str(e))
        except RuleViolation as e:
            form.room_type_id.errors.append(str(e))
        else:
            flash(f"Đã cập nhật phòng {room.room_number}.", "success")
            return redirect(url_for("rooms.admin_rooms", hotel_id=room.hotel_id))
    return render_template("rooms/admin_room_form.html", form=form, room=room)


@rooms_bp.post("/admin/rooms/<int:room_id>/toggle")
@login_required
@permission_required("room.manage")
def admin_room_toggle(room_id):
    room = db.get_or_404(Room, room_id)
    set_room_active(room, not room.is_active)
    flash(f"Đã {'hiện' if room.is_active else 'ẩn'} phòng {room.room_number}.", "info")
    return redirect(request.referrer or url_for("rooms.admin_rooms"))


# ─── Admin: loại phòng ──────────────────────────────────────────────────────

def _type_form(room_type=None):
    form = RoomTypeAdminForm(obj=room_type)
    form.hotel_id.choices = all_hotel_choices()
    form.amenity_ids.choices = get_amenity_choices()
    if room_type is not None and not form.is_submitted():
        form.amenity_ids.data = [a.id for a in room_type.amenities]
    return form


def _type_data(form):
    return {"hotel_id": form.hotel_id.data, "name": form.name.data,
            "description": form.description.data, "base_price": form.base_price.data,
            "capacity": form.capacity.data}


@rooms_bp.get("/admin/roomtypes")
@login_required
@permission_required("room.manage")
def admin_types():
    hotel_id = request.args.get("hotel_id", type=int)
    room_types, room_counts = list_room_types_admin(hotel_id)
    return render_template("rooms/admin_types.html", room_types=room_types,
                           room_counts=room_counts, hotels=all_hotel_choices(),
                           hotel_id=hotel_id)


@rooms_bp.route("/admin/roomtypes/new", methods=["GET", "POST"])
@login_required
@permission_required("room.manage")
def admin_type_new():
    form = _type_form()
    if form.validate_on_submit():
        filename, ok = _save_uploaded_image(form)
        if ok:
            try:
                room_type = create_room_type(_type_data(form), form.amenity_ids.data,
                                             image_filename=filename)
            except (RoomTypeNameTaken, RuleViolation) as e:
                delete_image(filename)
                form.name.errors.append(str(e))
            else:
                flash(f"Đã thêm loại phòng {room_type.name}.", "success")
                return redirect(url_for("rooms.admin_types", hotel_id=room_type.hotel_id))
    return render_template("rooms/admin_type_form.html", form=form, room_type=None)


@rooms_bp.route("/admin/roomtypes/<int:type_id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("room.manage")
def admin_type_edit(type_id):
    room_type = db.get_or_404(RoomType, type_id)
    form = _type_form(room_type)
    if form.validate_on_submit():
        filename, ok = _save_uploaded_image(form)
        if ok:
            try:
                update_room_type(room_type, _type_data(form), form.amenity_ids.data,
                                 image_filename=filename)
            except (RoomTypeNameTaken, RuleViolation) as e:
                delete_image(filename)
                form.name.errors.append(str(e))
            else:
                flash(f"Đã cập nhật loại phòng {room_type.name}.", "success")
                return redirect(url_for("rooms.admin_types", hotel_id=room_type.hotel_id))
    return render_template("rooms/admin_type_form.html", form=form, room_type=room_type)


# ─── Admin: tiện nghi ───────────────────────────────────────────────────────

@rooms_bp.get("/admin/amenities")
@login_required
@permission_required("room.manage")
def admin_amenities():
    amenities, hotel_counts, type_counts = list_amenities_admin()
    return render_template("rooms/admin_amenities.html", amenities=amenities,
                           hotel_counts=hotel_counts, type_counts=type_counts)


@rooms_bp.route("/admin/amenities/new", methods=["GET", "POST"])
@login_required
@permission_required("room.manage")
def admin_amenity_new():
    form = AmenityForm()
    if form.validate_on_submit():
        try:
            amenity = create_amenity(form.name.data, form.icon.data)
        except AmenityNameTaken as e:
            form.name.errors.append(str(e))
        else:
            flash(f"Đã thêm tiện nghi {amenity.name}.", "success")
            return redirect(url_for("rooms.admin_amenities"))
    return render_template("rooms/admin_amenity_form.html", form=form, amenity=None)


@rooms_bp.route("/admin/amenities/<int:amenity_id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("room.manage")
def admin_amenity_edit(amenity_id):
    amenity = db.get_or_404(Amenity, amenity_id)
    form = AmenityForm(obj=amenity)
    if form.validate_on_submit():
        try:
            update_amenity(amenity, form.name.data, form.icon.data)
        except AmenityNameTaken as e:
            form.name.errors.append(str(e))
        else:
            flash(f"Đã cập nhật tiện nghi {amenity.name}.", "success")
            return redirect(url_for("rooms.admin_amenities"))
    return render_template("rooms/admin_amenity_form.html", form=form, amenity=amenity)


@rooms_bp.post("/admin/amenities/<int:amenity_id>/delete")
@login_required
@permission_required("room.manage")
def admin_amenity_delete(amenity_id):
    amenity = db.get_or_404(Amenity, amenity_id)
    name = amenity.name
    delete_amenity(amenity)
    flash(f"Đã xóa tiện nghi {name}.", "info")
    return redirect(url_for("rooms.admin_amenities"))