"""Test cho các hàm cần DB trong app/hotels/services.py:
tìm kiếm, gom phòng theo loại, danh sách admin, tạo/sửa/ẩn/xóa khách sạn.

Dữ liệu tạm dùng fixture `scratch` của tests/room_helpers.py; mỗi nhóm khách sạn trong
một test được gán một tỉnh riêng để kết quả không lẫn với dữ liệu khác trong DB test.
"""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from werkzeug.datastructures import MultiDict

from app.extensions import db
from app.hotels import services as hs
from app.hotels.services import (
    HotelNameTaken, create_hotel, delete_hotel, get_amenity_choices,
    get_hotel_room_groups, get_provinces, list_hotels_admin, parse_search_args,
    search_hotels_page, set_hotel_active, update_hotel,
)
from app.models import (
    Amenity, Booking, Hotel, Room, RoomType, hotel_amenities, room_type_amenities,
)
from tests.room_helpers import (  # noqa: F401  (clean_bookings là fixture autouse)
    add_room, clean_bookings, future, get_room, make_booking, scratch,
)


@pytest.fixture
def uploads(app, tmp_path, monkeypatch):
    """Trỏ thư mục upload sang thư mục tạm để test không đụng ảnh thật."""
    monkeypatch.setitem(app.config, "UPLOAD_FOLDER", str(tmp_path))
    return tmp_path


# ─── Helper ─────────────────────────────────────────────────────────────────

def _isolate(*infos):
    """Gán cùng một tỉnh duy nhất cho các khách sạn tạm, trả về tên tỉnh."""
    province = "Tinh " + uuid4().hex[:8]
    for info in infos:
        db.session.get(Hotel, info.hotel_id).province = province
    db.session.commit()
    return province


def _set_stars(info, stars):
    db.session.get(Hotel, info.hotel_id).star_rating = stars
    db.session.commit()


def _add_type(info, name, price, capacity=2):
    room_type = RoomType(hotel_id=info.hotel_id, name=name, base_price=price,
                         capacity=capacity, description="loại tạm")
    db.session.add(room_type)
    db.session.commit()
    return room_type.id


def _add_room_of_type(info, type_id, number):
    room = Room(hotel_id=info.hotel_id, room_type_id=type_id,
                room_number=number, floor=1, is_active=True)
    db.session.add(room)
    db.session.commit()
    return room.id


def _search(province, per_page=9, **extra):
    raw = {"province": province}
    for key, value in extra.items():
        raw[key] = value if isinstance(value, list) else str(value)
    params, errors = parse_search_args(MultiDict(raw))
    assert errors == {}
    return search_hotels_page(params, per_page=per_page)


def _ids(pagination):
    return [h.id for h in pagination.items]


def _data(name, **overrides):
    data = {"name": name, "province": "Cần Thơ", "address": "1 Đường A",
            "star_rating": 4, "description": "Mô tả", "map_url": ""}
    data.update(overrides)
    return data


def _count_by_name(name):
    return db.session.execute(
        select(func.count()).select_from(Hotel).where(Hotel.name == name)
    ).scalar_one()


def _boom(*args, **kwargs):
    raise RuntimeError("boom")


# ─── search_hotels_page ─────────────────────────────────────────────────────

def test_search_tra_khach_san_co_phong_va_gia_tu(scratch):
    info = scratch.hotel(price=450000)
    province = _isolate(info)
    pagination, prices = _search(province)
    assert _ids(pagination) == [info.hotel_id]
    assert pagination.total == 1
    assert prices[info.hotel_id] == 450000


def test_search_chi_giu_khach_san_hop_le(scratch):
    ok = scratch.hotel()
    hidden = scratch.hotel(active=False)
    no_room = scratch.hotel(with_room=False)
    no_type = scratch.hotel(with_type=False)
    inactive_room = scratch.hotel()
    room = get_room(inactive_room.room_id)
    room.is_active = False
    db.session.commit()
    province = _isolate(ok, hidden, no_room, no_type, inactive_room)
    pagination, _ = _search(province)
    assert _ids(pagination) == [ok.hotel_id]


