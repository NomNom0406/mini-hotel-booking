"""Test route của blueprint hotels (app/hotels/routes.py): trang công khai và trang admin.

Dùng tín hiệu template_rendered để đọc context của template (tránh phụ thuộc vào HTML).
Ảnh upload ghi vào thư mục tạm; thư mục ảnh dưới static/uploads/hotels/<slug> do test tạo
được xóa qua scratch.dirs.
"""
import os
from contextlib import contextmanager
from io import BytesIO
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from flask import g, template_rendered
from sqlalchemy import select

from app.extensions import db
from app.hotels import routes as hotel_routes
from app.models import Amenity, Booking, Hotel
from app.utils.security import slugify
from tests.conftest import _get_csrf
from tests.room_helpers import (  # noqa: F401  (clean_bookings là fixture autouse)
    anon, clean_bookings, future, login, make_booking, post, scratch,
)

ADMIN = "admin@test.com"


@pytest.fixture
def uploads(app, tmp_path, monkeypatch):
    monkeypatch.setitem(app.config, "UPLOAD_FOLDER", str(tmp_path))
    return tmp_path


@pytest.fixture
def csrf_on(app, monkeypatch):
    """TestConfig tắt CSRF cho các test khác; bật lại cho riêng test kiểm tra CSRF.

    Flask-WTF giữ token trong g.csrf_token và app context dùng chung cả phiên pytest,
    nên phải xóa token cũ trước và sau để mỗi client nhận token đúng với session của nó.
    """
    monkeypatch.setitem(app.config, "WTF_CSRF_ENABLED", True)
    g.pop("csrf_token", None)
    yield
    g.pop("csrf_token", None)


# ─── Helper ─────────────────────────────────────────────────────────────────

@contextmanager
def captured(app):
    """Ghi lại (tên template, context) của mọi lần render trong khối with."""
    records = []

    def record(sender, template, context, **extra):
        records.append((template.name, context))

    template_rendered.connect(record, app)
    try:
        yield records
    finally:
        template_rendered.disconnect(record, app)


def _isolate(info):
    province = "Tinh " + uuid4().hex[:8]
    db.session.get(Hotel, info.hotel_id).province = province
    db.session.commit()
    return province


def _form(name, **overrides):
    data = {"name": name, "province": "Cần Thơ", "address": "1 Đường A",
            "star_rating": "4", "description": "Mô tả", "map_url": ""}
    data.update(overrides)
    return data


def _hotel_dir(app, scratch, name):
    """Thư mục ảnh của khách sạn theo tên; đăng ký để xóa khi test xong."""
    path = os.path.join(app.static_folder, "uploads", "hotels", slugify(name))
    scratch.dirs.append(path)
    return path


def _track(scratch, name):
    """Tìm khách sạn vừa tạo qua route theo tên và đăng ký dọn dẹp."""
    db.session.expire_all()
    hotel = db.session.execute(select(Hotel).filter_by(name=name)).scalar_one_or_none()
    if hotel is not None:
        scratch.hotel_ids.append(hotel.id)
    return hotel


def _page(resp):
    return resp.get_data(as_text=True)


# ─── _hotel_folder (hàm thuần) ──────────────────────────────────────────────

@pytest.mark.parametrize("image,expected", [
    ("hotels/foo/cover.jpg", "uploads/hotels/foo"),
    ("uploads/hotels/foo/cover.jpg", "uploads/hotels/foo"),
    ("uploads\\hotels\\foo\\cover.jpg", "uploads/hotels/foo"),
    ("abc.jpg", "uploads/hotels/khach-san-da-lat"),
    ("uploads/abc.jpg", "uploads/hotels/khach-san-da-lat"),
    (None, "uploads/hotels/khach-san-da-lat"),
    ("", "uploads/hotels/khach-san-da-lat"),
])
def test_hotel_folder(image, expected):
    hotel = SimpleNamespace(image_filename=image, name="Khách Sạn Đà Lạt")
    assert hotel_routes._hotel_folder(hotel) == expected


# ─── Trang chủ và tìm kiếm ──────────────────────────────────────────────────

def test_trang_chu_200(app):
    with captured(app) as records:
        resp = anon(app).get("/")
    assert resp.status_code == 200
    name, ctx = records[-1]
    assert name == "hotels/home.html"
    assert "Hà Nội" in ctx["provinces"]


