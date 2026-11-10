"""Test blueprint auth (app/auth/routes.py + services.py).

Dùng tài khoản pytest (conftest.py): admin@test.com, staff@test.com,
customer@test.com, customer2@test.com — KHÔNG dùng seed thật.
User tạo thêm trong test phải tự dọn.
"""
import pytest
from flask import g
from sqlalchemy import select

from app.extensions import db
from app.models import User
from tests.room_helpers import anon, login, post

# ─── Hằng số tài khoản test ────────────────────────────────────────────────

CUSTOMER = "customer@test.com"
ADMIN    = "admin@test.com"
STAFF    = "staff@test.com"
PWD      = "Password123!"

# ─── Helper ─────────────────────────────────────────────────────────────────

def _get_csrf(client, url):
    from tests.conftest import _get_csrf as _c
    return _c(client, url)


def _new_email():
    import uuid
    return f"tmp_{uuid.uuid4().hex[:10]}@test.com"


def _create_user(app, email, password=PWD, role="customer"):
    """Tạo user thẳng vào DB; trả user.id để dọn sau test."""
    from werkzeug.security import generate_password_hash
    with app.app_context():
        u = User(
            full_name="Tmp User",
            email=email,
            phone=None,
            password_hash=generate_password_hash(password),
            role=role,
            is_active=True,
        )
        db.session.add(u)
        db.session.commit()
        return u.id


def _delete_user(app, user_id):
    with app.app_context():
        u = db.session.get(User, user_id)
        if u:
            db.session.delete(u)
            db.session.commit()


# ─── authenticate (service) ─────────────────────────────────────────────────

def test_authenticate_dung_tra_user(app):
    from app.auth.services import authenticate
    with app.app_context():
        u = authenticate(CUSTOMER, PWD)
        assert u is not None
        assert u.email == CUSTOMER


def test_authenticate_sai_mat_khau_tra_none(app):
    from app.auth.services import authenticate
    with app.app_context():
        assert authenticate(CUSTOMER, "wrong") is None


def test_authenticate_email_khong_ton_tai_tra_none(app):
    from app.auth.services import authenticate
    with app.app_context():
        assert authenticate("nobody@test.com", PWD) is None


def test_authenticate_tai_khoan_bi_khoa_tra_none(app):
    from app.auth.services import authenticate
    with app.app_context():
        u = db.session.execute(select(User).filter_by(email=CUSTOMER)).scalar_one()
        u.is_active = False
        db.session.commit()
        result = authenticate(CUSTOMER, PWD)
        u.is_active = True
        db.session.commit()
    assert result is None


# ─── register_customer (service) ────────────────────────────────────────────

def test_register_customer_tao_duoc(app):
    from app.auth.services import register_customer
    email = _new_email()
    with app.app_context():
        u = register_customer("Test User", email, "0912345678", PWD)
        uid = u.id
        assert u.role == "customer"
        assert u.email == email
    _delete_user(app, uid)


def test_register_customer_email_trung_raise(app):
    from app.auth.services import register_customer, EmailTaken
    with app.app_context():
        with pytest.raises(EmailTaken):
            register_customer("X", CUSTOMER, "", PWD)


def test_register_customer_email_duoc_lowercase(app):
    from app.auth.services import register_customer
    email = _new_email().upper()
    with app.app_context():
        u = register_customer("Test", email, None, PWD)
        uid = u.id
        assert u.email == email.lower()
    _delete_user(app, uid)


# ─── change_password (service) ──────────────────────────────────────────────

def test_change_password_thanh_cong(app):
    from app.auth.services import change_password, authenticate
    email = _new_email()
    uid = _create_user(app, email, PWD)
    with app.app_context():
        u = db.session.get(User, uid)
        change_password(u, PWD, "NewPass99!")
        db.session.commit()
    with app.app_context():
        assert authenticate(email, "NewPass99!") is not None
        assert authenticate(email, PWD) is None
    _delete_user(app, uid)