def test_search_khong_co_ket_qua(scratch):
    pagination, prices = _search("Tinh " + uuid4().hex[:8])
    assert pagination.items == []
    assert pagination.total == 0
    assert prices == {}


def test_search_loc_tinh_chinh_xac(scratch):
    info = scratch.hotel()
    _isolate(info)
    pagination, _ = _search("Tinh " + uuid4().hex[:8])
    assert pagination.total == 0


def test_search_loc_suc_chua(scratch):
    info = scratch.hotel(capacity=2)
    province = _isolate(info)
    assert _search(province, guests=2)[0].total == 1
    assert _search(province, guests=3)[0].total == 0


def test_search_loc_khoang_gia_va_gia_tu_la_phong_re_nhat_hop_le(scratch):
    info = scratch.hotel(price=500000)
    cheap_id = _add_type(info, "Cheap", 300000)
    _add_room_of_type(info, cheap_id, "C101")
    province = _isolate(info)

    assert _search(province)[1][info.hotel_id] == 300000
    assert _search(province, min_price=400000)[1][info.hotel_id] == 500000
    assert _search(province, max_price=400000)[1][info.hotel_id] == 300000
    assert _search(province, min_price=600000)[0].total == 0
    assert _search(province, max_price=100000)[0].total == 0


def test_search_loc_hang_sao_tu_n_tro_len(scratch):
    info = scratch.hotel()
    _set_stars(info, 3)
    province = _isolate(info)
    assert _search(province, stars=3)[0].total == 1
    assert _search(province, stars=2)[0].total == 1
    assert _search(province, stars=4)[0].total == 0


def test_search_loc_tien_nghi_phai_co_du_moi_tien_nghi_da_chon(scratch):
    info = scratch.hotel()
    province = _isolate(info)
    a1, a2 = scratch.amenity(), scratch.amenity()
    db.session.get(Hotel, info.hotel_id).amenities = [db.session.get(Amenity, a1.id)]
    db.session.commit()

    assert _search(province, amenity=[str(a1.id)])[0].total == 1
    assert _search(province, amenity=[str(a2.id)])[0].total == 0
    assert _search(province, amenity=[str(a1.id), str(a2.id)])[0].total == 0


def test_search_khong_nhan_doi_khi_co_nhieu_phong(scratch):
    info = scratch.hotel()
    add_room(info, "T102")
    add_room(info, "T103")
    province = _isolate(info)
    pagination, _ = _search(province)
    assert _ids(pagination) == [info.hotel_id]


@pytest.mark.parametrize("status,expected", [
    ("Pending", 0), ("Confirmed", 0), ("Cancelled", 1), ("Completed", 1),
])
def test_search_theo_trang_thai_booking(scratch, status, expected):
    info = scratch.hotel()
    province = _isolate(info)
    ci, co = future(10), future(12)
    make_booking(info.room_id, ci, co, status)
    pagination, _ = _search(province, checkin=ci.isoformat(), checkout=co.isoformat())
    assert pagination.total == expected


@pytest.mark.parametrize("start,end,expected", [
    (8, 10, 1),    # kết thúc đúng ngày nhận: không chồng
    (12, 14, 1),   # bắt đầu đúng ngày trả: không chồng
    (9, 11, 0),    # chồng đầu
    (11, 13, 0),   # chồng cuối
    (10, 12, 0),   # trùng hẳn
    (9, 13, 0),    # bao trùm
    (10, 11, 0),   # nằm trong
])
def test_search_ranh_gioi_ngay(scratch, start, end, expected):
    info = scratch.hotel()
    province = _isolate(info)
    make_booking(info.room_id, future(start), future(end), "Confirmed")
    pagination, _ = _search(province, checkin=future(10).isoformat(),
                            checkout=future(12).isoformat())
    assert pagination.total == expected