def test_search_post_thieu_csrf_bi_400(app, csrf_on):
    resp = anon(app).post("/hotels/search", data={"province": ""})
    assert resp.status_code == 400


def test_search_post_co_csrf_hop_le_redirect(app, csrf_on):
    client = anon(app)
    token = _get_csrf(client, "/")
    assert token  # form có sinh csrf_token khi CSRF bật
    resp = post(client, "/hotels/search", token, data={
        "province": "", "checkin": "", "checkout": "", "guests": "1"})
    assert resp.status_code == 302


def test_search_post_hop_le_redirect_sang_get(app):
    client = anon(app)
    token = _get_csrf(client, "/")
    ci, co = future(5).isoformat(), future(7).isoformat()
    resp = post(client, "/hotels/search", token, data={
        "province": "Hà Nội", "checkin": ci, "checkout": co, "guests": "2"})
    assert resp.status_code == 302
    location = urlparse(resp.headers["Location"])
    assert location.path == "/hotels/search"
    assert parse_qs(location.query) == {
        "province": ["Hà Nội"], "checkin": [ci], "checkout": [co], "guests": ["2"]}


def test_search_post_bo_trong_ngay_van_redirect(app):
    client = anon(app)
    token = _get_csrf(client, "/")
    resp = post(client, "/hotels/search", token, data={
        "province": "", "checkin": "", "checkout": "", "guests": ""})
    assert resp.status_code == 302
    query = parse_qs(urlparse(resp.headers["Location"]).query)
    assert query == {"guests": ["1"]}


@pytest.mark.parametrize("data", [
    {"province": "Hà Nội", "checkin": future(7).isoformat(), "checkout": future(5).isoformat()},
    {"province": "Hà Nội", "checkin": future(5).isoformat(), "checkout": ""},
    {"province": "Không Có Tỉnh Này", "checkin": "", "checkout": ""},
    {"province": "Hà Nội", "checkin": "", "checkout": "", "guests": "0"},
])
def test_search_post_khong_hop_le_tra_422(app, data):
    client = anon(app)
    token = _get_csrf(client, "/")
    with captured(app) as records:
        resp = post(client, "/hotels/search", token, data=data)
    assert resp.status_code == 422
    assert records[-1][0] == "hotels/home.html"


def test_search_get_tra_ket_qua(app, scratch):
    info = scratch.hotel(price=450000)
    province = _isolate(info)
    with captured(app) as records:
        resp = anon(app).get("/hotels/search", query_string={"province": province})
    assert resp.status_code == 200
    name, ctx = records[-1]
    assert name == "hotels/search_results.html"
    assert [h.id for h in ctx["pagination"].items] == [info.hotel_id]
    assert ctx["prices"][info.hotel_id] == 450000
    assert ctx["params"]["province"] == province
    assert ctx["query"] == {"province": province}


def test_search_get_loc_theo_sao_va_ngay(app, scratch):
    info = scratch.hotel()
    province = _isolate(info)
    make_booking(info.room_id, future(10), future(12), "Pending")
    client = anon(app)

    with captured(app) as records:
        client.get("/hotels/search", query_string={"province": province, "stars": 5})
    assert records[-1][1]["pagination"].items == []

    with captured(app) as records:
        client.get("/hotels/search", query_string={
            "province": province,
            "checkin": future(10).isoformat(), "checkout": future(12).isoformat()})
    assert records[-1][1]["pagination"].items == []

    with captured(app) as records:
        client.get("/hotels/search", query_string={
            "province": province,
            "checkin": future(20).isoformat(), "checkout": future(22).isoformat()})
    assert [h.id for h in records[-1][1]["pagination"].items] == [info.hotel_id]


def test_search_get_tham_so_sai_van_200_va_hien_canh_bao(app):
    resp = anon(app).get("/hotels/search", query_string={"sort": "bogus", "guests": "0"})
    assert resp.status_code == 200
    text = _page(resp)
    assert "Cách sắp xếp không hợp lệ." in text
    assert "Tham số guests nằm ngoài khoảng cho phép." in text


def test_search_get_trang_vuot_qua_van_200(app):
    resp = anon(app).get("/hotels/search", query_string={"page": 999})
    assert resp.status_code == 200


# ─── Chi tiết khách sạn ─────────────────────────────────────────────────────