def test_change_password_sai_mat_khau_cu_raise(app):
    from app.auth.services import change_password, WrongPassword
    with app.app_context():
        u = db.session.execute(select(User).filter_by(email=CUSTOMER)).scalar_one()
        with pytest.raises(WrongPassword):
            change_password(u, "wrong", "NewPass99!")


# ─── update_profile (service) ───────────────────────────────────────────────

def test_update_profile_cap_nhat_ten_va_sdt(app):
    from app.auth.services import update_profile
    email = _new_email()
    uid = _create_user(app, email)
    with app.app_context():
        u = db.session.get(User, uid)
        update_profile(u, "Tên Mới", "0987654321")
        db.session.commit()
    with app.app_context():
        db.session.expire_all()
        u = db.session.get(User, uid)
        assert u.full_name == "Tên Mới"
        assert u.phone == "0987654321"
    _delete_user(app, uid)


def test_update_profile_sdt_rong_luu_none(app):
    from app.auth.services import update_profile
    email = _new_email()
    uid = _create_user(app, email)
    with app.app_context():
        u = db.session.get(User, uid)
        update_profile(u, "Tên", "")
        db.session.commit()
    with app.app_context():
        db.session.expire_all()
        assert db.session.get(User, uid).phone is None
    _delete_user(app, uid)


# ─── issue_api_token (service) ──────────────────────────────────────────────

def test_issue_api_token_tra_token_va_expires(app):
    from app.auth.services import issue_api_token
    with app.app_context():
        u = db.session.execute(select(User).filter_by(email=CUSTOMER)).scalar_one()
        token, expires_in = issue_api_token(u)
    assert isinstance(token, str) and len(token) > 10
    assert expires_in == 900  # 15 phút


# ─── Route: GET /auth/login ─────────────────────────────────────────────────

def test_login_get_200(app):
    resp = anon(app).get("/auth/login")
    assert resp.status_code == 200


def test_login_da_dang_nhap_redirect_theo_vai_tro(app):
    client, _ = login(app, CUSTOMER)
    resp = client.get("/auth/login")
    assert resp.status_code == 302
    assert "/hotels" in resp.headers["Location"] or "/" in resp.headers["Location"]


def test_login_admin_redirect_ve_dashboard(app):
    client, _ = login(app, ADMIN)
    resp = client.get("/auth/login")
    assert resp.status_code == 302
    assert "admin/dashboard" in resp.headers["Location"]


def test_login_receptionist_redirect_ve_manage_bookings(app):
    client, _ = login(app, STAFF)
    resp = client.get("/auth/login")
    assert resp.status_code == 302
    assert "manage/bookings" in resp.headers["Location"]


# ─── Route: POST /auth/login ────────────────────────────────────────────────

def test_login_post_dung_redirect_theo_vai_tro(app):
    client = anon(app)
    token = _get_csrf(client, "/auth/login")
    resp = post(client, "/auth/login", token,
                data={"email": CUSTOMER, "password": PWD})
    assert resp.status_code == 302
    assert "/hotels" in resp.headers["Location"] or "/" in resp.headers["Location"]


def test_login_post_admin_redirect_dashboard(app):
    client = anon(app)
    token = _get_csrf(client, "/auth/login")
    resp = post(client, "/auth/login", token,
                data={"email": ADMIN, "password": PWD})
    assert resp.status_code == 302
    assert "admin/dashboard" in resp.headers["Location"]


def test_login_post_sai_mat_khau_hien_loi_chung(app):
    client = anon(app)
    token = _get_csrf(client, "/auth/login")
    resp = post(client, "/auth/login", token,
                data={"email": CUSTOMER, "password": "wrong"},
                follow_redirects=True)
    assert resp.status_code == 200
    assert "Email hoặc mật khẩu không đúng." in resp.get_data(as_text=True)