def test_search_con_phong_khac_trong_thi_khach_san_van_hien(scratch):
    info = scratch.hotel()
    add_room(info, "T102")
    province = _isolate(info)
    make_booking(info.room_id, future(10), future(12), "Pending")
    pagination, _ = _search(province, checkin=future(10).isoformat(),
                            checkout=future(12).isoformat())
    assert _ids(pagination) == [info.hotel_id]


def test_search_gia_tu_chi_tinh_phong_con_trong(scratch):
    info = scratch.hotel(price=500000)
    cheap_id = _add_type(info, "Cheap", 300000)
    cheap_room = _add_room_of_type(info, cheap_id, "C101")
    province = _isolate(info)
    dates = dict(checkin=future(10).isoformat(), checkout=future(12).isoformat())

    assert _search(province, **dates)[1][info.hotel_id] == 300000
    make_booking(cheap_room, future(10), future(12), "Pending")
    assert _search(province, **dates)[1][info.hotel_id] == 500000


def test_search_sap_xep(scratch):
    h1 = scratch.hotel(price=300000)
    h2 = scratch.hotel(price=700000)
    h3 = scratch.hotel(price=500000)
    _set_stars(h1, 3)
    _set_stars(h2, 4)
    _set_stars(h3, 5)
    province = _isolate(h1, h2, h3)

    assert _ids(_search(province, sort="stars_desc")[0]) == [h3.hotel_id, h2.hotel_id, h1.hotel_id]
    assert _ids(_search(province, sort="price_asc")[0]) == [h1.hotel_id, h3.hotel_id, h2.hotel_id]
    assert _ids(_search(province, sort="price_desc")[0]) == [h2.hotel_id, h3.hotel_id, h1.hotel_id]
    # mặc định = stars_desc
    assert _ids(_search(province)[0]) == [h3.hotel_id, h2.hotel_id, h1.hotel_id]


def test_search_phan_trang(scratch):
    infos = [scratch.hotel(price=300000 + i * 100000) for i in range(3)]
    province = _isolate(*infos)

    page1, prices1 = _search(province, per_page=2, sort="price_asc")
    assert page1.total == 3 and page1.pages == 2
    assert _ids(page1) == [infos[0].hotel_id, infos[1].hotel_id]
    assert set(prices1) == {infos[0].hotel_id, infos[1].hotel_id}

    page2, prices2 = _search(province, per_page=2, sort="price_asc", page=2)
    assert _ids(page2) == [infos[2].hotel_id]
    assert set(prices2) == {infos[2].hotel_id}

    page9, prices9 = _search(province, per_page=2, page=9)
    assert page9.items == [] and prices9 == {}


# ─── get_provinces ──────────────────────────────────────────────────────────

def test_get_provinces_co_tinh_va_khong_trung(scratch):
    h1, h2 = scratch.hotel(), scratch.hotel()
    province = _isolate(h1, h2)
    provinces = get_provinces()
    assert provinces.count(province) == 1
    assert len(provinces) == len(set(provinces))


# ─── get_hotel_room_groups ──────────────────────────────────────────────────

def _hotel_two_types(scratch):
    """Loại 'Tmp Type' 500k (T101, T102) và loại 'Cheap' 300k, sức chứa 4 (B101)."""
    info = scratch.hotel(price=500000, capacity=2)
    t102 = add_room(info, "T102")
    cheap_id = _add_type(info, "Cheap", 300000, capacity=4)
    b101 = _add_room_of_type(info, cheap_id, "B101")
    return info, t102, b101


def test_groups_khong_co_phong(scratch):
    info = scratch.hotel(with_room=False)
    assert get_hotel_room_groups(info.hotel_id) == []


