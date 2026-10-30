from flask import Blueprint, render_template, redirect, url_for, flash, abort, session
from flask_login import login_required, current_user
from datetime import date
import random, string
from ..models import Booking, Room, RoomType
from ..extensions import db
from ..utils.dates import nights_between
from .forms import BookingStep1Form, BookingStep2Form, BookingStep3Form, CancelBookingForm

bookings_bp = Blueprint("bookings", __name__)

def _gen_code():
    return "BK" + "".join(random.choices(string.digits, k=8))

@bookings_bp.route("/")
@login_required
def index():
    """Danh sách phòng booking của user hiện tại."""
    if current_user.role in ("admin", "receptionist"):
        bookings = Booking.query.order_by(Booking.created_at.desc()).all()
    else:
        bookings = Booking.query.filter_by(user_id=current_user.id).order_by(Booking.created_at.desc()).all()
    return render_template("bookings/index.html", bookings=bookings)

@bookings_bp.route("/<int:booking_id>")
@login_required
def detail(booking_id):
    """Chi tiết booking"""
    booking = Booking.query.get_or_404(booking_id)
    #Chỉ cho xem booking của mình, trừ admin, receptionist
    if current_user.role == "customer" and booking.user_id != current_user.id:
        abort(403)
    cancel_form = CancelBookingForm()
    return render_template("bookings/detail.html", booking=booking, cancel_form=cancel_form)

@bookings_bp.route("/step1", methods=["GET", "POST"])
@login_required
def step1():
    """Bước 1: Chọn phòng và ngày."""
    form = BookingStep1Form()
    if form.validate_on_submit():
        # Kiểm tra ngày hợp lệ
        ci = form.check_in.data
        co = form.check_out.data
        if co <= ci:
            flash("Ngày trả phòng phải sau ngày nhận phòng.", "danger")
            return render_template("bookings/step1.html", form=form)
        if ci < date.today():
            flash("Ngày nhận phòng không được trong quá khứ.", "danger")
            return render_template("bookings/step1.html", form=form)

        # Kiểm tra phòng còn trống
        room = Room.query.get(int(form.room_id.data))
        if not room or not room.is_active:
            flash("Phòng không tồn tại hoặc đã ngừng hoạt động.", "danger")
            return render_template("bookings/step1.html", form=form)

        conflict = Booking.query.filter(
            Booking.room_id == room.id,
            Booking.status.in_(["Pending", "Confirmed"]),
            Booking.check_in  < co,
            Booking.check_out > ci,
        ).first()
        if conflict:
            flash("Phòng đã được đặt trong khoảng thời gian này.", "danger")
            return render_template("bookings/step1.html", form=form)

        # Lưu vào session để qua bước 2
        session["booking_step1"] = {
            "hotel_id":  form.hotel_id.data,
            "room_id":   form.room_id.data,
            "check_in":  ci.isoformat(),
            "check_out": co.isoformat(),
            "guests":    form.guests.data,
        }
        return redirect(url_for("bookings.step2"))

    return render_template("bookings/step1.html", form=form)

@bookings_bp.route("/step2", methods=["GET", "POST"])
@login_required
def step2():
    """Bước 2: Thông tin khách hàng."""
    step1_data = session.get("booking_step1")
    if not step1_data:
        flash("Vui lòng bắt đầu từ bước 1.", "warning")
        return redirect(url_for("hotels.index"))

    form = BookingStep2Form()

    # Điền sẵn thông tin user nếu GET
    if not form.is_submitted():
        form.guest_name.data  = current_user.full_name
        form.guest_phone.data = current_user.phone or ""
        form.guest_email.data = current_user.email

    if form.validate_on_submit():
        session["booking_step2"] = {
            "guest_name":  form.guest_name.data.strip(),
            "guest_phone": form.guest_phone.data.strip(),
            "guest_email": form.guest_email.data.strip().lower(),
            "note":        form.note.data.strip() if form.note.data else "",
        }
        return redirect(url_for("bookings.step3"))

    room = Room.query.get(int(step1_data["room_id"]))
    return render_template("bookings/step2.html", form=form, step1=step1_data, room=room)


@bookings_bp.route("/step3", methods=["GET", "POST"])
@login_required
def step3():
    """Bước 3: Xác nhận và đặt phòng."""
    step1_data = session.get("booking_step1")
    step2_data = session.get("booking_step2")
    if not step1_data or not step2_data:
        flash("Vui lòng bắt đầu từ bước 1.", "warning")
        return redirect(url_for("hotels.index"))

    room    = Room.query.get(int(step1_data["room_id"]))
    ci      = date.fromisoformat(step1_data["check_in"])
    co      = date.fromisoformat(step1_data["check_out"])
    nights  = nights_between(ci, co)
    total   = room.room_type.base_price * nights

    form = BookingStep3Form()

    if form.validate_on_submit():
        # Kiểm tra lại phòng trước khi commit (khóa lạc quan)
        conflict = Booking.query.filter(
            Booking.room_id == room.id,
            Booking.status.in_(["Pending", "Confirmed"]),
            Booking.check_in  < co,
            Booking.check_out > ci,
        ).first()
        if conflict:
            flash("Rất tiếc, phòng vừa được đặt bởi người khác. Vui lòng chọn phòng khác.", "danger")
            session.pop("booking_step1", None)
            session.pop("booking_step2", None)
            return redirect(url_for("hotels.index"))

        booking = Booking(
            code=_gen_code(),
            user_id=current_user.id,
            room_id=room.id,
            check_in=ci,
            check_out=co,
            guests=int(step1_data["guests"]),
            guest_name=step2_data["guest_name"],
            guest_phone=step2_data["guest_phone"],
            guest_email=step2_data["guest_email"],
            note=step2_data["note"] or None,
            total_price=total,
            status="Pending",
        )
        db.session.add(booking)
        db.session.commit()

        # Xóa session sau khi đặt xong
        session.pop("booking_step1", None)
        session.pop("booking_step2", None)

        flash(f"Đặt phòng thành công! Mã booking: {booking.code}", "success")
        return redirect(url_for("bookings.detail", booking_id=booking.id))

    return render_template("bookings/step3.html", form=form, room=room, step1=step1_data, step2=step2_data, nights=nights, total=total,)


@bookings_bp.route("/<int:booking_id>/cancel", methods=["POST"])
@login_required
def cancel(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if current_user.role == "customer" and booking.user_id != current_user.id:
        abort(403)
    if booking.status not in ("Pending", "Confirmed"):
        flash("Không thể hủy booking ở trạng thái này.", "warning")
        return redirect(url_for("bookings.detail", booking_id=booking_id))

    form = CancelBookingForm()
    if form.validate_on_submit():
        booking.status        = "Cancelled"
        booking.cancel_reason = form.cancel_reason.data or None
        db.session.commit()
        flash("Đã hủy booking thành công.", "info")

    return redirect(url_for("bookings.detail", booking_id=booking_id))