def test_login_post_tai_khoan_bi_khoa(app):
    client = anon(app)
    with app.app_context():
        u = db.session.execute(select(User).filter_by(email=CUSTOMER)).scalar_one()
        u.is_active = False
        db.session.commit()
    token = _get_csrf(client, "/auth/login")
    resp = post(client, "/auth/login", token,
                data={"email": CUSTOMER, "password": PWD},
                follow_redirects=True)
    assert "Email hoặc mật khẩu không đúng." in resp.get_data(as_text=True)
    with app.app_context():
        u = db.session.execute(select(User).filter_by(email=CUSTOMER)).scalar_one()
        u.is_active = True
        db.session.commit()


def test_login_post_next_noi_bo_duoc_redirect(app):
    client = anon(app)
    token = _get_csrf(client, "/auth/login")
    resp = post(client, "/auth/login?next=%2Fauth%2Fprofile", token,
                data={"email": CUSTOMER, "password": PWD})
    assert resp.status_code == 302
    assert "/auth/profile" in resp.headers["Location"]


def test_login_post_next_ngoai_trang_bi_bo_qua(app):
    client = anon(app)
    token = _get_csrf(client, "/auth/login")
    resp = post(client, "/auth/login?next=https%3A%2F%2Fevil.com", token,
                data={"email": CUSTOMER, "password": PWD})
    assert resp.status_code == 302
    assert "evil.com" not in resp.headers["Location"]


# ─── Route: POST /auth/logout ───────────────────────────────────────────────

def test_logout_post_thanh_cong(app):
    client, token = login(app, CUSTOMER)
    resp = post(client, "/auth/logout", token, follow_redirects=True)
    assert resp.status_code == 200
    # Sau khi logout, truy cập trang cần login phải redirect
    assert client.get("/auth/profile").status_code == 302


def test_logout_chua_dang_nhap_redirect_login(app):
    client = anon(app)
    token = _get_csrf(client, "/auth/login")
    resp = post(client, "/auth/logout", token)
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]


# ─── Route: GET/POST /auth/register ─────────────────────────────────────────

def test_register_get_200(app):
    assert anon(app).get("/auth/register").status_code == 200


def test_register_da_dang_nhap_redirect(app):
    client, _ = login(app, CUSTOMER)
    assert client.get("/auth/register").status_code == 302