def test_groups_khong_ngay_gom_theo_loai_xep_theo_gia(scratch):
    info, _, _ = _hotel_two_types(scratch)
    groups = get_hotel_room_groups(info.hotel_id)
    assert [g["type"].name for g in groups] == ["Cheap", "Tmp Type"]
    assert [r.room_number for r in groups[0]["rooms"]] == ["B101"]
    assert [r.room_number for r in groups[1]["rooms"]] == ["T101", "T102"]
    assert all(g["nights"] is None and g["total"] is None for g in groups)


def test_groups_bo_phong_khong_hoat_dong(scratch):
    info, t102, _ = _hotel_two_types(scratch)
    room = get_room(t102)
    room.is_active = False
    db.session.commit()
    groups = get_hotel_room_groups(info.hotel_id)
    tmp = next(g for g in groups if g["type"].name == "Tmp Type")
    assert [r.room_number for r in tmp["rooms"]] == ["T101"]


def test_groups_co_ngay_tinh_so_dem_va_tong_tien(scratch):
    info, _, _ = _hotel_two_types(scratch)
    groups = get_hotel_room_groups(info.hotel_id, future(10).isoformat(),
                                   future(12).isoformat())
    assert [g["nights"] for g in groups] == [2, 2]
    assert [g["total"] for g in groups] == [600000, 1000000]


def test_groups_co_ngay_loai_phong_da_dat(scratch):
    info, t102, _ = _hotel_two_types(scratch)
    ci, co = future(10), future(12)
    dates = (ci.isoformat(), co.isoformat())

    make_booking(info.room_id, ci, co, "Pending")
    groups = get_hotel_room_groups(info.hotel_id, *dates)
    tmp = next(g for g in groups if g["type"].name == "Tmp Type")
    assert [r.room_number for r in tmp["rooms"]] == ["T102"]

    make_booking(t102, ci, co, "Confirmed")
    groups = get_hotel_room_groups(info.hotel_id, *dates)
    assert [g["type"].name for g in groups] == ["Cheap"]


def test_groups_booking_da_huy_khong_giu_phong(scratch):
    info = scratch.hotel()
    make_booking(info.room_id, future(10), future(12), "Cancelled")
    groups = get_hotel_room_groups(info.hotel_id, future(10).isoformat(),
                                   future(12).isoformat())
    assert len(groups) == 1


def test_groups_co_ngay_loc_suc_chua(scratch):
    info, _, _ = _hotel_two_types(scratch)
    dates = (future(10).isoformat(), future(12).isoformat())
    groups = get_hotel_room_groups(info.hotel_id, *dates, guests=3)
    assert [g["type"].name for g in groups] == ["Cheap"]
    assert get_hotel_room_groups(info.hotel_id, *dates, guests=5) == []


def test_groups_ngay_sai_xu_ly_nhu_khong_co_ngay(scratch):
    info = scratch.hotel()
    groups = get_hotel_room_groups(info.hotel_id, future(12).isoformat(),
                                   future(10).isoformat())
    assert len(groups) == 1
    assert groups[0]["nights"] is None and groups[0]["total"] is None


# ─── list_hotels_admin, get_amenity_choices ─────────────────────────────────

def test_list_hotels_admin_gom_ca_khach_san_an_va_dem_phong(scratch):
    active = scratch.hotel()
    hidden = scratch.hotel(active=False)
    empty = scratch.hotel(with_room=False)
    add_room(active, "T102")

    hotels, counts = list_hotels_admin()
    ids = {h.id for h in hotels}
    assert {active.hotel_id, hidden.hotel_id, empty.hotel_id} <= ids
    assert counts[active.hotel_id] == 2
    assert counts[hidden.hotel_id] == 1
    assert empty.hotel_id not in counts


def test_get_amenity_choices(scratch):
    amenity = scratch.amenity()
    choices = get_amenity_choices()
    assert (amenity.id, amenity.name) in choices


