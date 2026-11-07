from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..auth.services import EmailTaken
from ..bookings.services import auto_update_bookings
from ..decorators import permission_required
from ..extensions import db
from ..models import User
from .forms import ReceptionistForm, UserForm
from .services import (
    create_receptionist, get_dashboard_data, get_hotel_choices,
    list_users, set_user_active, update_user,
)

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/dashboard")
@login_required
@permission_required('dashboard.view')
def dashboard():
    hotel_id = request.args.get("hotel_id", type=int)
    auto_update_bookings()
    data = get_dashboard_data(hotel_id)
    return render_template("admin/dashboard.html", data=data,
                           hotels=get_hotel_choices(), selected_hotel_id=hotel_id)


@admin_bp.get("/dashboard/data")
@login_required
@permission_required('dashboard.view')
def dashboard_data():
    hotel_id = request.args.get("hotel_id", type=int)
    auto_update_bookings()
    return jsonify(get_dashboard_data(hotel_id))


@admin_bp.get("/users")
@login_required
@permission_required('user.manage')
def users():
    return render_template("admin/users.html", users=list_users())


@admin_bp.route("/users/new", methods=["GET", "POST"])
@login_required
@permission_required('user.manage')
def user_create():
    form = ReceptionistForm()
    if form.validate_on_submit():
        try:
            user = create_receptionist(form.full_name.data, form.email.data,
                                       form.phone.data, form.password.data)
        except EmailTaken as e:
            form.email.errors.append(str(e))
        else:
            flash(f"Đã tạo tài khoản lễ tân {user.email}.", "success")
            return redirect(url_for("admin.users"))
    return render_template("admin/user_form.html", form=form, user=None)


@admin_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@permission_required('user.manage')
def user_edit(user_id):
    user = db.get_or_404(User, user_id)
    form = UserForm(obj=user)
    if form.validate_on_submit():
        try:
            update_user(user, current_user, form.full_name.data,
                        form.role.data, form.is_active.data)
        except (PermissionError, ValueError) as e:
            flash(str(e), "danger")
        else:
            flash(f"Đã cập nhật người dùng {user.email}.", "success")
            return redirect(url_for("admin.users"))
    return render_template("admin/user_form.html", form=form, user=user)


@admin_bp.post("/users/<int:user_id>/toggle")
@login_required
@permission_required('user.manage')
def user_toggle(user_id):
    user = db.get_or_404(User, user_id)
    try:
        set_user_active(user, current_user, not user.is_active)
    except PermissionError as e:
        flash(str(e), "danger")
    else:
        flash(f"Đã {'mở khóa' if user.is_active else 'khóa'} tài khoản {user.email}.", "info")
    return redirect(url_for("admin.users"))