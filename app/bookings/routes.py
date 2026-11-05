from datetime import date, timedelta

from flask import Blueprint, render_template, redirect, url_for, flash, session, abort, request, jsonify
from flask_login import login_required, current_user

from ..models import Booking, Room
from ..extensions import db
from ..utils.dates import MAX_NIGHTS, nights_between, has_conflict
from ..utils.security import sanitize
from ..decorators import booking_owner_or_staff, roles_required, permission_required
from ..admin.forms import BookingStatusForm
from ..admin.services import get_hotel_choices
from .forms import (
    BookingStep1Form, BookingStep2Form, BookingStep3Form,
    CancelBookingForm, BookingFilterForm,
)
from .services import (
    create_booking, change_status, list_bookings, RoomUnavailable,
    get_calendar_data, parse_month,
)

bookings_bp = Blueprint("bookings", __name__)


# ─── My Bookings ────────────────────────────────────────────────────────────

@bookings_bp.get("/my-bookings")
@login_required
def my_bookings():
    """Customer xem danh sách booking của mình."""
    bookings = (Booking.query
                .filter_by(user_id=current_user.id)
                .order_by(Booking.created_at.desc())
                .all())
    return render_template("bookings/my_bookings.html", bookings=bookings)


# ─── Booking success ────────────────────────────────────────────────────────

@bookings_bp.get("/book/success/<code>")
@login_required
def success(code):
    """Trang kết quả sau khi đặt phòng thành công."""
    booking = db.one_or_404(db.select(Booking).filter_by(code=code))
    # Chỉ chủ booking hoặc nhân viên xem được
    if current_user.role == "customer" and booking.user_id != current_user.id:
        abort(403)
    return render_template("bookings/success.html", booking=booking)


# ─── Booking steps ──────────────────────────────────────────────────────────

@bookings_bp.route("/book/<int:room_id>/dates", methods=["GET", "POST"])
@login_required
@roles_required("customer")
def step_dates(room_id):
    """Bước 1: Chọn ngày và số khách."""
    room = db.session.get(Room, room_id)
    if not room or not room.is_active:
        abort(404)

    form = BookingStep1Form()
    # Điền sẵn khi GET (mang theo từ trang chi tiết khách sạn / bản nháp)
    if not form.is_submitted():
        form.room_id.data = str(room_id)
        form.hotel_id.data = str(room.hotel_id)
        draft = session.get("booking_draft", {})
        ci = request.args.get("checkin") or draft.get("check_in", "")
        co = request.args.get("checkout") or draft.get("check_out", "")
        guests = request.args.get("guests", type=int)
        if guests and guests > 0:
            form.guests.data = guests
        if ci and co:
            try:
                form.check_in.data = date.fromisoformat(ci)
                form.check_out.data = date.fromisoformat(co)
            except ValueError:
                pass

    if form.validate_on_submit():
        ci = form.check_in.data
        co = form.check_out.data

        if ci < date.today():
            flash("Ngày nhận phòng không được trong quá khứ.", "danger")
            return render_template("bookings/step1_dates.html", form=form, room=room)
        if co <= ci:
            flash("Ngày trả phòng phải sau ngày nhận phòng.", "danger")
            return render_template("bookings/step1_dates.html", form=form, room=room)
        if (co - ci).days > MAX_NIGHTS:
            flash(f"Mỗi lần đặt tối đa {MAX_NIGHTS} đêm.", "danger")
            return render_template("bookings/step1_dates.html", form=form, room=room)
        if form.guests.data > room.room_type.capacity:
            flash(f"Phòng này tối đa {room.room_type.capacity} khách.", "danger")
            return render_template("bookings/step1_dates.html", form=form, room=room)
        if has_conflict(room.id, ci, co):
            flash("Phòng đã được đặt trong khoảng thời gian này.", "danger")
            return render_template("bookings/step1_dates.html", form=form, room=room)

        session["booking_draft"] = {
            "room_id":   room_id,
            "hotel_id":  room.hotel_id,
            "check_in":  ci.isoformat(),
            "check_out": co.isoformat(),
            "guests":    form.guests.data,
        }
        return redirect(url_for("bookings.step_guest", room_id=room_id))

    return render_template("bookings/step1_dates.html", form=form, room=room)


@bookings_bp.route("/book/<int:room_id>/guest", methods=["GET", "POST"])
@login_required
@roles_required("customer")
def step_guest(room_id):
    """Bước 2: Thông tin khách."""
    draft = session.get("booking_draft")
    if not draft or draft.get("room_id") != room_id:
        flash("Vui lòng bắt đầu từ bước 1.", "warning")
        return redirect(url_for("bookings.step_dates", room_id=room_id))

    form = BookingStep2Form()
    if not form.is_submitted():
        form.guest_name.data = current_user.full_name
        form.guest_phone.data = current_user.phone or ""
        form.guest_email.data = current_user.email

    if form.validate_on_submit():
        session["booking_draft"].update({
            "guest_name":  form.guest_name.data.strip(),
            "guest_phone": form.guest_phone.data.strip(),
            "guest_email": form.guest_email.data.strip().lower(),
            "note":        sanitize(form.note.data or ""),
        })
        session.modified = True
        return redirect(url_for("bookings.step_confirm", room_id=room_id))

    room = db.session.get(Room, room_id)
    return render_template("bookings/step2_guest.html", form=form, room=room, draft=draft)