# ─── create_hotel ───────────────────────────────────────────────────────────

def test_create_hotel_luu_du_lieu_va_cat_khoang_trang(scratch):
    amenity = scratch.amenity()
    name = "Tmp Hotel New " + uuid4().hex[:8]
    hotel = create_hotel(
        _data("  " + name + "  ", province="  Cần Thơ ", address=" 1 Đường A ",
              description="   ", map_url=""),
        [amenity.id], image_filename="cover.jpg",
    )
    scratch.hotel_ids.append(hotel.id)

    assert hotel.id is not None
    assert hotel.name == name
    assert hotel.province == "Cần Thơ"
    assert hotel.address == "1 Đường A"
    assert hotel.star_rating == 4
    assert hotel.description is None
    assert hotel.map_url is None
    assert hotel.is_active is True
    assert hotel.image_filename == "cover.jpg"
    assert [a.id for a in hotel.amenities] == [amenity.id]


def test_create_hotel_bo_qua_tien_nghi_khong_ton_tai(scratch):
    name = "Tmp Hotel New " + uuid4().hex[:8]
    hotel = create_hotel(_data(name), [999999])
    scratch.hotel_ids.append(hotel.id)
    assert hotel.amenities == []


def test_create_hotel_trung_ten(scratch):
    info = scratch.hotel()
    with pytest.raises(HotelNameTaken):
        create_hotel(_data(info.hotel_name), [])
    with pytest.raises(HotelNameTaken):
        create_hotel(_data("  " + info.hotel_name + "  "), [])
    assert _count_by_name(info.hotel_name) == 1


def test_create_hotel_integrity_error_doi_thanh_hotel_name_taken(scratch, monkeypatch):
    info = scratch.hotel()
    monkeypatch.setattr(hs, "_name_taken", lambda *a, **k: False)
    with pytest.raises(HotelNameTaken):
        create_hotel(_data(info.hotel_name), [])
    monkeypatch.undo()
    assert _count_by_name(info.hotel_name) == 1
    assert db.session.get(Hotel, info.hotel_id) is not None  # session còn dùng được


def test_create_hotel_loi_bat_ngo_rollback(scratch, monkeypatch):
    name = "Tmp Hotel New " + uuid4().hex[:8]
    monkeypatch.setattr(hs, "_apply", _boom)
    with pytest.raises(RuntimeError):
        create_hotel(_data(name), [])
    monkeypatch.undo()
    assert _count_by_name(name) == 0


# ─── update_hotel ───────────────────────────────────────────────────────────

def test_update_hotel_doi_thong_tin_va_tien_nghi(scratch):
    info = scratch.hotel()
    a1, a2 = scratch.amenity(), scratch.amenity()
    hotel = db.session.get(Hotel, info.hotel_id)

    update_hotel(hotel, _data(info.hotel_name, province="Huế", star_rating=5,
                              description="Mới", map_url="https://maps.google.com/x"),
                 [a1.id, a2.id])
    db.session.expire_all()
    hotel = db.session.get(Hotel, info.hotel_id)
    assert hotel.province == "Huế"
    assert hotel.star_rating == 5
    assert hotel.description == "Mới"
    assert hotel.map_url == "https://maps.google.com/x"
    assert {a.id for a in hotel.amenities} == {a1.id, a2.id}

    update_hotel(hotel, _data(info.hotel_name), [])
    db.session.expire_all()
    assert db.session.get(Hotel, info.hotel_id).amenities == []


def test_update_hotel_giu_nguyen_ten_cua_chinh_no(scratch):
    info = scratch.hotel()
    hotel = db.session.get(Hotel, info.hotel_id)
    update_hotel(hotel, _data(info.hotel_name), [])
    assert hotel.name == info.hotel_name


