"""Test app/utils/security.py và app/utils/dates.py."""
import io
import os
from datetime import date, timedelta

import pytest

from app.utils.dates import has_conflict, is_valid_date_range, nights_between, MAX_NIGHTS
from app.utils.security import (
    is_safe_url, sanitize, save_image, save_image_to_folder,
    save_uploaded_image, slugify, ALLOWED_EXTENSIONS, MAX_IMAGE_BYTES,
)
from werkzeug.datastructures import FileStorage
from tests.room_helpers import (  # noqa: F401
    anon, clean_bookings, future, make_booking, scratch,
)


# ─── slugify ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("Hà Nội",           "ha-noi"),
    ("Khách Sạn Đà Lạt", "khach-san-da-lat"),
    ("đường Đồng Khởi",  "duong-dong-khoi"),
    ("ABC 123",          "abc-123"),
    ("  --hello--  ",    "hello"),
    ("",                 "unnamed"),
    ("!!!",              "unnamed"),
    ("Phú Quốc",         "phu-quoc"),
])
def test_slugify(text, expected):
    assert slugify(text) == expected


# ─── sanitize ───────────────────────────────────────────────────────────────

def test_sanitize_xoa_the_html():
    assert sanitize("<script>alert(1)</script>hello") == "alert(1)hello"


def test_sanitize_xoa_thuoc_tinh():
    assert sanitize('<p onclick="evil()">text</p>') == "text"


def test_sanitize_van_ban_binh_thuong_giu_nguyen():
    assert sanitize("Ghi chú: Lấy phòng trễ.") == "Ghi chú: Lấy phòng trễ."


def test_sanitize_chuoi_rong():
    assert sanitize("") == ""


# ─── is_safe_url ────────────────────────────────────────────────────────────

def test_is_safe_url_duong_dan_noi_bo(app):
    with app.test_request_context("/"):
        assert is_safe_url("/auth/profile") is True
        assert is_safe_url("/admin/dashboard") is True


def test_is_safe_url_host_ngoai_bi_chan(app):
    with app.test_request_context("/"):
        assert is_safe_url("https://evil.com/steal") is False
        assert is_safe_url("http://evil.com") is False


def test_is_safe_url_javascript_bi_chan(app):
    with app.test_request_context("/"):
        assert is_safe_url("javascript:alert(1)") is False


def test_is_safe_url_duong_dan_tuong_doi(app):
    with app.test_request_context("/"):
        assert is_safe_url("../etc/passwd") is True  # cùng host, chỉ path


# ─── save_image ─────────────────────────────────────────────────────────────

def _make_file(name, content=b"fake-image-data"):
    return FileStorage(stream=io.BytesIO(content), filename=name)


def test_save_image_thanh_cong(tmp_path):
    f = _make_file("photo.jpg")
    result = save_image(f, str(tmp_path))
    assert result is not None
    assert result.endswith(".jpg")
    assert (tmp_path / result).exists()


@pytest.mark.parametrize("name", ["photo.gif", "photo.bmp", "photo.svg", "photo.exe"])
def test_save_image_dinh_dang_khong_hop_le(tmp_path, name):
    assert save_image(_make_file(name), str(tmp_path)) is None
    assert list(tmp_path.iterdir()) == []


def test_save_image_qua_lon(tmp_path):
    big = b"x" * (MAX_IMAGE_BYTES + 1)
    assert save_image(_make_file("photo.jpg", big), str(tmp_path)) is None


def test_save_image_file_none(tmp_path):
    assert save_image(None, str(tmp_path)) is None


def test_save_image_filename_rong(tmp_path):
    f = _make_file("")
    assert save_image(f, str(tmp_path)) is None


def test_save_image_tao_thu_muc_neu_chua_co(tmp_path):
    folder = tmp_path / "new_sub"
    f = _make_file("photo.png")
    result = save_image(f, str(folder))
    assert result is not None
    assert folder.exists()


@pytest.mark.parametrize("ext", sorted(ALLOWED_EXTENSIONS))
def test_save_image_cac_dinh_dang_hop_le(tmp_path, ext):
    f = _make_file(f"photo.{ext}")
    result = save_image(f, str(tmp_path))
    assert result is not None and result.endswith(f".{ext}")


# ─── save_image_to_folder ───────────────────────────────────────────────────

