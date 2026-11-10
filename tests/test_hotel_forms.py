"""Test cho app/hotels/forms.py (HotelSearchForm, HotelForm). Không dùng DB."""
from datetime import date, timedelta
from io import BytesIO

import pytest
from werkzeug.datastructures import FileStorage, MultiDict

from app.hotels.forms import HotelForm, HotelSearchForm

PROVINCES = [("", "Tất cả điểm đến"), ("Hà Nội", "Hà Nội"), ("Đà Nẵng", "Đà Nẵng")]
AMENITY_CHOICES = [(1, "WiFi miễn phí"), (2, "Hồ bơi")]


@pytest.fixture
def ctx(app):
    with app.test_request_context():
        yield


def _day(offset):
    return (date.today() + timedelta(days=offset)).isoformat()


def _formdata(**fields):
    items = []
    for key, value in fields.items():
        values = value if isinstance(value, (list, tuple)) else [value]
        items.extend((key, v) for v in values)
    return MultiDict(items)


def _search(**fields):
    form = HotelSearchForm(formdata=_formdata(**fields), meta={"csrf": False})
    form.province.choices = PROVINCES
    return form


def _hotel(**overrides):
    data = {
        "name": "Khách sạn Thử", "province": "Cần Thơ", "address": "1 Đường A",
        "star_rating": "4", "description": "", "map_url": "",
    }
    data.update(overrides)
    form = HotelForm(formdata=_formdata(**data), meta={"csrf": False})
    form.amenity_ids.choices = AMENITY_CHOICES
    return form


# ─── HotelSearchForm ────────────────────────────────────────────────────────

def test_search_bo_trong_ca_hai_ngay_hop_le(ctx):
    form = _search(province="", checkin="", checkout="", guests="1")
    assert form.validate()


def test_search_ngay_chi_co_khoang_trang_van_hop_le(ctx):
    form = _search(province="", checkin="  ", checkout=" ", guests="1")
    assert form.validate()


def test_search_ngay_hop_le(ctx):
    form = _search(province="Hà Nội", checkin=_day(5), checkout=_day(7), guests="2")
    assert form.validate()


def test_search_ngay_nhan_la_hom_nay_hop_le(ctx):
    form = _search(checkin=_day(0), checkout=_day(1), guests="1")
    assert form.validate()


def test_search_chi_co_ngay_nhan(ctx):
    form = _search(checkin=_day(5), checkout="", guests="1")
    assert not form.validate()
    assert "Vui lòng chọn ngày trả." in form.checkout.errors
    assert not form.checkin.errors


def test_search_chi_co_ngay_tra(ctx):
    form = _search(checkin="", checkout=_day(5), guests="1")
    assert not form.validate()
    assert "Vui lòng chọn ngày nhận." in form.checkin.errors
    assert not form.checkout.errors


def test_search_ngay_sai_dinh_dang(ctx):
    form = _search(checkin="01/12/2030", checkout="abc", guests="1")
    assert not form.validate()
    assert "Ngày nhận không đúng định dạng." in form.checkin.errors
    assert "Ngày trả không đúng định dạng." in form.checkout.errors


def test_search_ngay_nhan_trong_qua_khu(ctx):
    form = _search(checkin=_day(-1), checkout=_day(3), guests="1")
    assert not form.validate()
    assert "Ngày nhận không được trong quá khứ." in form.checkin.errors
    assert not form.checkout.errors


def test_search_ngay_tra_bang_ngay_nhan(ctx):
    form = _search(checkin=_day(5), checkout=_day(5), guests="1")
    assert not form.validate()
    assert "Ngày trả phải sau ngày nhận." in form.checkout.errors


def test_search_ngay_tra_truoc_ngay_nhan(ctx):
    form = _search(checkin=_day(8), checkout=_day(5), guests="1")
    assert not form.validate()
    assert "Ngày trả phải sau ngày nhận." in form.checkout.errors


@pytest.mark.parametrize("guests", ["0", "-2", "abc"])
def test_search_so_khach_khong_hop_le(ctx, guests):
    form = _search(checkin="", checkout="", guests=guests)
    assert not form.validate()
    assert form.guests.errors


def test_search_tinh_khong_nam_trong_danh_sach(ctx):
    form = _search(province="Cần Thơ", checkin="", checkout="", guests="1")
    assert not form.validate()
    assert form.province.errors


def test_search_tinh_hop_le(ctx):
    form = _search(province="Đà Nẵng", checkin="", checkout="", guests="1")
    assert form.validate()


# ─── HotelForm ──────────────────────────────────────────────────────────────

def test_hotel_form_hop_le(ctx):
    form = _hotel()
    assert form.validate(), form.errors
    assert form.star_rating.data == 4


@pytest.mark.parametrize("field,value", [
    ("name", "AB"),
    ("name", "A" * 150),
    ("province", "AB"),
    ("province", "A" * 80),
    ("address", "A" * 255),
    ("description", "A" * 2000),
    ("star_rating", "1"),
    ("star_rating", "5"),
    ("map_url", "https://maps.google.com/?q=hotel"),
    ("amenity_ids", ["1", "2"]),
])
def test_hotel_form_gia_tri_bien_hop_le(ctx, field, value):
    form = _hotel(**{field: value})
    assert form.validate(), form.errors


@pytest.mark.parametrize("field,value", [
    ("name", ""),
    ("name", "   "),
    ("name", "A"),
    ("name", "A" * 151),
    ("province", ""),
    ("province", "A"),
    ("province", "A" * 81),
    ("address", ""),
    ("address", "A" * 256),
    ("star_rating", "0"),
    ("star_rating", "6"),
    ("star_rating", "abc"),
    ("description", "A" * 2001),
    ("map_url", "abc"),
    ("map_url", "https://example.com/" + "a" * 481),
    ("amenity_ids", ["99"]),
    ("amenity_ids", ["abc"]),
])
def test_hotel_form_gia_tri_khong_hop_le(ctx, field, value):
    form = _hotel(**{field: value})
    assert not form.validate()
    assert getattr(form, field).errors


def test_hotel_form_khong_chon_tien_nghi_van_hop_le(ctx):
    form = _hotel()
    assert form.validate(), form.errors
    assert form.amenity_ids.data == []


def test_hotel_form_anh_png_hop_le(ctx):
    image = FileStorage(stream=BytesIO(b"x"), filename="anh.png")
    form = _hotel(image=image)
    assert form.validate(), form.errors


def test_hotel_form_anh_gif_bi_tu_choi(ctx):
    image = FileStorage(stream=BytesIO(b"x"), filename="anh.gif")
    form = _hotel(image=image)
    assert not form.validate()
    assert form.image.errors