def test_register_post_thanh_cong(app):
    email = _new_email()
    client = anon(app)
    token = _get_csrf(client, "/auth/register")
    resp = post(client, "/auth/register", token, data={
        "full_name": "Khách Mới", "email": email,
        "phone": "0912345678", "password": PWD, "confirm_password": PWD,
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert "Đăng ký thành công" in resp.get_data(as_text=True)
    with app.app_context():
        u = db.session.execute(select(User).filter_by(email=email)).scalar_one_or_none()
        assert u is not None and u.role == "customer"
        _delete_user(app, u.id)


def test_register_post_email_trung_hien_loi(app):
    client = anon(app)
    token = _get_csrf(client, "/auth/register")
    resp = post(client, "/auth/register", token, data={
        "full_name": "Khách Test", "email": CUSTOMER,
        "password": PWD, "confirm_password": PWD,
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert "Email đã được sử dụng." in resp.get_data(as_text=True)


def test_register_post_mat_khau_yeu_hien_loi(app):
    client = anon(app)
    token = _get_csrf(client, "/auth/register")
    resp = post(client, "/auth/register", token, data={
        "full_name": "X", "email": _new_email(),
        "password": "tooyshort", "confirm_password": "tooyshort",
    }, follow_redirects=True)
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    # Thiếu chữ+số hoặc ngắn hơn 8 ký tự — ít nhất một lỗi validation
    assert "Mật khẩu" in text


def test_register_post_xac_nhan_mat_khau_khong_khop(app):
    client = anon(app)
    token = _get_csrf(client, "/auth/register")
    resp = post(client, "/auth/register", token, data={
        "full_name": "X", "email": _new_email(),
        "password": PWD, "confirm_password": "Different99!",
    }, follow_redirects=True)
    assert "Mật khẩu xác nhận không khớp." in resp.get_data(as_text=True)


def test_register_post_sdt_sai_dinh_dang(app):
    client = anon(app)
    token = _get_csrf(client, "/auth/register")
    resp = post(client, "/auth/register", token, data={
        "full_name": "X", "email": _new_email(), "phone": "123",
        "password": PWD, "confirm_password": PWD,
    }, follow_redirects=True)
    assert "Số điện thoại" in resp.get_data(as_text=True)


# ─── Route: GET/POST /auth/change-password ──────────────────────────────────

def test_change_password_get_200(app):
    client, _ = login(app, CUSTOMER)
    assert client.get("/auth/change-password").status_code == 200


def test_change_password_chua_dang_nhap_redirect(app):
    assert anon(app).get("/auth/change-password").status_code == 302


def test_change_password_post_thanh_cong(app):
    email = _new_email()
    uid = _create_user(app, email, PWD)
    client, token = login(app, email)
    resp = post(client, "/auth/change-password", token, data={
        "old_password": PWD,
        "new_password": "NewPass99!",
        "confirm_password": "NewPass99!",
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert "Đổi mật khẩu thành công." in resp.get_data(as_text=True)
    # redirect về chính nó (GET)
    with app.app_context():
        from app.auth.services import authenticate
        assert authenticate(email, "NewPass99!") is not None
    _delete_user(app, uid)


def test_change_password_post_sai_mat_khau_cu(app):
    client, token = login(app, CUSTOMER)
    resp = post(client, "/auth/change-password", token, data={
        "old_password": "wrong",
        "new_password": "NewPass99!",
        "confirm_password": "NewPass99!",
    }, follow_redirects=True)
    assert "Mật khẩu hiện tại không đúng." in resp.get_data(as_text=True)


def test_change_password_post_redirect_ve_chinh_no(app):
    email = _new_email()
    uid = _create_user(app, email, PWD)
    client, token = login(app, email)
    resp = post(client, "/auth/change-password", token, data={
        "old_password": PWD,
        "new_password": "NewPass99!",
        "confirm_password": "NewPass99!",
    })
    assert resp.status_code == 302
    assert "/auth/change-password" in resp.headers["Location"]
    _delete_user(app, uid)


# ─── Route: GET/POST /auth/profile ──────────────────────────────────────────

def test_profile_get_200(app):
    client, _ = login(app, CUSTOMER)
    assert client.get("/auth/profile").status_code == 200


def test_profile_chua_dang_nhap_redirect(app):
    assert anon(app).get("/auth/profile").status_code == 302


def test_profile_post_cap_nhat_thanh_cong(app):
    email = _new_email()
    uid = _create_user(app, email)
    client, token = login(app, email)
    resp = post(client, "/auth/profile", token, data={
        "full_name": "Tên Đã Sửa", "phone": "0909090909",
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert "Đã cập nhật hồ sơ." in resp.get_data(as_text=True)
    with app.app_context():
        db.session.expire_all()
        u = db.session.get(User, uid)
        assert u.full_name == "Tên Đã Sửa"
        assert u.phone == "0909090909"
    _delete_user(app, uid)


def test_profile_post_redirect_ve_chinh_no(app):
    client, token = login(app, CUSTOMER)
    resp = post(client, "/auth/profile", token,
                data={"full_name": "Khách Test", "phone": ""})
    assert resp.status_code == 302
    assert "/auth/profile" in resp.headers["Location"]


# ─── Route: GET /auth/api-token ─────────────────────────────────────────────

def test_api_token_tra_token_hop_le(app):
    client, _ = login(app, CUSTOMER)
    resp = client.get("/auth/api-token")
    assert resp.status_code == 200
    assert resp.headers.get("Cache-Control") == "no-store"
    data = resp.get_json()
    assert data["data"]["token_type"] == "Bearer"
    assert data["data"]["expires_in"] == 900
    assert len(data["data"]["access_token"]) > 10


def test_api_token_chua_dang_nhap_redirect(app):
    resp = anon(app).get("/auth/api-token")
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]    