def test_detail_200_khong_ngay(app, scratch):
    info = scratch.hotel()
    with captured(app) as records:
        resp = anon(app).get(f"/hotels/{info.hotel_id}")
    assert resp.status_code == 200
    name, ctx = records[-1]
    assert name == "hotels/detail.html"
    assert ctx["hotel"].id == info.hotel_id
    assert len(ctx["groups"]) == 1
    assert ctx["has_dates"] is False
    assert ctx["checkin"] == "" and ctx["checkout"] == ""
    assert ctx["guests"] == 1
    assert ctx["gallery"] == []


def test_detail_404_khach_san_an_hoac_khong_ton_tai(app, scratch):
    hidden = scratch.hotel(active=False)
    assert anon(app).get(f"/hotels/{hidden.hotel_id}").status_code == 404
    assert anon(app).get("/hotels/99999999").status_code == 404


def test_detail_co_ngay_hop_le(app, scratch):
    info = scratch.hotel()
    ci, co = future(5).isoformat(), future(7).isoformat()
    with captured(app) as records:
        resp = anon(app).get(f"/hotels/{info.hotel_id}",
                             query_string={"checkin": ci, "checkout": co, "guests": 2})
    assert resp.status_code == 200
    ctx = records[-1][1]
    assert ctx["has_dates"] is True
    assert (ctx["checkin"], ctx["checkout"], ctx["guests"]) == (ci, co, 2)
    assert ctx["groups"][0]["nights"] == 2


def test_detail_loai_phong_da_dat(app, scratch):
    info = scratch.hotel()
    make_booking(info.room_id, future(5), future(7), "Confirmed")
    with captured(app) as records:
        anon(app).get(f"/hotels/{info.hotel_id}", query_string={
            "checkin": future(5).isoformat(), "checkout": future(7).isoformat()})
    assert records[-1][1]["groups"] == []


def test_detail_ngay_nhan_trong_qua_khu(app, scratch):
    info = scratch.hotel()
    with captured(app) as records:
        resp = anon(app).get(f"/hotels/{info.hotel_id}", query_string={
            "checkin": future(-3).isoformat(), "checkout": future(2).isoformat()})
    assert resp.status_code == 200
    ctx = records[-1][1]
    assert ctx["has_dates"] is False and ctx["checkin"] == ""
    assert "Ngày nhận không được trong quá khứ." in _page(resp)


def test_detail_ngay_tra_khong_sau_ngay_nhan(app, scratch):
    info = scratch.hotel()
    with captured(app) as records:
        anon(app).get(f"/hotels/{info.hotel_id}", query_string={
            "checkin": future(7).isoformat(), "checkout": future(5).isoformat()})
    assert records[-1][1]["has_dates"] is False


@pytest.mark.parametrize("raw,expected", [("0", 1), ("-4", 1), ("abc", 1), ("3", 3)])
def test_detail_so_khach(app, scratch, raw, expected):
    info = scratch.hotel()
    with captured(app) as records:
        anon(app).get(f"/hotels/{info.hotel_id}", query_string={"guests": raw})
    assert records[-1][1]["guests"] == expected


def test_detail_gallery_anh_bia_tran(app, scratch):
    info = scratch.hotel()
    db.session.get(Hotel, info.hotel_id).image_filename = "bare-xyz.jpg"
    db.session.commit()
    with captured(app) as records:
        anon(app).get(f"/hotels/{info.hotel_id}")
    assert records[-1][1]["gallery"] == ["uploads/bare-xyz.jpg"]


def test_detail_gallery_doc_thu_muc_khach_san(app, scratch):
    info = scratch.hotel()
    slug = slugify(info.hotel_name)
    folder = _hotel_dir(app, scratch, info.hotel_name)
    os.makedirs(folder)
    for filename in ("cover.jpg", "b.png", "notes.txt"):
        with open(os.path.join(folder, filename), "wb") as handle:
            handle.write(b"x")
    db.session.get(Hotel, info.hotel_id).image_filename = f"uploads/hotels/{slug}/cover.jpg"
    db.session.commit()

    with captured(app) as records:
        anon(app).get(f"/hotels/{info.hotel_id}")
    assert records[-1][1]["gallery"] == [
        f"uploads/hotels/{slug}/cover.jpg", f"uploads/hotels/{slug}/b.png"]


# ─── Phân quyền /admin/hotels ───────────────────────────────────────────────

def _admin_urls(hotel_id):
    base = f"/admin/hotels/{hotel_id}"
    return [("get", "/admin/hotels"), ("get", "/admin/hotels/new"),
            ("get", f"{base}/edit"), ("post", f"{base}/toggle"),
            ("post", f"{base}/delete"), ("post", f"{base}/delete-image")]


