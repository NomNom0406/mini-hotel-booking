"""Test blueprint admin (app/admin/routes.py + services.py).

Dùng tài khoản pytest: admin@test.com, staff@test.com, customer@test.com.
User tạo thêm trong test phải tự dọn.
"""
import pytest
from flask import template_rendered
from contextlib import contextmanager
from sqlalchemy import select

from app.extensions import db
from app.models import User
from tests.room_helpers import (  # noqa: F401
    anon, clean_bookings, login, make_booking, post, scratch,
)

ADMIN    = "admin@test.com"
STAFF    = "staff@test.com"
CUSTOMER = "customer@test.com"
PWD      = "Password123!"


# ─── Helper ─────────────────────────────────────────────────────────────────

@contextmanager
def captured(app):
    records = []
    def record(sender, template, context, **extra):
        records.append((template.name, context))
    template_rendered.connect(record, app)
    try:
        yield records
    finally:
        template_rendered.disconnect(record, app)


def _get_csrf(client, url):
    from tests.conftest import _get_csrf as _c
    return _c(client, url)


def _new_email():
    import uuid
    return f"tmp_{uuid.uuid4().hex[:10]}@test.com"


def _delete_user(app, user_id):
    with app.app_context():
        u = db.session.get(User, user_id)
        if u:
            db.session.delete(u)
            db.session.commit()


def _page(resp):
    return resp.get_data(as_text=True)


# ─── Phân quyền dashboard ───────────────────────────────────────────────────

def test_dashboard_chi_admin_vao_duoc(app):
    admin, _ = login(app, ADMIN)
    assert admin.get("/admin/dashboard").status_code == 200


def test_dashboard_staff_bi_403(app):
    staff, _ = login(app, STAFF)
    assert staff.get("/admin/dashboard").status_code == 403


def test_dashboard_customer_bi_403(app):
    client, _ = login(app, CUSTOMER)
    assert client.get("/admin/dashboard").status_code == 403


def test_dashboard_chua_dang_nhap_redirect_login(app):
    resp = anon(app).get("/admin/dashboard")
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]


# ─── Dashboard render ────────────────────────────────────────────────────────

def test_dashboard_render_dung_template(app):
    admin, _ = login(app, ADMIN)
    with captured(app) as records:
        resp = admin.get("/admin/dashboard")
    assert resp.status_code == 200
    assert records[-1][0] == "admin/dashboard.html"


def test_dashboard_context_co_data_va_hotels(app):
    admin, _ = login(app, ADMIN)
    with captured(app) as records:
        admin.get("/admin/dashboard")
    ctx = records[-1][1]
    assert "data" in ctx and "hotels" in ctx
    data = ctx["data"]
    assert "revenue" in data
    assert "occupancy" in data
    assert "bookings" in data
    assert "occupancy_today" in data


def test_dashboard_data_revenue_co_6_thang(app):
    admin, _ = login(app, ADMIN)
    with captured(app) as records:
        admin.get("/admin/dashboard")
    revenue = records[-1][1]["data"]["revenue"]
    assert len(revenue) == 6
    for item in revenue:
        assert "month" in item and "revenue" in item


def test_dashboard_loc_theo_hotel_id(app, scratch):
    from tests.room_helpers import Scratch
    admin, _ = login(app, ADMIN)
    with captured(app) as records:
        admin.get(f"/admin/dashboard?hotel_id={scratch.hotel().hotel_id}")
    ctx = records[-1][1]
    assert ctx["selected_hotel_id"] is not None


# ─── /admin/dashboard/data (JSON) ───────────────────────────────────────────

def test_dashboard_data_endpoint_tra_json(app):
    admin, _ = login(app, ADMIN)
    resp = admin.get("/admin/dashboard/data")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "revenue" in data and "bookings" in data


def test_dashboard_data_staff_bi_403(app):
    staff, _ = login(app, STAFF)
    assert staff.get("/admin/dashboard/data").status_code == 403


def test_dashboard_data_chua_dang_nhap_redirect(app):
    resp = anon(app).get("/admin/dashboard/data")
    assert resp.status_code == 302


