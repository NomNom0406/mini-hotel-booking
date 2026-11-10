import os
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.extensions import db
from app.models import Amenity, Room, RoomType
from app.rooms.routes import _get_room_type_gallery, _room_type_folder
from app.utils.security import slugify
from tests.conftest import _get_csrf
from tests.room_helpers import (  # noqa: F401  (fixture được import để pytest nhận ra)
    add_room,
    anon,
    clean_bookings,
    future,
    get_room,
    get_type,
    login,
    post,
    scratch,
)

ADMIN = "admin@test.com"
CUSTOMER = "customer@test.com"

ADMIN_GET_URLS = [
    "/admin/rooms", "/admin/rooms/new",
    "/admin/roomtypes", "/admin/roomtypes/new",
    "/admin/amenities", "/admin/amenities/new",
]


def _count(model, **filters):
    db.session.expire_all()
    return db.session.execute(
        select(func.count()).select_from(model).filter_by(**filters)).scalar_one()


def _room_form(info, number, floor="3", type_id=None, hotel_id=None):
    return {
        "hotel_id": str(hotel_id or info.hotel_id),
        "room_type_id": str(type_id or info.type_id),
        "room_number": number,
        "floor": floor,
    }


def _type_form(info, name, capacity="3", price="700000", amenity_ids=None, hotel_id=None):
    data = {
        "hotel_id": str(hotel_id or info.hotel_id),
        "name": name,
        "description": "Mô tả",
        "base_price": price,
        "capacity": capacity,
    }
    if amenity_ids:
        data["amenity_ids"] = [str(a) for a in amenity_ids]
    return data


# ─── Công khai: /rooms ──────────────────────────────────────────────────────

def test_rooms_index_without_valid_hotel_redirects(app):
    client = anon(app)
    assert client.get("/rooms").status_code == 302
    assert client.get("/rooms?hotel_id=abc").status_code == 302


def test_rooms_index_unknown_or_inactive_hotel_is_404(app, scratch):
    hidden = scratch.hotel(active=False)
    client = anon(app)
    assert client.get("/rooms?hotel_id=999999").status_code == 404
    assert client.get(f"/rooms?hotel_id={hidden.hotel_id}").status_code == 404


def test_rooms_index_renders_with_filters(app, scratch):
    info = scratch.hotel()
    client = anon(app)
    resp = client.get(f"/rooms?hotel_id={info.hotel_id}")
    assert resp.status_code == 200
    assert info.hotel_name in resp.get_data(as_text=True)

    query = (f"/rooms?hotel_id={info.hotel_id}&guests=2&price_min=100000&price_max=900000"
             f"&room_type_id={info.type_id}&page=1")
    assert client.get(query).status_code == 200
    assert client.get(f"/rooms?hotel_id={info.hotel_id}&guests=abc&page=abc").status_code == 200


def test_rooms_index_handles_dates(app, scratch):
    info = scratch.hotel()
    client = anon(app)
    past = (f"/rooms?hotel_id={info.hotel_id}&checkin={future(-5).isoformat()}"
            f"&checkout={future(-3).isoformat()}")
    assert client.get(past).status_code == 200  # ngày quá khứ bị bỏ, kèm cảnh báo
    good = (f"/rooms?hotel_id={info.hotel_id}&checkin={future(30).isoformat()}"
            f"&checkout={future(32).isoformat()}")
    assert client.get(good).status_code == 200
    assert client.get(f"/rooms?hotel_id={info.hotel_id}&checkin=abc&checkout=xyz").status_code == 200


def test_rooms_filter_post_without_hotel_is_400(app):
    client = anon(app)
    token = _get_csrf(client, "/auth/login")
    assert post(client, "/rooms/filter", token, {"guests": "1"}).status_code == 400


