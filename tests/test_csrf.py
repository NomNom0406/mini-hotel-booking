"""
test_csrf.py — Kiểm tra CSRF protection cho mọi route POST ngoài /api.

Dùng fixture csrf_on (conftest.py) để bật WTF_CSRF_ENABLED = True.
TestConfig mặc định tắt CSRF; các file test khác không bị ảnh hưởng.
"""
import os
import re

import pytest
from bs4 import BeautifulSoup


# ─── Helpers ────────────────────────────────────────────────────────────────

def _get_csrf(client, url):
    """Lấy CSRF token từ trang có form."""
    resp = client.get(url)
    soup = BeautifulSoup(resp.data, "html.parser")
    token = soup.find("input", {"name": "csrf_token"})
    return token["value"] if token else ""


def _login(client, email, password):
    """Đăng nhập, lấy token từ trang login."""
    token = _get_csrf(client, "/auth/login")
    client.post("/auth/login", data={
        "email": email,
        "password": password,
        "csrf_token": token,
    }, follow_redirects=True)


# ─── Fixture tiện ích ───────────────────────────────────────────────────────

@pytest.fixture()
def anon(client, csrf_on):
    """Client chưa đăng nhập, CSRF bật."""
    return client


@pytest.fixture()
def customer(client, csrf_on):
    """Client đăng nhập customer, CSRF bật."""
    _login(client, "customer@test.com", "Password123!")
    return client


@pytest.fixture()
def admin(client, csrf_on):
    """Client đăng nhập admin, CSRF bật."""
    _login(client, "admin@test.com", "Password123!")
    return client


@pytest.fixture()
def staff(client, csrf_on):
    """Client đăng nhập receptionist, CSRF bật."""
    _login(client, "staff@test.com", "Password123!")
    return client


# ─── 1. Quét template: mọi <form method="post"> phải có csrf_token ──────────

class TestTemplateHasCsrfToken:
    """Quét tất cả template .html, kiểm tra form POST có hidden_tag hoặc csrf_token."""

    def _collect_templates(self):
        tmpl_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
        html_files = []
        for root, _, files in os.walk(tmpl_dir):
            for f in files:
                if f.endswith(".html"):
                    html_files.append(os.path.join(root, f))
        return html_files

    def test_all_post_forms_have_csrf(self):
        """Mọi <form method="post"> trong template phải có csrf_token hoặc hidden_tag."""
        missing = []
        for path in self._collect_templates():
            with open(path, encoding="utf-8") as fh:
                content = fh.read()
            # Tìm mọi form method="post" (không phân biệt hoa thường)
            forms = re.findall(
                r'<form\b[^>]*method=["\']post["\'][^>]*>.*?</form>',
                content, re.IGNORECASE | re.DOTALL,
            )
            for form in forms:
                has_csrf = (
                    "csrf_token" in form
                    or "hidden_tag" in form
                )
                if not has_csrf:
                    rel = os.path.relpath(path)
                    missing.append(rel)
                    break  # báo mỗi file một lần

        assert missing == [], (
            "Các template có <form method='post'> thiếu csrf_token/hidden_tag:\n"
            + "\n".join(missing)
        )


# ─── 2. Quét url_map: mọi route POST ngoài /api bị chặn khi thiếu token ────

class TestAllPostRoutesRequireCsrf:
    """
    Duyệt app.url_map, POST mọi route ngoài /api không kèm token
    phải nhận 400 (hoặc redirect 302 về login — route yêu cầu đăng nhập).
    """

    # Route cần tham số int — dùng id=0 (sẽ 404 trước CSRF nếu không có record,
    # nhưng CSRF check xảy ra trước @login_required và trước db lookup).
    _INT_PLACEHOLDER = 1

    def _fill_rule(self, rule):
        """Điền placeholder vào rule có <int:...>."""
        return re.sub(r"<int:[^>]+>", str(self._INT_PLACEHOLDER), rule)

    def test_all_web_post_routes_reject_missing_token(self, app, client, csrf_on):
        """POST không có csrf_token phải nhận 400 hoặc redirect (302 → login)."""
        failures = []
        with app.app_context():
            rules = [
                r for r in app.url_map.iter_rules()
                if "POST" in r.methods and not r.rule.startswith("/api")
            ]

        for rule in rules:
            url = self._fill_rule(rule.rule)
            resp = client.post(url, data={}, follow_redirects=False)
            # 400 = CSRF bị chặn; 302 = redirect về login (trước khi vào route)
            # 404 = placeholder id không tồn tại — cũng OK (CSRF xảy ra sau login check)
            # 405 = method not allowed — không nên xảy ra (đã lọc POST)
            if resp.status_code not in (400, 302, 404):
                failures.append(
                    f"{rule.endpoint:45s} {url}  → {resp.status_code}"
                )

        assert failures == [], (
            "Các route POST không trả 400/302/404 khi thiếu CSRF token:\n"
            + "\n".join(failures)
        )


