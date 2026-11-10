"""Nhân viên hủy booking Confirmed từ ngày nhận phòng trở đi: vẫn tính doanh thu
(cột bookings.is_charged); khách tự hủy vẫn bị chặn từ ngày nhận."""
from datetime import date, timedelta

import pytest

from app.admin.services import get_occupancy_today, get_revenue_by_month
from app.bookings.services import change_status
from app.extensions import db
from tests.room_helpers import (  # noqa: F401  (clean_bookings là fixture autouse)
    clean_bookings, get_user, make_booking, scratch,
)

STAFF = ["staff@test.com", "admin@test.com"]


def _booking(info, offset, status="Confirmed"):
    check_in = date.today() + timedelta(days=offset)
    return make_booking(info.room_id, check_in, check_in + timedelta(days=2), status)


def _revenue_this_month(hotel_id):
    rows = {r["month"]: r["revenue"] for r in get_revenue_by_month(hotel_id)}
    return rows[date.today().strftime("%Y-%m")]


def test_booking_moi_mac_dinh_khong_tinh_tien(scratch):
    info = scratch.hotel()
    assert _booking(info, 5).is_charged is False


@pytest.mark.parametrize("email", STAFF)
@pytest.mark.parametrize("offset,expected", [(5, False), (1, False), (0, True), (-1, True)])
def test_nhan_vien_huy_confirmed_chi_tinh_tien_tu_ngay_nhan(scratch, email, offset, expected):
    info = scratch.hotel()
    booking = _booking(info, offset)
    result = change_status(booking, "Cancelled", get_user(email), "Khách bận")
    assert result.status == "Cancelled"
    assert result.cancel_reason == "Khách bận"
    assert result.is_charged is expected


def test_nhan_vien_huy_pending_khong_tinh_tien(scratch):
    info = scratch.hotel()
    booking = _booking(info, 0, "Pending")
    result = change_status(booking, "Cancelled", get_user("staff@test.com"), "Từ chối")
    assert result.status == "Cancelled"
    assert result.is_charged is False


def test_nhan_vien_huy_thieu_ly_do_bi_tu_choi(scratch):
    info = scratch.hotel()
    booking = _booking(info, 0)
    with pytest.raises(ValueError):
        change_status(booking, "Cancelled", get_user("staff@test.com"), None)
    db.session.expire_all()
    assert booking.status == "Confirmed"
    assert booking.is_charged is False


def test_khach_huy_truoc_ngay_nhan_khong_tinh_tien(scratch):
    info = scratch.hotel()
    booking = _booking(info, 5)
    result = change_status(booking, "Cancelled", get_user("customer@test.com"))
    assert result.status == "Cancelled"
    assert result.is_charged is False


def test_khach_van_khong_tu_huy_duoc_tu_ngay_nhan(scratch):
    info = scratch.hotel()
    booking = _booking(info, 0)
    with pytest.raises(ValueError):
        change_status(booking, "Cancelled", get_user("customer@test.com"))
    db.session.expire_all()
    assert booking.status == "Confirmed"
    assert booking.is_charged is False


def test_doanh_thu_tinh_huy_muon_va_bo_qua_huy_thuong(scratch):
    info = scratch.hotel()
    _booking(info, 0, "Confirmed")
    _booking(info, 0, "Completed")
    _booking(info, 0, "Pending")
    _booking(info, 0, "Cancelled")          # hủy thường: không tính
    charged = _booking(info, 0, "Cancelled")  # hủy muộn: tính
    charged.is_charged = True
    db.session.commit()
    # mỗi booking 1.000.000: Confirmed + Completed + hủy muộn = 3.000.000
    assert _revenue_this_month(info.hotel_id) == 3000000.0


def test_doanh_thu_khong_doi_khi_nhan_vien_huy_muon(scratch):
    info = scratch.hotel()
    booking = _booking(info, 0)
    before = _revenue_this_month(info.hotel_id)
    change_status(booking, "Cancelled", get_user("staff@test.com"), "Khách bận")
    assert before == _revenue_this_month(info.hotel_id) == 1000000.0


def test_cong_suat_khong_tinh_booking_huy_muon(scratch):
    info = scratch.hotel()
    booking = _booking(info, 0)
    assert get_occupancy_today(info.hotel_id)["occupied"] == 1
    change_status(booking, "Cancelled", get_user("staff@test.com"), "Khách bận")
    assert get_occupancy_today(info.hotel_id)["occupied"] == 0