def test_rooms_filter_post_redirects_to_index_with_hotel(app, scratch):
    info = scratch.hotel()
    client = anon(app)
    token = _get_csrf(client, "/auth/login")
    resp = post(client, "/rooms/filter", token, {
        "hotel_id": str(info.hotel_id), "room_type_id": "", "price_min": "",
        "price_max": "", "checkin": "", "checkout": "", "guests": "1"})
    assert resp.status_code == 302
    assert "/rooms" in resp.headers["Location"]
    assert f"hotel_id={info.hotel_id}" in resp.headers["Location"]


def test_rooms_filter_post_with_only_one_date_drops_dates(app, scratch):
    info = scratch.hotel()
    client = anon(app)
    token = _get_csrf(client, "/auth/login")
    resp = post(client, "/rooms/filter", token, {
        "hotel_id": str(info.hotel_id), "checkin": future(30).isoformat(),
        "checkout": "", "guests": "1"})
    assert resp.status_code == 302
    assert f"hotel_id={info.hotel_id}" in resp.headers["Location"]
    assert "checkin=" not in resp.headers["Location"]


# ─── Công khai: /rooms/<id> ─────────────────────────────────────────────────

def test_room_detail_renders_and_handles_dates_and_guests(app, scratch):
    info = scratch.hotel()
    client = anon(app)
    assert client.get(f"/rooms/{info.room_id}").status_code == 200
    dates = f"checkin={future(30).isoformat()}&checkout={future(32).isoformat()}"
    assert client.get(f"/rooms/{info.room_id}?{dates}&guests=2").status_code == 200
    assert client.get(f"/rooms/{info.room_id}?{dates}&guests=9").status_code == 200  # quá sức chứa
    assert client.get(f"/rooms/{info.room_id}?guests=abc").status_code == 200


def test_room_detail_404_for_unknown_inactive_room_or_hidden_hotel(app, scratch):
    info = scratch.hotel()
    hidden_room = add_room(info, "T102", active=False)
    hidden_hotel = scratch.hotel(active=False)
    client = anon(app)
    assert client.get("/rooms/999999").status_code == 404
    assert client.get(f"/rooms/{hidden_room}").status_code == 404
    assert client.get(f"/rooms/{hidden_hotel.room_id}").status_code == 404


# ─── Phân quyền admin ───────────────────────────────────────────────────────

@pytest.mark.parametrize("url", ADMIN_GET_URLS)
def test_admin_pages_require_login(app, url):
    resp = anon(app).get(url)
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]


@pytest.mark.parametrize("url", ADMIN_GET_URLS)
def test_admin_pages_forbidden_for_customer(app, url):
    client, _ = login(app, CUSTOMER)
    assert client.get(url).status_code == 403


@pytest.mark.parametrize("url", ADMIN_GET_URLS)
def test_admin_pages_render_for_admin(app, url):
    client, _ = login(app, ADMIN)
    assert client.get(url).status_code == 200


def test_admin_post_actions_forbidden_for_customer(app, scratch):
    info = scratch.hotel()
    amenity = scratch.amenity()
    client, token = login(app, CUSTOMER)
    assert post(client, f"/admin/rooms/{info.room_id}/toggle", token).status_code == 403
    assert post(client, f"/admin/amenities/{amenity.id}/delete", token).status_code == 403
    assert post(client, "/admin/rooms/new", token,
                _room_form(info, "T777")).status_code == 403
    assert get_room(info.room_id).is_active is True
    assert _count(Room, hotel_id=info.hotel_id, room_number="T777") == 0


# ─── Admin: phòng ───────────────────────────────────────────────────────────

def test_admin_rooms_list_filters_and_pages(app, scratch):
    info = scratch.hotel()
    client, _ = login(app, ADMIN)
    resp = client.get(f"/admin/rooms?hotel_id={info.hotel_id}&page=1")
    assert resp.status_code == 200
    assert "T101" in resp.get_data(as_text=True)
    assert client.get("/admin/rooms?page=abc").status_code == 200