# ─── 3. Auth routes ─────────────────────────────────────────────────────────

class TestAuthCsrf:
    def test_login_missing_token_returns_400(self, anon):
        resp = anon.post("/auth/login", data={
            "email": "customer@test.com",
            "password": "Password123!",
        })
        assert resp.status_code == 400

    def test_login_wrong_token_returns_400(self, anon):
        resp = anon.post("/auth/login", data={
            "email": "customer@test.com",
            "password": "Password123!",
            "csrf_token": "badtoken",
        })
        assert resp.status_code == 400

    def test_login_valid_token_succeeds(self, anon):
        token = _get_csrf(anon, "/auth/login")
        resp = anon.post("/auth/login", data={
            "email": "customer@test.com",
            "password": "Password123!",
            "csrf_token": token,
        }, follow_redirects=False)
        assert resp.status_code == 302

    def test_register_missing_token_returns_400(self, anon):
        resp = anon.post("/auth/register", data={
            "full_name": "Test User",
            "email": "newuser@test.com",
            "phone": "0900000099",
            "password": "Password123!",
            "confirm_password": "Password123!",
        })
        assert resp.status_code == 400

    def test_register_valid_token_accepted(self, anon):
        token = _get_csrf(anon, "/auth/register")
        resp = anon.post("/auth/register", data={
            "full_name": "New User",
            "email": "newcsrf@test.com",
            "phone": "0900000098",
            "password": "Password123!",
            "confirm_password": "Password123!",
            "csrf_token": token,
        }, follow_redirects=False)
        # 302 redirect = form accepted (kể cả nếu email trùng thì render lại 200)
        assert resp.status_code in (200, 302)

    def test_logout_missing_token_returns_400(self, customer):
        resp = customer.post("/auth/logout")
        assert resp.status_code == 400

    def test_logout_valid_token_succeeds(self, customer):
        # Logout form nằm trong base template — lấy token từ bất kỳ trang có form
        token = _get_csrf(customer, "/auth/profile")
        resp = customer.post("/auth/logout", data={"csrf_token": token},
                             follow_redirects=False)
        assert resp.status_code == 302

    def test_change_password_missing_token_returns_400(self, customer):
        resp = customer.post("/auth/change-password", data={
            "old_password": "Password123!",
            "new_password": "NewPass123!",
            "confirm_password": "NewPass123!",
        })
        assert resp.status_code == 400

    def test_profile_missing_token_returns_400(self, customer):
        resp = customer.post("/auth/profile", data={
            "full_name": "Updated",
            "phone": "0900000003",
        })
        assert resp.status_code == 400


# ─── 4. Hotel search & filter ───────────────────────────────────────────────

class TestHotelSearchCsrf:
    def test_search_missing_token_returns_400(self, anon):
        resp = anon.post("/hotels/search", data={"province": ""})
        assert resp.status_code == 400

    def test_search_valid_token_accepted(self, anon):
        token = _get_csrf(anon, "/")
        resp = anon.post("/hotels/search", data={
            "province": "",
            "csrf_token": token,
        }, follow_redirects=False)
        # PRG: redirect sang GET
        assert resp.status_code == 302


# ─── 5. Rooms filter ────────────────────────────────────────────────────────

class TestRoomsFilterCsrf:
    def test_rooms_filter_missing_token_returns_400(self, anon):
        resp = anon.post("/rooms/filter", data={"hotel_id": "1"})
        assert resp.status_code == 400


# ─── 6. Booking steps ───────────────────────────────────────────────────────

class TestBookingStepsCsrf:
    def test_step_dates_missing_token_returns_400(self, customer):
        resp = customer.post("/book/1/dates", data={
            "check_in": "2027-01-01",
            "check_out": "2027-01-03",
            "guests": "1",
        })
        assert resp.status_code == 400

    def test_step_guest_missing_token_returns_400(self, customer):
        resp = customer.post("/book/1/guest", data={
            "guest_name": "Test",
            "guest_phone": "0900000003",
            "guest_email": "customer@test.com",
        })
        assert resp.status_code == 400

    def test_step_confirm_missing_token_returns_400(self, customer):
        resp = customer.post("/book/1/confirm", data={})
        assert resp.status_code == 400

    def test_cancel_missing_token_returns_400(self, customer):
        resp = customer.post("/book/1/cancel", data={})
        assert resp.status_code == 400