# ─── /admin/users ───────────────────────────────────────────────────────────

def test_users_list_200(app):
    admin, _ = login(app, ADMIN)
    with captured(app) as records:
        resp = admin.get("/admin/users")
    assert resp.status_code == 200
    assert records[-1][0] == "admin/users.html"
    assert "users" in records[-1][1]


def test_users_list_co_du_tai_khoan_test(app):
    admin, _ = login(app, ADMIN)
    with captured(app) as records:
        admin.get("/admin/users")
    emails = {u.email for u in records[-1][1]["users"]}
    assert {ADMIN, STAFF, CUSTOMER} <= emails


def test_users_list_staff_bi_403(app):
    staff, _ = login(app, STAFF)
    assert staff.get("/admin/users").status_code == 403


def test_users_list_customer_bi_403(app):
    client, _ = login(app, CUSTOMER)
    assert client.get("/admin/users").status_code == 403


# ─── /admin/users/new ───────────────────────────────────────────────────────

def test_user_create_get_200(app):
    admin, _ = login(app, ADMIN)
    with captured(app) as records:
        resp = admin.get("/admin/users/new")
    assert resp.status_code == 200
    assert records[-1][0] == "admin/user_form.html"
    assert records[-1][1]["user"] is None


def test_user_create_thanh_cong(app):
    email = _new_email()
    admin, token = login(app, ADMIN)
    resp = post(admin, "/admin/users/new", token, data={
        "full_name": "Lễ Tân Mới", "email": email, "phone": "",
        "password": PWD, "confirm_password": PWD,
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert "Đã tạo tài khoản lễ tân" in _page(resp)
    with app.app_context():
        u = db.session.execute(select(User).filter_by(email=email)).scalar_one_or_none()
        assert u is not None and u.role == "receptionist"
        _delete_user(app, u.id)


def test_user_create_redirect_ve_danh_sach(app):
    email = _new_email()
    admin, token = login(app, ADMIN)
    resp = post(admin, "/admin/users/new", token, data={
        "full_name": "Le Tan", "email": email, "phone": "",
        "password": PWD, "confirm_password": PWD,
    })
    assert resp.status_code == 302
    assert "/admin/users" in resp.headers["Location"]
    with app.app_context():
        u = db.session.execute(select(User).filter_by(email=email)).scalar_one_or_none()
        if u:
            _delete_user(app, u.id)


def test_user_create_email_trung_hien_loi(app):
    admin, token = login(app, ADMIN)
    with captured(app) as records:
        resp = post(admin, "/admin/users/new", token, data={
            "full_name": "Le Tan", "email": CUSTOMER, "phone": "",
            "password": PWD, "confirm_password": PWD,
        })
    assert resp.status_code == 200
    assert records[-1][0] == "admin/user_form.html"
    assert "Email đã được sử dụng." in _page(resp)


def test_user_create_du_lieu_sai_render_lai_form(app):
    admin, token = login(app, ADMIN)
    with captured(app) as records:
        resp = post(admin, "/admin/users/new", token, data={
            "full_name": "X", "email": "not-an-email", "phone": "",
            "password": PWD, "confirm_password": PWD,
        })
    assert resp.status_code == 200
    assert records[-1][0] == "admin/user_form.html"


def test_user_create_staff_bi_403(app):
    staff, token = login(app, STAFF)
    resp = post(staff, "/admin/users/new", token, data={
        "full_name": "X", "email": _new_email(), "phone": "",
        "password": PWD, "confirm_password": PWD,
    })
    assert resp.status_code == 403


# ─── /admin/users/<id>/edit ─────────────────────────────────────────────────

def test_user_edit_get_dien_san_form(app):
    email = _new_email()
    uid = None
    with app.app_context():
        from werkzeug.security import generate_password_hash
        u = User(full_name="Edit Me", email=email, phone=None,
                 password_hash=generate_password_hash(PWD),
                 role="customer", is_active=True)
        db.session.add(u)
        db.session.commit()
        uid = u.id
    admin, _ = login(app, ADMIN)
    with captured(app) as records:
        resp = admin.get(f"/admin/users/{uid}/edit")
    assert resp.status_code == 200
    ctx = records[-1][1]
    assert ctx["form"].full_name.data == "Edit Me"
    assert ctx["user"].id == uid
    _delete_user(app, uid)


def test_user_edit_khong_ton_tai_404(app):
    admin, token = login(app, ADMIN)
    assert admin.get("/admin/users/99999999/edit").status_code == 404


def test_user_edit_thanh_cong(app):
    email = _new_email()
    uid = None
    with app.app_context():
        from werkzeug.security import generate_password_hash
        u = User(full_name="Old Name", email=email, phone=None,
                 password_hash=generate_password_hash(PWD),
                 role="customer", is_active=True)
        db.session.add(u)
        db.session.commit()
        uid = u.id
    admin, token = login(app, ADMIN)
    resp = post(admin, f"/admin/users/{uid}/edit", token, data={
        "full_name": "New Name", "role": "receptionist", "is_active": "y",
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert "Đã cập nhật người dùng" in _page(resp)
    with app.app_context():
        db.session.expire_all()
        u = db.session.get(User, uid)
        assert u.full_name == "New Name" and u.role == "receptionist"
    _delete_user(app, uid)


def test_user_edit_admin_khong_tu_ha_quyen(app):
    with app.app_context():
        admin_user = db.session.execute(
            select(User).filter_by(email=ADMIN)).scalar_one()
        uid = admin_user.id
    admin, token = login(app, ADMIN)
    resp = post(admin, f"/admin/users/{uid}/edit", token, data={
        "full_name": "Admin", "role": "customer", "is_active": "y",
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert "không thể" in _page(resp).lower() or "Bạn không thể" in _page(resp)
    with app.app_context():
        db.session.expire_all()
        assert db.session.get(User, uid).role == "admin"


def test_user_edit_staff_bi_403(app):
    with app.app_context():
        uid = db.session.execute(
            select(User).filter_by(email=CUSTOMER)).scalar_one().id
    staff, token = login(app, STAFF)
    assert post(staff, f"/admin/users/{uid}/edit", token,
                data={"full_name": "X", "role": "customer"}).status_code == 403


# ─── /admin/users/<id>/toggle ───────────────────────────────────────────────

def test_user_toggle_khoa_roi_mo_lai(app):
    email = _new_email()
    uid = None
    with app.app_context():
        from werkzeug.security import generate_password_hash
        u = User(full_name="Toggle Me", email=email, phone=None,
                 password_hash=generate_password_hash(PWD),
                 role="customer", is_active=True)
        db.session.add(u)
        db.session.commit()
        uid = u.id

    admin, token = login(app, ADMIN)
    # Khóa
    post(admin, f"/admin/users/{uid}/toggle", token, follow_redirects=True)
    with app.app_context():
        db.session.expire_all()
        assert db.session.get(User, uid).is_active is False
    # Mở lại
    post(admin, f"/admin/users/{uid}/toggle", token, follow_redirects=True)
    with app.app_context():
        db.session.expire_all()
        assert db.session.get(User, uid).is_active is True
    _delete_user(app, uid)


def test_user_toggle_admin_khong_tu_khoa_minh(app):
    with app.app_context():
        uid = db.session.execute(
            select(User).filter_by(email=ADMIN)).scalar_one().id
    admin, token = login(app, ADMIN)
    resp = post(admin, f"/admin/users/{uid}/toggle", token, follow_redirects=True)
    assert resp.status_code == 200
    assert "không thể" in _page(resp).lower() or "Bạn không thể" in _page(resp)
    with app.app_context():
        db.session.expire_all()
        assert db.session.get(User, uid).is_active is True


def test_user_toggle_khong_ton_tai_404(app):
    admin, token = login(app, ADMIN)
    assert post(admin, "/admin/users/99999999/toggle", token).status_code == 404


def test_user_toggle_chi_nhan_post(app):
    with app.app_context():
        uid = db.session.execute(
            select(User).filter_by(email=CUSTOMER)).scalar_one().id
    admin, _ = login(app, ADMIN)
    assert admin.get(f"/admin/users/{uid}/toggle").status_code == 405


def test_user_toggle_staff_bi_403(app):
    with app.app_context():
        uid = db.session.execute(
            select(User).filter_by(email=CUSTOMER)).scalar_one().id
    staff, token = login(app, STAFF)
    assert post(staff, f"/admin/users/{uid}/toggle", token).status_code == 403


# ─── admin/services: get_dashboard_data ─────────────────────────────────────

def test_get_dashboard_data_co_du_key(app):
    from app.admin.services import get_dashboard_data
    with app.app_context():
        data = get_dashboard_data()
    assert set(data.keys()) == {
        "revenue", "revenue_total", "occupancy",
        "occupancy_today", "bookings", "bookings_total"
    }


def test_get_revenue_by_month_co_6_thang(app):
    from app.admin.services import get_revenue_by_month
    with app.app_context():
        result = get_revenue_by_month()
    assert len(result) == 6
    for item in result:
        assert "month" in item and "revenue" in item
        assert item["revenue"] >= 0


def test_get_bookings_by_month_co_du_key(app):
    from app.admin.services import get_bookings_by_month
    with app.app_context():
        result = get_bookings_by_month()
    assert "months" in result and "series" in result and "ratio" in result
    assert len(result["months"]) == 6
    for status in ("Pending", "Confirmed", "Cancelled", "Completed"):
        assert status in result["series"]


def test_get_occupancy_today_co_du_key(app):
    from app.admin.services import get_occupancy_today
    with app.app_context():
        result = get_occupancy_today()
    assert "occupied" in result and "active_rooms" in result and "rate" in result
    assert 0 <= result["rate"] <= 100


def test_get_hotel_choices_tra_danh_sach(app):
    from app.admin.services import get_hotel_choices
    with app.app_context():
        choices = get_hotel_choices()
    # Test Hotel active → phải có trong danh sách
    assert any(name == "Test Hotel" for _, name in choices)


# ─── admin/services: user management ────────────────────────────────────────

def test_create_receptionist_tao_duoc(app):
    from app.admin.services import create_receptionist
    email = _new_email()
    with app.app_context():
        u = create_receptionist("Le Tan Moi", email, "0912345678", PWD)
        uid = u.id
        assert u.role == "receptionist" and u.is_active is True
    _delete_user(app, uid)


def test_create_receptionist_email_trung_raise(app):
    from app.admin.services import create_receptionist
    from app.auth.services import EmailTaken
    with app.app_context():
        with pytest.raises(EmailTaken):
            create_receptionist("X", CUSTOMER, "", PWD)


def test_update_user_doi_vai_tro(app):
    from app.admin.services import update_user
    email = _new_email()
    uid = None
    with app.app_context():
        from werkzeug.security import generate_password_hash
        u = User(full_name="U", email=email, phone=None,
                 password_hash=generate_password_hash(PWD),
                 role="customer", is_active=True)
        db.session.add(u)
        db.session.commit()
        uid = u.id
        actor = db.session.execute(select(User).filter_by(email=ADMIN)).scalar_one()
        update_user(u, actor, "U Moi", "receptionist", True)
        db.session.expire_all()
        assert db.session.get(User, uid).role == "receptionist"
    _delete_user(app, uid)


def test_update_user_tu_ha_quyen_raise(app):
    from app.admin.services import update_user
    with app.app_context():
        actor = db.session.execute(select(User).filter_by(email=ADMIN)).scalar_one()
        with pytest.raises(PermissionError):
            update_user(actor, actor, actor.full_name, "customer", True)


def test_set_user_active_tu_khoa_minh_raise(app):
    from app.admin.services import set_user_active
    with app.app_context():
        actor = db.session.execute(select(User).filter_by(email=ADMIN)).scalar_one()
        with pytest.raises(PermissionError):
            set_user_active(actor, actor, False)