def test_admin_room_create_success(app, scratch):
    info = scratch.hotel()
    client, token = login(app, ADMIN)
    resp = post(client, "/admin/rooms/new", token, _room_form(info, "T300"))
    assert resp.status_code == 302
    assert f"hotel_id={info.hotel_id}" in resp.headers["Location"]
    db.session.expire_all()
    room = db.session.execute(select(Room).filter_by(
        hotel_id=info.hotel_id, room_number="T300")).scalar_one()
    assert room.floor == 3
    assert room.is_active is True


def test_admin_room_create_rejects_duplicate_number_and_foreign_type(app, scratch):
    info, other = scratch.hotel(), scratch.hotel()
    client, token = login(app, ADMIN)
    duplicate = post(client, "/admin/rooms/new", token, _room_form(info, "T101"))
    assert duplicate.status_code == 200  # hiện lại form kèm lỗi
    foreign = post(client, "/admin/rooms/new", token,
                   _room_form(info, "T888", type_id=other.type_id))
    assert foreign.status_code == 200
    assert _count(Room, hotel_id=info.hotel_id) == 1


def test_admin_room_edit_get_post_and_404(app, scratch):
    info = scratch.hotel()
    client, token = login(app, ADMIN)
    assert client.get(f"/admin/rooms/{info.room_id}/edit").status_code == 200
    assert client.get("/admin/rooms/999999/edit").status_code == 404

    resp = post(client, f"/admin/rooms/{info.room_id}/edit", token,
                _room_form(info, "T101", floor="4"))
    assert resp.status_code == 302
    assert get_room(info.room_id).floor == 4

    second = add_room(info, "T102")
    clash = post(client, f"/admin/rooms/{second}/edit", token, _room_form(info, "T101"))
    assert clash.status_code == 200
    assert get_room(second).room_number == "T102"


def test_admin_room_toggle_hides_then_shows_and_404(app, scratch):
    info = scratch.hotel()
    client, token = login(app, ADMIN)
    assert post(client, f"/admin/rooms/{info.room_id}/toggle", token).status_code == 302
    assert get_room(info.room_id).is_active is False
    assert post(client, f"/admin/rooms/{info.room_id}/toggle", token).status_code == 302
    assert get_room(info.room_id).is_active is True
    assert post(client, "/admin/rooms/999999/toggle", token).status_code == 404


# ─── Admin: loại phòng ──────────────────────────────────────────────────────

def test_admin_types_list_filters_by_hotel(app, scratch):
    info = scratch.hotel()
    client, _ = login(app, ADMIN)
    resp = client.get(f"/admin/roomtypes?hotel_id={info.hotel_id}")
    assert resp.status_code == 200
    assert "Tmp Type" in resp.get_data(as_text=True)


def test_admin_type_create_success_with_amenity(app, scratch):
    info = scratch.hotel(with_type=False)
    amenity = scratch.amenity()
    client, token = login(app, ADMIN)
    resp = post(client, "/admin/roomtypes/new", token,
                _type_form(info, "Loại Mới", amenity_ids=[amenity.id]))
    assert resp.status_code == 302
    assert f"hotel_id={info.hotel_id}" in resp.headers["Location"]
    db.session.expire_all()
    room_type = db.session.execute(select(RoomType).filter_by(
        hotel_id=info.hotel_id, name="Loại Mới")).scalar_one()
    assert room_type.capacity == 3
    assert [a.name for a in room_type.amenities] == [amenity.name]


def test_admin_type_create_rejects_duplicate_name(app, scratch):
    info = scratch.hotel()
    client, token = login(app, ADMIN)
    resp = post(client, "/admin/roomtypes/new", token, _type_form(info, "Tmp Type"))
    assert resp.status_code == 200
    assert _count(RoomType, hotel_id=info.hotel_id) == 1


