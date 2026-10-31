from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from ..models import User
from ..extensions import db, limiter
from .forms import LoginForm, RegisterForm, ChangePasswordForm
from urllib.parse import urlparse, urljoin


auth_bp = Blueprint("auth", __name__)


def _is_safe_url(target: str) -> bool:
    ref_url  = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ("http", "https") and ref_url.netloc == test_url.netloc

@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("hotels.index"))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.strip().lower(), is_active=True).first()
        if user and check_password_hash(user.password_hash, form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get("next")
            if next_page and not _is_safe_url(next_page):
                next_page = None
            return redirect(next_page or url_for("hotels.index"))
        flash("Email hoặc mật khẩu không đúng.", "danger")
    return render_template("auth/login.html", form=form)

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("hotels.index"))

    form = RegisterForm()
    if form.validate_on_submit():
        if User.query.filter_by(email=form.email.data.strip().lower()).first():
            flash("Email đã được sử dụng.", "danger")
        else:
            user = User(
                full_name=form.full_name.data.strip(),
                email=form.email.data.strip().lower(),
                phone=form.phone.data.strip() or None,
                password_hash=generate_password_hash(form.password.data),
                role="customer",
            )
            db.session.add(user)
            db.session.commit()
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
        if not check_password_hash(current_user.password_hash, form.old_password.data):
            flash("Mật khẩu hiện tại không đúng.", "danger")
        else:
            current_user.password_hash = generate_password_hash(form.new_password.data)
            db.session.commit()
            flash("Đổi mật khẩu thành công.", "success")
            return redirect(url_for("hotels.index"))

    return render_template("auth/change_password.html", form=form)