@pytest.mark.parametrize("email", ["customer@test.com", "staff@test.com"])
def test_khong_phai_admin_bi_403_va_du_lieu_khong_doi(app, scratch, email):
    info = scratch.hotel()
    client, token = login(app, email)
    for method, url in _admin_urls(info.hotel_id):
        resp = client.get(url) if method == "get" else post(client, url, token)
        assert resp.status_code == 403, (method, url)
    db.session.expire_all()
    hotel = db.session.get(Hotel, info.hotel_id)
    assert hotel is not None and hotel.is_active is True


def test_chua_dang_nhap_bi_chuyen_ve_trang_login(app, scratch):
    info = scratch.hotel()
    client = anon(app)
    token = _get_csrf(client, "/auth/login")
    for method, url in _admin_urls(info.hotel_id):
        resp = client.get(url) if method == "get" else post(client, url, token)
        assert resp.status_code == 302, (method, url)
        assert "/auth/login" in resp.headers["Location"], (method, url)
    db.session.expire_all()
    assert db.session.get(Hotel, info.hotel_id) is not None


# ─── Admin: danh sách ───────────────────────────────────────────────────────

def test_admin_list_200(app, scratch):
    active = scratch.hotel()
    hidden = scratch.hotel(active=False)
    admin, _ = login(app, ADMIN)
    with captured(app) as records:
        resp = admin.get("/admin/hotels")
    assert resp.status_code == 200
    name, ctx = records[-1]
    assert name == "admin/hotels.html"
    ids = {h.id for h in ctx["hotels"]}
    assert {active.hotel_id, hidden.hotel_id} <= ids
    assert ctx["room_counts"][active.hotel_id] == 1


# ─── Admin: tạo ─────────────────────────────────────────────────────────────

def test_admin_create_get_200(app):
    admin, _ = login(app, ADMIN)
    with captured(app) as records:
        resp = admin.get("/admin/hotels/new")
    assert resp.status_code == 200
    assert records[-1][0] == "admin/hotel_form.html"
    assert records[-1][1]["hotel"] is None


def test_admin_create_thanh_cong(app, scratch):
    amenity = scratch.amenity()
    name = "Tmp Hotel New " + uuid4().hex[:8]
    admin, token = login(app, ADMIN)
    resp = post(admin, "/admin/hotels/new", token, data=_form(
        name, amenity_ids=[str(amenity.id)], map_url="https://maps.google.com/x"))
    hotel = _track(scratch, name)

    assert resp.status_code == 302
    assert urlparse(resp.headers["Location"]).path == "/admin/hotels"
    assert hotel is not None
    assert hotel.province == "Cần Thơ" and hotel.star_rating == 4
    assert hotel.map_url == "https://maps.google.com/x"
    assert hotel.is_active is True
    assert [a.id for a in hotel.amenities] == [amenity.id]


def test_admin_create_hien_thong_bao_thanh_cong(app, scratch):
    name = "Tmp Hotel New " + uuid4().hex[:8]
    admin, token = login(app, ADMIN)
    resp = post(admin, "/admin/hotels/new", token, data=_form(name), follow_redirects=True)
    _track(scratch, name)
    assert resp.status_code == 200
    assert "Đã thêm khách sạn" in _page(resp)


def test_admin_create_du_lieu_sai_render_lai_form(app, scratch):
    name = "Tmp Hotel New " + uuid4().hex[:8]
    admin, token = login(app, ADMIN)
    with captured(app) as records:
        resp = post(admin, "/admin/hotels/new", token, data=_form(name, province="A"))
    assert resp.status_code == 200
    assert records[-1][0] == "admin/hotel_form.html"
    assert records[-1][1]["form"].province.errors
    assert _track(scratch, name) is None


def test_admin_create_thieu_csrf_bi_400(app, scratch, csrf_on):
    name = "Tmp Hotel No Csrf " + uuid4().hex[:8]
    admin, token = login(app, ADMIN)
    assert token
    assert admin.get("/admin/hotels").status_code == 200  # đã đăng nhập thật
    resp = admin.post("/admin/hotels/new", data=_form(name))
    assert resp.status_code == 400
    assert _track(scratch, name) is None