def test_admin_type_edit_get_post_and_404(app, scratch):
    info = scratch.hotel()
    client, token = login(app, ADMIN)
    assert client.get(f"/admin/roomtypes/{info.type_id}/edit").status_code == 200
    assert client.get("/admin/roomtypes/999999/edit").status_code == 404

    resp = post(client, f"/admin/roomtypes/{info.type_id}/edit", token,
                _type_form(info, "Tmp Type Đổi", capacity="4", price="800000"))
    assert resp.status_code == 302
    done = get_type(info.type_id)
    assert done.name == "Tmp Type Đổi"
    assert done.capacity == 4

    clash = post(client, f"/admin/roomtypes/{info.type_id}/edit", token,
                 _type_form(info, "Tmp Type Đổi", capacity="4", price="800000"))
    assert clash.status_code == 302  # giữ nguyên tên của chính nó thì hợp lệ


# ─── Hàm phụ về thư mục ảnh ─────────────────────────────────────────────────

def _set_cover(type_id, cover):
    room_type = db.session.get(RoomType, type_id)
    room_type.image_filename = cover
    db.session.commit()
    return get_type(type_id)


def test_room_type_folder_uses_cover_folder_or_slug_default(app, scratch):
    info = scratch.hotel()
    default = f"uploads/rooms/{slugify(info.hotel_name)}/{slugify('Tmp Type')}"

    assert _room_type_folder(_set_cover(info.type_id, None)) == default
    assert _room_type_folder(_set_cover(info.type_id, "abc.jpg")) == default
    assert _room_type_folder(_set_cover(info.type_id, "uploads/abc.jpg")) == default
    assert _room_type_folder(
        _set_cover(info.type_id, "uploads/rooms/x/y/cover.jpg")) == "uploads/rooms/x/y"
    assert _room_type_folder(
        _set_cover(info.type_id, "rooms/x/y/cover.jpg")) == "uploads/rooms/x/y"


def _make_type_folder(scratch, info, names=("cover.jpg", "b.png", "a.webp", "notes.txt")):
    """Tạo thư mục ảnh thật của loại phòng; trả về (đường dẫn tương đối, đường dẫn tuyệt đối)."""
    from flask import current_app
    room_type = get_type(info.type_id)
    rel = _room_type_folder(room_type)
    static_root = os.path.abspath(current_app.static_folder)
    abs_dir = os.path.join(static_root, rel)
    os.makedirs(abs_dir, exist_ok=True)
    hotel_dir = os.path.join(static_root, "uploads", "rooms", rel.split("/")[2])
    scratch.dirs.append(hotel_dir)
    for name in names:
        with open(os.path.join(abs_dir, name), "w", encoding="utf-8") as handle:
            handle.write("x")
    return rel, abs_dir


def test_get_room_type_gallery_orders_cover_first_and_skips_non_images(app, scratch):
    info = scratch.hotel()
    assert _get_room_type_gallery(None) == []
    assert _get_room_type_gallery(get_type(info.type_id)) == []  # chưa có ảnh bìa

    rel, _ = _make_type_folder(scratch, info)
    room_type = _set_cover(info.type_id, f"{rel}/cover.jpg")
    assert _get_room_type_gallery(room_type) == [
        f"{rel}/cover.jpg", f"{rel}/a.webp", f"{rel}/b.png"]


def test_admin_type_edit_page_with_gallery_renders(app, scratch):
    info = scratch.hotel()
    rel, _ = _make_type_folder(scratch, info)
    _set_cover(info.type_id, f"{rel}/cover.jpg")
    client, _ = login(app, ADMIN)
    assert client.get(f"/admin/roomtypes/{info.type_id}/edit").status_code == 200


# ─── Xóa ảnh phụ của loại phòng ─────────────────────────────────────────────

def test_admin_type_delete_image_removes_extra_file(app, scratch):
    info = scratch.hotel()
    rel, abs_dir = _make_type_folder(scratch, info)
    _set_cover(info.type_id, f"{rel}/cover.jpg")
    client, token = login(app, ADMIN)
    resp = post(client, f"/admin/roomtypes/{info.type_id}/delete-image", token,
                {"filename": f"{rel}/b.png"})
    assert resp.status_code == 302
    assert not os.path.exists(os.path.join(abs_dir, "b.png"))
    assert os.path.exists(os.path.join(abs_dir, "a.webp"))