def test_update_hotel_trung_ten_khach_san_khac(scratch):
    a, b = scratch.hotel(), scratch.hotel()
    hotel = db.session.get(Hotel, b.hotel_id)
    with pytest.raises(HotelNameTaken):
        update_hotel(hotel, _data(a.hotel_name), [])
    db.session.expire_all()
    assert db.session.get(Hotel, b.hotel_id).name == b.hotel_name


def test_update_hotel_integrity_error(scratch, monkeypatch):
    a, b = scratch.hotel(), scratch.hotel()
    hotel = db.session.get(Hotel, b.hotel_id)
    monkeypatch.setattr(hs, "_name_taken", lambda *a, **k: False)
    with pytest.raises(HotelNameTaken):
        update_hotel(hotel, _data(a.hotel_name), [])
    monkeypatch.undo()
    db.session.expire_all()
    assert db.session.get(Hotel, b.hotel_id).name == b.hotel_name


def test_update_hotel_loi_bat_ngo_rollback(scratch, monkeypatch):
    info = scratch.hotel()
    hotel = db.session.get(Hotel, info.hotel_id)
    monkeypatch.setattr(hs, "_apply", _boom)
    with pytest.raises(RuntimeError):
        update_hotel(hotel, _data(info.hotel_name, province="Huế"), [])
    monkeypatch.undo()
    db.session.expire_all()
    assert db.session.get(Hotel, info.hotel_id).province == "Hà Nội"


def test_update_hotel_thay_anh_xoa_anh_cu(scratch, uploads):
    info = scratch.hotel()
    (uploads / "old.jpg").write_bytes(b"x")
    hotel = db.session.get(Hotel, info.hotel_id)
    hotel.image_filename = "old.jpg"
    db.session.commit()

    update_hotel(hotel, _data(info.hotel_name), [], image_filename="new.jpg")
    assert hotel.image_filename == "new.jpg"
    assert not (uploads / "old.jpg").exists()


def test_update_hotel_khong_co_anh_moi_giu_anh_cu(scratch, uploads):
    info = scratch.hotel()
    (uploads / "old.jpg").write_bytes(b"x")
    hotel = db.session.get(Hotel, info.hotel_id)
    hotel.image_filename = "old.jpg"
    db.session.commit()

    update_hotel(hotel, _data(info.hotel_name), [])
    assert hotel.image_filename == "old.jpg"
    assert (uploads / "old.jpg").exists()


def test_update_hotel_cung_ten_anh_khong_xoa(scratch, uploads):
    info = scratch.hotel()
    (uploads / "same.jpg").write_bytes(b"x")
    hotel = db.session.get(Hotel, info.hotel_id)
    hotel.image_filename = "same.jpg"
    db.session.commit()

    update_hotel(hotel, _data(info.hotel_name), [], image_filename="same.jpg")
    assert (uploads / "same.jpg").exists()


# ─── set_hotel_active ───────────────────────────────────────────────────────

def test_set_hotel_active_an_va_hien(scratch):
    info = scratch.hotel()
    hotel = db.session.get(Hotel, info.hotel_id)
    set_hotel_active(hotel, False)
    db.session.expire_all()
    assert db.session.get(Hotel, info.hotel_id).is_active is False
    set_hotel_active(db.session.get(Hotel, info.hotel_id), True)
    db.session.expire_all()
    assert db.session.get(Hotel, info.hotel_id).is_active is True


def test_set_hotel_active_loi_thi_rollback(scratch):
    info = scratch.hotel()
    hotel = db.session.get(Hotel, info.hotel_id)
    with pytest.MonkeyPatch.context() as m:
        m.setattr(db.session, "commit", _boom)
        with pytest.raises(RuntimeError):
            set_hotel_active(hotel, False)
    db.session.expire_all()
    assert db.session.get(Hotel, info.hotel_id).is_active is True


# ─── delete_hotel ───────────────────────────────────────────────────────────