def test_admin_create_co_csrf_hop_le(app, scratch, csrf_on):
    name = "Tmp Hotel With Csrf " + uuid4().hex[:8]
    admin, _ = login(app, ADMIN)
    # đăng nhập phải thành công khi CSRF bật
    assert admin.get("/admin/hotels").status_code == 200
    # token lấy trước khi đăng nhập có thể đã bị làm mới: lấy token mới từ trang form
    token = _get_csrf(admin, "/admin/hotels/new")
    assert token
    resp = post(admin, "/admin/hotels/new", token, data=_form(name))
    hotel = _track(scratch, name)
    assert resp.status_code == 302
    assert hotel is not None


def test_admin_create_trung_ten(app, scratch):
    info = scratch.hotel()
    admin, token = login(app, ADMIN)
    with captured(app) as records:
        resp = post(admin, "/admin/hotels/new", token, data=_form(info.hotel_name))
    assert resp.status_code == 200
    assert "Tên khách sạn đã tồn tại." in records[-1][1]["form"].name.errors
    db.session.expire_all()
    assert db.session.execute(
        select(Hotel).filter_by(name=info.hotel_name)).scalars().all().__len__() == 1


def test_admin_create_co_anh_bia(app, scratch, uploads):
    name = "Tmp Hotel New " + uuid4().hex[:8]
    admin, token = login(app, ADMIN)
    resp = post(admin, "/admin/hotels/new", token,
                data={**_form(name), "image": (BytesIO(b"fake-png"), "cover.png")},
                content_type="multipart/form-data")
    hotel = _track(scratch, name)
    assert resp.status_code == 302
    assert hotel.image_filename.endswith(".png")
    assert (uploads / hotel.image_filename).exists()


def test_admin_create_anh_sai_dinh_dang(app, scratch, uploads):
    name = "Tmp Hotel New " + uuid4().hex[:8]
    admin, token = login(app, ADMIN)
    with captured(app) as records:
        resp = post(admin, "/admin/hotels/new", token,
                    data={**_form(name), "image": (BytesIO(b"gif"), "cover.gif")},
                    content_type="multipart/form-data")
    assert resp.status_code == 200
    assert records[-1][1]["form"].image.errors
    assert _track(scratch, name) is None
    assert list(uploads.iterdir()) == []


def test_admin_create_luu_anh_that_bai_thi_khong_tao(app, scratch, monkeypatch):
    monkeypatch.setattr(hotel_routes, "save_uploaded_image",
                        lambda form, folder: (None, False))
    name = "Tmp Hotel New " + uuid4().hex[:8]
    admin, token = login(app, ADMIN)
    resp = post(admin, "/admin/hotels/new", token, data=_form(name))
    assert resp.status_code == 200
    assert _track(scratch, name) is None


def test_admin_create_trung_ten_thi_xoa_anh_vua_luu(app, scratch, uploads):
    info = scratch.hotel()
    admin, token = login(app, ADMIN)
    resp = post(admin, "/admin/hotels/new", token,
                data={**_form(info.hotel_name), "image": (BytesIO(b"fake"), "cover.png")},
                content_type="multipart/form-data")
    assert resp.status_code == 200
    assert list(uploads.iterdir()) == []


def test_admin_create_anh_phu(app, scratch, uploads):
    name = "Tmp Hotel New " + uuid4().hex[:8]
    folder = _hotel_dir(app, scratch, name)
    admin, token = login(app, ADMIN)
    resp = post(admin, "/admin/hotels/new", token, data={
        **_form(name),
        "extra_images": [(BytesIO(b"1"), "e1.png"), (BytesIO(b"2"), "e2.jpg"),
                         (BytesIO(b"3"), "bad.gif")],
    }, content_type="multipart/form-data", follow_redirects=True)
    _track(scratch, name)

    assert resp.status_code == 200
    assert len(os.listdir(folder)) == 2  # bad.gif bị bỏ qua
    assert "bad.gif" in _page(resp)       # có cảnh báo cho ảnh không hợp lệ


# ─── Admin: sửa ─────────────────────────────────────────────────────────────

def test_admin_edit_get_dien_san_form(app, scratch):
    info = scratch.hotel()
    amenity = scratch.amenity()
    db.session.get(Hotel, info.hotel_id).amenities = [db.session.get(Amenity, amenity.id)]
    db.session.commit()
    admin, _ = login(app, ADMIN)
    with captured(app) as records:
        resp = admin.get(f"/admin/hotels/{info.hotel_id}/edit")
    assert resp.status_code == 200
    ctx = records[-1][1]
    assert ctx["hotel"].id == info.hotel_id
    assert ctx["form"].name.data == info.hotel_name
    assert ctx["form"].amenity_ids.data == [amenity.id]