# ─── 7. Manage bookings ─────────────────────────────────────────────────────

class TestManageBookingsCsrf:
    def test_manage_filter_missing_token_returns_400(self, staff):
        resp = staff.post("/manage/bookings/filter", data={})
        assert resp.status_code == 400

    def test_update_status_missing_token_returns_400(self, staff):
        resp = staff.post("/manage/bookings/1/status", data={
            "status": "Confirmed",
        })
        assert resp.status_code == 400


# ─── 8. Admin routes ────────────────────────────────────────────────────────

class TestAdminCsrf:
    def test_user_create_missing_token_returns_400(self, admin):
        resp = admin.post("/admin/users/new", data={
            "full_name": "X",
            "email": "x@test.com",
            "phone": "0900000099",
            "role": "customer",
            "password": "Password123!",
        })
        assert resp.status_code == 400

    def test_user_edit_missing_token_returns_400(self, admin):
        resp = admin.post("/admin/users/1/edit", data={
            "full_name": "X",
            "phone": "0900000001",
            "role": "admin",
        })
        assert resp.status_code == 400

    def test_user_toggle_missing_token_returns_400(self, admin):
        resp = admin.post("/admin/users/1/toggle", data={})
        assert resp.status_code == 400

    def test_hotel_create_missing_token_returns_400(self, admin):
        resp = admin.post("/admin/hotels/new", data={
            "name": "X Hotel",
            "province": "Hà Nội",
        })
        assert resp.status_code == 400

    def test_hotel_edit_missing_token_returns_400(self, admin):
        resp = admin.post("/admin/hotels/1/edit", data={})
        assert resp.status_code == 400

    def test_hotel_toggle_missing_token_returns_400(self, admin):
        resp = admin.post("/admin/hotels/1/toggle", data={})
        assert resp.status_code == 400

    def test_hotel_delete_missing_token_returns_400(self, admin):
        resp = admin.post("/admin/hotels/1/delete", data={})
        assert resp.status_code == 400

    def test_room_new_missing_token_returns_400(self, admin):
        resp = admin.post("/admin/rooms/new", data={})
        assert resp.status_code == 400

    def test_room_edit_missing_token_returns_400(self, admin):
        resp = admin.post("/admin/rooms/1/edit", data={})
        assert resp.status_code == 400

    def test_room_toggle_missing_token_returns_400(self, admin):
        resp = admin.post("/admin/rooms/1/toggle", data={})
        assert resp.status_code == 400

    def test_roomtype_new_missing_token_returns_400(self, admin):
        resp = admin.post("/admin/roomtypes/new", data={})
        assert resp.status_code == 400

    def test_roomtype_edit_missing_token_returns_400(self, admin):
        resp = admin.post("/admin/roomtypes/1/edit", data={})
        assert resp.status_code == 400

    def test_roomtype_delete_image_missing_token_returns_400(self, admin):
        resp = admin.post("/admin/roomtypes/1/delete-image", data={})
        assert resp.status_code == 400

    def test_amenity_new_missing_token_returns_400(self, admin):
        resp = admin.post("/admin/amenities/new", data={})
        assert resp.status_code == 400

    def test_amenity_edit_missing_token_returns_400(self, admin):
        resp = admin.post("/admin/amenities/1/edit", data={})
        assert resp.status_code == 400

    def test_amenity_delete_missing_token_returns_400(self, admin):
        resp = admin.post("/admin/amenities/1/delete", data={})
        assert resp.status_code == 400


# ─── 9. API blueprint miễn CSRF ─────────────────────────────────────────────

class TestApiBlueprintExemptFromCsrf:
    """Route /api không bị chặn bởi CSRF (xác thực bằng JWT header)."""

    def test_api_login_no_csrf_token_not_400(self, anon):
        """POST /api/auth/login không có CSRF token — không bị 400."""
        resp = anon.post("/api/auth/login", json={
            "email": "customer@test.com",
            "password": "Password123!",
        })
        # 200 (token ok) hoặc 401 (sai pw) đều chấp nhận; chỉ không phải 400
        assert resp.status_code != 400