def test_admin_type_delete_image_protects_cover_and_outside_files(app, scratch):
    info = scratch.hotel()
    rel, abs_dir = _make_type_folder(scratch, info)
    _set_cover(info.type_id, f"{rel}/cover.jpg")
    outside_dir = os.path.dirname(abs_dir)  # uploads/rooms/<hotel>: ngoài thư mục loại phòng
    outside_file = os.path.join(outside_dir, "outside.jpg")
    with open(outside_file, "w", encoding="utf-8") as handle:
        handle.write("x")
    hotel_slug = rel.split("/")[2]

    client, token = login(app, ADMIN)
    url = f"/admin/roomtypes/{info.type_id}/delete-image"
    cover = post(client, url, token, {"filename": f"{rel}/cover.jpg"})
    assert cover.status_code == 302
    assert os.path.exists(os.path.join(abs_dir, "cover.jpg"))

    outside = post(client, url, token,
                   {"filename": f"uploads/rooms/{hotel_slug}/outside.jpg"})
    assert outside.status_code == 302
    assert os.path.exists(outside_file)


def test_admin_type_delete_image_missing_or_nonexistent_file(app, scratch):
    info = scratch.hotel()
    rel, _ = _make_type_folder(scratch, info)
    client, token = login(app, ADMIN)
    url = f"/admin/roomtypes/{info.type_id}/delete-image"
    assert post(client, url, token, {"filename": ""}).status_code == 302
    assert post(client, url, token, {"filename": f"{rel}/khong-co.png"}).status_code == 302
    assert post(client, "/admin/roomtypes/999999/delete-image", token,
                {"filename": "x"}).status_code == 404


# ─── Admin: tiện nghi ───────────────────────────────────────────────────────

def test_admin_amenity_create_success_and_duplicate(app, scratch):
    name = "Tạm " + uuid4().hex[:8]
    client, token = login(app, ADMIN)
    resp = post(client, "/admin/amenities/new", token, {"name": name, "icon": "bi-star"})
    assert resp.status_code == 302
    db.session.expire_all()
    amenity = db.session.execute(select(Amenity).filter_by(name=name)).scalar_one()
    scratch.amenity_ids.append(amenity.id)

    again = post(client, "/admin/amenities/new", token, {"name": name, "icon": "bi-star"})
    assert again.status_code == 200
    assert _count(Amenity, name=name) == 1


def test_admin_amenity_edit_get_post_duplicate_and_404(app, scratch):
    first, second = scratch.amenity(), scratch.amenity()
    client, token = login(app, ADMIN)
    assert client.get(f"/admin/amenities/{first.id}/edit").status_code == 200
    assert client.get("/admin/amenities/999999/edit").status_code == 404

    new_name = "Tạm " + uuid4().hex[:8]
    resp = post(client, f"/admin/amenities/{first.id}/edit", token,
                {"name": new_name, "icon": "bi-wifi"})
    assert resp.status_code == 302
    db.session.expire_all()
    assert db.session.get(Amenity, first.id).name == new_name

    clash = post(client, f"/admin/amenities/{first.id}/edit", token,
                 {"name": second.name, "icon": "bi-wifi"})
    assert clash.status_code == 200
    db.session.expire_all()
    assert db.session.get(Amenity, first.id).name == new_name


def test_admin_amenity_delete_and_404(app, scratch):
    amenity = scratch.amenity()
    client, token = login(app, ADMIN)
    resp = post(client, f"/admin/amenities/{amenity.id}/delete", token)
    assert resp.status_code == 302
    db.session.expire_all()
    assert db.session.get(Amenity, amenity.id) is None
    assert post(client, "/admin/amenities/999999/delete", token).status_code == 404