def test_admin_edit_khong_ton_tai_404(app):
    admin, token = login(app, ADMIN)
    assert admin.get("/admin/hotels/99999999/edit").status_code == 404
    assert post(admin, "/admin/hotels/99999999/edit", token, data=_form("X Y")).status_code == 404


def test_admin_edit_thanh_cong(app, scratch):
    info = scratch.hotel()
    amenity = scratch.amenity()
    admin, token = login(app, ADMIN)
    resp = post(admin, f"/admin/hotels/{info.hotel_id}/edit", token, data=_form(
        info.hotel_name, province="Huế", star_rating="5", description="Mới",
        amenity_ids=[str(amenity.id)]))
    assert resp.status_code == 302
    assert urlparse(resp.headers["Location"]).path == "/admin/hotels"
    db.session.expire_all()
    hotel = db.session.get(Hotel, info.hotel_id)
    assert (hotel.province, hotel.star_rating, hotel.description) == ("Huế", 5, "Mới")
    assert [a.id for a in hotel.amenities] == [amenity.id]


def test_admin_edit_bo_chon_het_tien_nghi(app, scratch):
    info = scratch.hotel()
    amenity = scratch.amenity()
    db.session.get(Hotel, info.hotel_id).amenities = [db.session.get(Amenity, amenity.id)]
    db.session.commit()
    admin, token = login(app, ADMIN)
    post(admin, f"/admin/hotels/{info.hotel_id}/edit", token, data=_form(info.hotel_name))
    db.session.expire_all()
    assert db.session.get(Hotel, info.hotel_id).amenities == []


def test_admin_edit_du_lieu_sai(app, scratch):
    info = scratch.hotel()
    admin, token = login(app, ADMIN)
    with captured(app) as records:
        resp = post(admin, f"/admin/hotels/{info.hotel_id}/edit", token,
                    data=_form(info.hotel_name, province="A"))
    assert resp.status_code == 200
    assert records[-1][1]["form"].province.errors
    db.session.expire_all()
    assert db.session.get(Hotel, info.hotel_id).province == "Hà Nội"


def test_admin_edit_trung_ten_khach_san_khac(app, scratch):
    a, b = scratch.hotel(), scratch.hotel()
    admin, token = login(app, ADMIN)
    with captured(app) as records:
        resp = post(admin, f"/admin/hotels/{b.hotel_id}/edit", token,
                    data=_form(a.hotel_name))
    assert resp.status_code == 200
    assert "Tên khách sạn đã tồn tại." in records[-1][1]["form"].name.errors
    db.session.expire_all()
    assert db.session.get(Hotel, b.hotel_id).name == b.hotel_name


def test_admin_edit_thay_anh_bia_xoa_anh_cu(app, scratch, uploads):
    info = scratch.hotel()
    (uploads / "old.jpg").write_bytes(b"x")
    db.session.get(Hotel, info.hotel_id).image_filename = "old.jpg"
    db.session.commit()
    admin, token = login(app, ADMIN)
    resp = post(admin, f"/admin/hotels/{info.hotel_id}/edit", token,
                data={**_form(info.hotel_name), "image": (BytesIO(b"new"), "new.png")},
                content_type="multipart/form-data")
    assert resp.status_code == 302
    db.session.expire_all()
    new_name = db.session.get(Hotel, info.hotel_id).image_filename
    assert new_name != "old.jpg" and new_name.endswith(".png")
    assert not (uploads / "old.jpg").exists()
    assert (uploads / new_name).exists()


def test_admin_edit_luu_anh_that_bai_thi_khong_doi_gi(app, scratch, monkeypatch):
    info = scratch.hotel()
    monkeypatch.setattr(hotel_routes, "save_uploaded_image",
                        lambda form, folder: (None, False))
    admin, token = login(app, ADMIN)
    resp = post(admin, f"/admin/hotels/{info.hotel_id}/edit", token,
                data=_form(info.hotel_name, province="Huế"))
    assert resp.status_code == 200
    db.session.expire_all()
    assert db.session.get(Hotel, info.hotel_id).province == "Hà Nội"