@bookings_bp.route("/book/<int:room_id>/confirm", methods=["GET", "POST"])
@login_required
@roles_required("customer")
def step_confirm(room_id):
    """Bước 3: Xác nhận và tạo booking."""
    draft = session.get("booking_draft")
    if not draft or draft.get("room_id") != room_id or "guest_name" not in draft:
        flash("Vui lòng bắt đầu từ bước 1.", "warning")
        return redirect(url_for("bookings.step_dates", room_id=room_id))

    room = db.session.get(Room, room_id)
    ci = date.fromisoformat(draft["check_in"])
    co = date.fromisoformat(draft["check_out"])
    nights = nights_between(ci, co)
    total = room.room_type.base_price * nights
    form = BookingStep3Form()

    if form.validate_on_submit():
        try:
            booking = create_booking(
                user_id=current_user.id,
                room_id=room_id,
                check_in=ci,
                check_out=co,
                guests=draft["guests"],
                guest_name=draft["guest_name"],
                guest_phone=draft["guest_phone"],
                guest_email=draft["guest_email"],
                note=draft.get("note") or None,
            )
            session.pop("booking_draft", None)
            flash(f"Đặt phòng thành công! Mã booking: {booking.code}", "success")
            return redirect(url_for("bookings.success", code=booking.code))
        except RoomUnavailable:
            flash("Phòng vừa được đặt bởi người khác, vui lòng chọn phòng khác.", "danger")
            session.pop("booking_draft", None)
            return redirect(url_for("hotels.index"))
        except ValueError as e:
            flash(str(e), "danger")
            session.pop("booking_draft", None)
            return redirect(url_for("bookings.step_dates", room_id=room_id))

    return render_template("bookings/step3_confirm.html",
                           form=form, room=room, draft=draft,
                           nights=nights, total=total, ci=ci, co=co)


# ─── Cancel ─────────────────────────────────────────────────────────────────

@bookings_bp.post("/book/<int:booking_id>/cancel")
@login_required
@booking_owner_or_staff
def cancel(booking_id):
    booking = db.session.get(Booking, booking_id)
    if not booking:
        abort(404)
    form = CancelBookingForm()
    if form.validate_on_submit():
        try:
            change_status(booking, "Cancelled", current_user, form.cancel_reason.data)
            flash("Đã hủy booking thành công.", "info")
        except PermissionError:
            abort(403)
        except ValueError as e:
            flash(str(e), "warning")
    return redirect(url_for("bookings.my_bookings"))


# ─── Quản lý booking (Receptionist, Admin) ─────────────────────────────────

_FILTER_KEYS = ("hotel_id", "status", "date_from", "date_to", "q")


def _filter_form(**data):
    form = BookingFilterForm(data=data)
    form.hotel_id.choices = [("", "Tất cả khách sạn")] + [
        (str(h[0]), h[1]) for h in get_hotel_choices()
    ]
    return form


@bookings_bp.get("/manage/bookings")
@login_required
@roles_required("admin", "receptionist")
def manage_bookings():
    filters = {k: request.args.get(k, "").strip() for k in _FILTER_KEYS}
    page = request.args.get("page", 1, type=int)
    pagination = list_bookings(
        hotel_id=int(filters["hotel_id"]) if filters["hotel_id"].isdigit() else None,
        status=filters["status"], date_from=filters["date_from"],
        date_to=filters["date_to"], q=filters["q"], page=page,
    )
    return render_template("manage/bookings.html", pagination=pagination,
                           filters={k: v for k, v in filters.items() if v},
                           filter_form=_filter_form(**filters),
                           status_form=BookingStatusForm())


@bookings_bp.post("/manage/bookings/filter")
@login_required
@roles_required("admin", "receptionist")
def manage_filter():
    form = _filter_form()
    if form.validate_on_submit():
        params = {k: getattr(form, k).data for k in _FILTER_KEYS
                  if getattr(form, k).data}
        return redirect(url_for("bookings.manage_bookings", **params))
    flash("Bộ lọc không hợp lệ.", "danger")
    return redirect(url_for("bookings.manage_bookings"))


@bookings_bp.post("/manage/bookings/<int:booking_id>/status")
@login_required
@permission_required("booking.change_status")
def update_booking_status(booking_id):
    booking = db.get_or_404(Booking, booking_id)
    form = BookingStatusForm()
    if form.validate_on_submit():
        try:
            change_status(booking, form.status.data, current_user,
                          form.cancel_reason.data)
            flash(f"Đã cập nhật trạng thái booking {booking.code}.", "success")
        except PermissionError:
            abort(403)
        except ValueError as e:
            flash(str(e), "danger")
    else:
        flash("Dữ liệu đổi trạng thái không hợp lệ.", "danger")
    return redirect(url_for("bookings.manage_bookings"))



@bookings_bp.get("/manage/bookings/calendar")
@login_required
@roles_required("admin", "receptionist")
def manage_calendar():
    hotels = get_hotel_choices()
    hotel_id = request.args.get("hotel_id", type=int) or (hotels[0][0] if hotels else None)
    month = parse_month(request.args.get("month", ""))
    return render_template(
        "manage/calendar.html", hotels=hotels, hotel_id=hotel_id,
        month=month.strftime("%Y-%m"),
        prev_month=(month - timedelta(days=1)).strftime("%Y-%m"),
        next_month=(month + timedelta(days=32)).strftime("%Y-%m"),
    )


@bookings_bp.get("/manage/bookings/calendar/data")
@login_required
@roles_required("admin", "receptionist")
def manage_calendar_data():
    hotel_id = request.args.get("hotel_id", type=int)
    if not hotel_id:
        return jsonify(error={"code": 400, "message": "Thiếu hotel_id",
                              "fields": {"hotel_id": "Bắt buộc"}}), 400
    month = parse_month(request.args.get("month", ""))
    return jsonify(data=get_calendar_data(hotel_id, month))