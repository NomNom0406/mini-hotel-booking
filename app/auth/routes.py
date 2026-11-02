from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_user, logout_user, login_required, current_user

from ..extensions import limiter
from ..utils.security import is_safe_url
from .forms import LoginForm, RegisterForm, ChangePasswordForm, ProfileForm
from .services import (
    authenticate, register_customer, update_profile, issue_api_token,
    change_password as change_password_service, EmailTaken, WrongPassword,
)

auth_bp = Blueprint("auth", __name__)


def _home_for(user) -> str:
    if user.role == "admin":
        return url_for("admin.dashboard")
    if user.role == "receptionist":
        return url_for("bookings.manage_bookings")
    return url_for("hotels.index")


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(_home_for(current_user))

    form = LoginForm()
    if form.validate_on_submit():
        user = authenticate(form.email.data, form.password.data)
        if user:
            login_user(user, remember=form.remember.data)
            next_page = request.args.get("next")
            if next_page and is_safe_url(next_page):
                return redirect(next_page)
            return redirect(_home_for(user))
        flash("Email hoặc mật khẩu không đúng.", "danger")
    return render_template("auth/login.html", form=form)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(_home_for(current_user))

    form = RegisterForm()
    if form.validate_on_submit():
        try:
            user = register_customer(form.full_name.data, form.email.data,
                                     form.phone.data, form.password.data)
        except EmailTaken as e:
            form.email.errors.append(str(e))
        else:
            login_user(user)
            flash("Đăng ký thành công! Chào mừng bạn.", "success")
            return redirect(url_for("hotels.index"))
    return render_template("auth/register.html", form=form)


@auth_bp.post("/logout")
@login_required
def logout():
    logout_user()
    flash("Đã đăng xuất.", "info")
    return redirect(url_for("hotels.index"))


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        try:
            change_password_service(current_user, form.old_password.data,
                                    form.new_password.data)
        except WrongPassword as e:
            form.old_password.errors.append(str(e))
        else:
            flash("Đổi mật khẩu thành công.", "success")
            return redirect(url_for("auth.change_password"))
    return render_template("auth/change_password.html", form=form)


@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    form = ProfileForm(obj=current_user)
    if form.validate_on_submit():
        update_profile(current_user, form.full_name.data, form.phone.data)
        flash("Đã cập nhật hồ sơ.", "success")
        return redirect(url_for("auth.profile"))
    return render_template("auth/profile.html", form=form)


@auth_bp.get("/api-token")
@login_required
def api_token():
    """JWT 15 phút cho AJAX (xác thực bằng session)."""
    token, expires_in = issue_api_token(current_user)
    resp = jsonify(data={"access_token": token, "token_type": "Bearer",
                         "expires_in": expires_in})
    resp.headers["Cache-Control"] = "no-store"
    return resp