def test_admin_edit_them_anh_phu(app, scratch, uploads):
    info = scratch.hotel()
    folder = _hotel_dir(app, scratch, info.hotel_name)
    admin, token = login(app, ADMIN)
    resp = post(admin, f"/admin/hotels/{info.hotel_id}/edit", token,
                data={**_form(info.hotel_name), "extra_images": [(BytesIO(b"1"), "e1.png")]},
                content_type="multipart/form-data")
    assert resp.status_code == 302
    assert len(os.listdir(folder)) == 1


# ─── Admin: ẩn/hiện, xóa ────────────────────────────────────────────────────

def test_admin_toggle_an_roi_hien_lai(app, scratch):
    info = scratch.hotel()
    admin, token = login(app, ADMIN)
    url = f"/admin/hotels/{info.hotel_id}/toggle"

    resp = post(admin, url, token)
    assert resp.status_code == 302
    db.session.expire_all()
    assert db.session.get(Hotel, info.hotel_id).is_active is False

    post(admin, url, token)
    db.session.expire_all()
    assert db.session.get(Hotel, info.hotel_id).is_active is True


def test_admin_toggle_chi_nhan_post_va_404(app, scratch):
    info = scratch.hotel()
    admin, token = login(app, ADMIN)
    assert admin.get(f"/admin/hotels/{info.hotel_id}/toggle").status_code == 405
    assert post(admin, "/admin/hotels/99999999/toggle", token).status_code == 404


def test_admin_delete_xoa_ca_booking(app, scratch):
    info = scratch.hotel()
    code = make_booking(info.room_id, future(5), future(7), "Confirmed").code
    admin, token = login(app, ADMIN)
    resp = post(admin, f"/admin/hotels/{info.hotel_id}/delete", token, follow_redirects=True)
    assert resp.status_code == 200
    assert "Đã xóa khách sạn" in _page(resp)
    db.session.expire_all()
    assert db.session.get(Hotel, info.hotel_id) is None
    assert db.session.execute(select(Booking).filter_by(code=code)).scalar_one_or_none() is None


def test_admin_delete_chi_nhan_post_va_404(app, scratch):
    info = scratch.hotel()
    admin, token = login(app, ADMIN)
    assert admin.get(f"/admin/hotels/{info.hotel_id}/delete").status_code == 405
    assert post(admin, "/admin/hotels/99999999/delete", token).status_code == 404
    db.session.expire_all()
    assert db.session.get(Hotel, info.hotel_id) is not None


# ─── Admin: xóa ảnh phụ ─────────────────────────────────────────────────────

def _hotel_with_images(app, scratch):
    """Khách sạn có ảnh bìa cover.jpg và ảnh phụ extra.png trong thư mục riêng."""
    info = scratch.hotel()
    slug = slugify(info.hotel_name)
    folder = _hotel_dir(app, scratch, info.hotel_name)
    os.makedirs(folder)
    for filename in ("cover.jpg", "extra.png"):
        with open(os.path.join(folder, filename), "wb") as handle:
            handle.write(b"x")
    db.session.get(Hotel, info.hotel_id).image_filename = f"uploads/hotels/{slug}/cover.jpg"
    db.session.commit()
    return info, slug, folder


def _delete_image(app, info, filename):
    admin, token = login(app, ADMIN)
    return post(admin, f"/admin/hotels/{info.hotel_id}/delete-image", token,
                data={"filename": filename}, follow_redirects=True)


def test_xoa_anh_phu_thanh_cong(app, scratch):
    info, slug, folder = _hotel_with_images(app, scratch)
    resp = _delete_image(app, info, f"uploads/hotels/{slug}/extra.png")
    assert resp.status_code == 200
    assert "Đã xóa ảnh." in _page(resp)
    assert not os.path.exists(os.path.join(folder, "extra.png"))
    assert os.path.exists(os.path.join(folder, "cover.jpg"))


def test_xoa_anh_khong_gui_ten_file(app, scratch):
    info, _, folder = _hotel_with_images(app, scratch)
    resp = _delete_image(app, info, "")
    assert "Không tìm thấy tên file" in _page(resp)
    assert len(os.listdir(folder)) == 2


def test_khong_xoa_duoc_anh_bia(app, scratch):
    info, slug, folder = _hotel_with_images(app, scratch)
    resp = _delete_image(app, info, f"uploads/hotels/{slug}/cover.jpg")
    assert "Không thể xóa ảnh bìa" in _page(resp)
    assert os.path.exists(os.path.join(folder, "cover.jpg"))