def _full_hotel(scratch, uploads):
    """Khách sạn tạm có tiện nghi, ảnh, booking; kèm một khách sạn khác không bị đụng tới."""
    target, other = scratch.hotel(), scratch.hotel()
    amenity = scratch.amenity()
    hotel = db.session.get(Hotel, target.hotel_id)
    room_type = db.session.get(RoomType, target.type_id)
    amenity_row = db.session.get(Amenity, amenity.id)
    hotel.amenities = [amenity_row]
    room_type.amenities = [amenity_row]
    hotel.image_filename = "hotel-cover.jpg"
    room_type.image_filename = "uploads/hotels/x/type-cover.jpg"  # có thư mục con: không bị xóa
    db.session.commit()
    (uploads / "hotel-cover.jpg").write_bytes(b"x")
    nested = uploads / "uploads" / "hotels" / "x"
    nested.mkdir(parents=True)
    (nested / "type-cover.jpg").write_bytes(b"x")
    return target, other, amenity


def test_delete_hotel_xoa_het_du_lieu_lien_quan(scratch, uploads):
    target, other, amenity = _full_hotel(scratch, uploads)
    code = make_booking(target.room_id, future(5), future(7), "Confirmed").code
    hotel = db.session.get(Hotel, target.hotel_id)

    delete_hotel(hotel)
    db.session.expire_all()

    assert db.session.get(Hotel, target.hotel_id) is None
    assert db.session.get(RoomType, target.type_id) is None
    assert db.session.get(Room, target.room_id) is None
    assert db.session.execute(select(Booking).filter_by(code=code)).scalar_one_or_none() is None
    assert db.session.execute(
        select(func.count()).select_from(hotel_amenities)
        .where(hotel_amenities.c.hotel_id == target.hotel_id)).scalar_one() == 0
    assert db.session.execute(
        select(func.count()).select_from(room_type_amenities)
        .where(room_type_amenities.c.room_type_id == target.type_id)).scalar_one() == 0

    # tiện nghi và khách sạn khác còn nguyên
    assert db.session.get(Amenity, amenity.id) is not None
    assert db.session.get(Hotel, other.hotel_id) is not None
    assert db.session.get(Room, other.room_id) is not None

    # ảnh upload tên trần bị xóa; ảnh có thư mục con thì giữ
    assert not (uploads / "hotel-cover.jpg").exists()
    assert (uploads / "uploads" / "hotels" / "x" / "type-cover.jpg").exists()


def test_delete_hotel_loi_thi_rollback_va_khong_xoa_anh(scratch, uploads):
    target, _, _ = _full_hotel(scratch, uploads)
    code = make_booking(target.room_id, future(5), future(7), "Pending").code
    hotel = db.session.get(Hotel, target.hotel_id)

    with pytest.MonkeyPatch.context() as m:
        m.setattr(db.session, "commit", _boom)
        with pytest.raises(RuntimeError):
            delete_hotel(hotel)

    db.session.expire_all()
    assert db.session.get(Hotel, target.hotel_id) is not None
    assert db.session.get(Room, target.room_id) is not None
    assert db.session.execute(select(Booking).filter_by(code=code)).scalar_one_or_none() is not None
    assert (uploads / "hotel-cover.jpg").exists()


# ─── delete_image ───────────────────────────────────────────────────────────

def test_delete_image_xoa_file_ton_tai_va_bo_qua_file_thieu(uploads):
    (uploads / "a.jpg").write_bytes(b"x")
    hs.delete_image("a.jpg")
    assert not (uploads / "a.jpg").exists()
    hs.delete_image("missing.jpg")  # không có file: không báo lỗi


@pytest.mark.parametrize("name", [None, "", "sub/a.jpg"])
def test_delete_image_bo_qua_ten_rong_va_duong_dan_con(uploads, name):
    nested = uploads / "sub"
    nested.mkdir()
    (nested / "a.jpg").write_bytes(b"x")
    hs.delete_image(name)
    assert (nested / "a.jpg").exists()