def test_save_image_to_folder_tra_duong_dan_tuong_doi(tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    f = _make_file("cover.jpg")
    result = save_image_to_folder(f, "uploads/hotels/test-hotel", str(static))
    assert result is not None
    assert result.startswith("uploads/hotels/test-hotel/")
    assert result.endswith(".jpg")
    assert (static / result).exists()


def test_save_image_to_folder_chan_path_traversal(tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    f = _make_file("evil.jpg")
    result = save_image_to_folder(f, "uploads/../../outside", str(static))
    assert result is None


def test_save_image_to_folder_dinh_dang_sai(tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    f = _make_file("photo.gif")
    assert save_image_to_folder(f, "uploads/hotels/x", str(static)) is None


def test_save_image_to_folder_file_none(tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    assert save_image_to_folder(None, "uploads/hotels/x", str(static)) is None


# ─── save_uploaded_image ────────────────────────────────────────────────────

class _FakeField:
    def __init__(self, file):
        self.data = file
        self.errors = []


class _FakeForm:
    def __init__(self, file):
        self.image = _FakeField(file)


def test_save_uploaded_image_thanh_cong(tmp_path):
    form = _FakeForm(_make_file("cover.png"))
    filename, ok = save_uploaded_image(form, str(tmp_path))
    assert ok is True
    assert filename is not None and filename.endswith(".png")


def test_save_uploaded_image_khong_co_file():
    form = _FakeForm(None)
    filename, ok = save_uploaded_image(form, "/tmp")
    assert ok is True and filename is None


def test_save_uploaded_image_filename_rong():
    form = _FakeForm(_make_file(""))
    filename, ok = save_uploaded_image(form, "/tmp")
    assert ok is True and filename is None


def test_save_uploaded_image_dinh_dang_sai(tmp_path):
    form = _FakeForm(_make_file("photo.gif"))
    filename, ok = save_uploaded_image(form, str(tmp_path))
    assert ok is False and filename is None
    assert form.image.errors != []


# ─── nights_between ─────────────────────────────────────────────────────────

def test_nights_between_tinh_dung():
    ci = date(2026, 11, 10)
    co = date(2026, 11, 13)
    assert nights_between(ci, co) == 3


def test_nights_between_mot_dem():
    d = date(2026, 12, 1)
    assert nights_between(d, d + timedelta(days=1)) == 1


def test_nights_between_check_out_khong_sau_raise():
    d = date(2026, 11, 10)
    with pytest.raises(ValueError):
        nights_between(d, d)
    with pytest.raises(ValueError):
        nights_between(d, d - timedelta(days=1))


# ─── is_valid_date_range ────────────────────────────────────────────────────

def test_is_valid_date_range_hop_le():
    assert is_valid_date_range(future(1), future(3)) is True


def test_is_valid_date_range_check_in_qua_khu():
    yesterday = date.today() - timedelta(days=1)
    assert is_valid_date_range(yesterday, future(2)) is False


def test_is_valid_date_range_check_out_khong_sau():
    today = date.today()
    assert is_valid_date_range(future(3), future(1)) is False
    assert is_valid_date_range(today, today) is False


def test_is_valid_date_range_check_in_hom_nay():
    # check_in == hôm nay vẫn hợp lệ (>= date.today())
    today = date.today()
    assert is_valid_date_range(today, future(1)) is True


# ─── has_conflict ────────────────────────────────────────────────────────────

def test_has_conflict_khong_trung(app, scratch):
    info = scratch.hotel(with_room=True)
    make_booking(info.room_id, future(5), future(7), "Confirmed")
    with app.app_context():
        # Khoảng hoàn toàn tách rời
        assert has_conflict(info.room_id, future(10), future(12)) is False


def test_has_conflict_co_trung(app, scratch):
    info = scratch.hotel(with_room=True)
    make_booking(info.room_id, future(5), future(8), "Confirmed")
    with app.app_context():
        assert has_conflict(info.room_id, future(6), future(9)) is True


def test_has_conflict_sat_ngay_khong_trung(app, scratch):
    info = scratch.hotel(with_room=True)
    make_booking(info.room_id, future(5), future(7), "Confirmed")
    with app.app_context():
        # check_in == check_out của booking cũ → không trùng
        assert has_conflict(info.room_id, future(7), future(9)) is False
        assert has_conflict(info.room_id, future(3), future(5)) is False


def test_has_conflict_booking_da_huy_khong_tinh(app, scratch):
    info = scratch.hotel(with_room=True)
    make_booking(info.room_id, future(5), future(7), "Cancelled")
    with app.app_context():
        assert has_conflict(info.room_id, future(5), future(7)) is False


def test_has_conflict_exclude_booking_id(app, scratch):
    info = scratch.hotel(with_room=True)
    bk = make_booking(info.room_id, future(5), future(7), "Pending")
    with app.app_context():
        # Loại trừ chính booking đó → không còn conflict
        assert has_conflict(info.room_id, future(5), future(7),
                            exclude_booking_id=bk.id) is False