def test_xoa_file_khong_ton_tai(app, scratch):
    info, slug, _ = _hotel_with_images(app, scratch)
    resp = _delete_image(app, info, f"uploads/hotels/{slug}/missing.png")
    assert "Không thể xóa ảnh." in _page(resp)


@pytest.mark.parametrize("template", [
    "uploads/hotels/{other}/sentinel.png",
    "uploads/hotels/{slug}/../{other}/sentinel.png",
])
def test_khong_xoa_duoc_file_ngoai_thu_muc_khach_san(app, scratch, template):
    info, slug, _ = _hotel_with_images(app, scratch)
    other = "tmp-other-" + uuid4().hex[:8]
    other_dir = os.path.join(app.static_folder, "uploads", "hotels", other)
    scratch.dirs.append(other_dir)
    os.makedirs(other_dir)
    sentinel = os.path.join(other_dir, "sentinel.png")
    with open(sentinel, "wb") as handle:
        handle.write(b"x")

    resp = _delete_image(app, info, template.format(slug=slug, other=other))
    assert "Không được xóa file ngoài thư mục khách sạn" in _page(resp)
    assert os.path.exists(sentinel)


def test_xoa_anh_khach_san_khong_ton_tai_404(app):
    admin, token = login(app, ADMIN)
    resp = post(admin, "/admin/hotels/99999999/delete-image", token,
                data={"filename": "uploads/x.png"})
    assert resp.status_code == 404  



# ---------------------------------------------------------------------------
# Ba test bổ sung: dòng 144, 241, 259 của hotels/routes.py
# ---------------------------------------------------------------------------

def test_save_extra_images_bo_qua_file_khong_co_ten(app, scratch, uploads):
    """Dòng 144: _save_extra_images bỏ qua FileStorage không có filename."""
    info = scratch.hotel()
    _hotel_dir(app, scratch, info.hotel_name)
    admin, token = login(app, ADMIN)
    resp = post(
        admin,
        f"/admin/hotels/{info.hotel_id}/edit",
        token,
        data={
            **_form(info.hotel_name),
            "extra_images": (BytesIO(b"data"), ""),  # filename rỗng
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    # Không crash; không có ảnh phụ nào được lưu
    assert resp.status_code == 200


def test_detail_gallery_anh_bia_tran_cong_anh_phu_trong_thu_muc(app, scratch):
    """Dòng 241: _get_hotel_gallery khi ảnh bìa tên trần mà thư mục KS có ảnh phụ."""
    info = scratch.hotel()
    slug = slugify(info.hotel_name)
    folder = _hotel_dir(app, scratch, info.hotel_name)
    os.makedirs(folder)
    # Ảnh bìa lưu tên trần (không có thư mục con)
    db.session.get(Hotel, info.hotel_id).image_filename = "bare-cover.jpg"
    db.session.commit()
    # Thêm ảnh phụ vào thư mục khách sạn
    with open(os.path.join(folder, "extra1.png"), "wb") as fh:
        fh.write(b"x")

    with captured(app) as records:
        resp = anon(app).get(f"/hotels/{info.hotel_id}")
    assert resp.status_code == 200
    # gallery phải chứa cả ảnh bìa tên trần lẫn ảnh phụ trong thư mục
    gallery = records[-1][1]["gallery"]
    assert "uploads/bare-cover.jpg" in gallery
    assert f"uploads/hotels/{slug}/extra1.png" in gallery


def test_xoa_anh_khi_anh_bia_la_ten_tran(app, scratch):
    """Dòng 259: admin_hotel_delete_image khi ảnh bìa là tên trần → cover = 'uploads/' + cover."""
    info = scratch.hotel()
    slug = slugify(info.hotel_name)
    folder = _hotel_dir(app, scratch, info.hotel_name)
    os.makedirs(folder)
    # Ảnh bìa tên trần; ảnh phụ nằm trong thư mục khách sạn
    with open(os.path.join(folder, "extra_del.png"), "wb") as fh:
        fh.write(b"x")
    db.session.get(Hotel, info.hotel_id).image_filename = "bare-cover2.jpg"
    db.session.commit()

    extra_rel = f"uploads/hotels/{slug}/extra_del.png"
    resp = _delete_image(app, info, extra_rel)
    assert resp.status_code == 200
    assert "Đã xóa ảnh." in _page(resp)
    assert not os.path.exists(os.path.join(folder, "extra_del.png"))