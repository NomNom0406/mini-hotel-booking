from flask import Blueprint, render_template, abort, redirect, flash, url_for
from flask_login import login_required, current_user
from ..models import Hotel, Room, Booking, User
from ..extensions import db
from sqlalchemy import func
from .forms import BookingStatusForm

admin_bp = Blueprint("admin", __name__)

def _staff_required():
    if not current_user.is_authenticated or current_user.role not in ("admin", "receptionist"):
        abort(403)

def _admin_required():
    if not current_user.is_authenticated or current_user.role != "admin":
        abort(403)


@admin_bp.route("/")
@login_required
def dashboard():
    _staff_required()
    total_hotels   = Hotel.query.filter_by(is_active=True).count()
    total_rooms    = Room.query.filter_by(is_active=True).count()
    total_bookings = Booking.query.count()
    total_users    = User.query.filter_by(role="customer").count()

    status_counts = dict(db.session.execute(db.select(Booking.status, func.count(Booking.id)).group_by(Booking.status)).all())

    recent_bookings = (Booking.query.order_by(Booking.created_at.desc()).limit(10).all())
    
    return render_template("admin/dashboard.html", total_hotels=total_hotels, total_rooms=total_rooms, total_bookings=total_bookings, total_users=total_users, status_counts=status_counts, recent_bookings=recent_bookings)


@admin_bp.route("/bookings")
@login_required
def bookings():
    _staff_required()
    bookings = Booking.query.order_by(Booking.created_at.desc()).all()
    status_form = BookingStatusForm()
    return render_template("admin/bookings.html", bookings=bookings, status_form=status_form)


@admin_bp.route("/bookings/<int:booking_id>/status", methods=["POST"])
@login_required
def update_booking_status(booking_id):
    _staff_required()
    booking = Booking.query.get_or_404(booking_id)
    form    = BookingStatusForm()
    if form.validate_on_submit():
        booking.status = form.status.data
        if form.status.data == "Cancelled":
            booking.cancel_reason = form.cancel_reason.data or None
        db.session.commit()
        flash(f"Đã cập nhật trạng thái booking {booking.code}.", "success")
    return redirect(url_for("admin.bookings"))


@admin_bp.get("/hotels")
@login_required
def hotels():
    _staff_required()
    hotels = Hotel.query.order_by(Hotel.province, Hotel.name).all()
    return render_template("admin/hotels.html", hotels=hotels)


@admin_bp.get("/users")
@login_required
def users():
    _admin_required()
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=users)