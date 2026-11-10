"""Test cho các hàm thuần trong app/hotels/services.py:
parse_dates, parse_search_args, search_query. Không dùng DB."""
from datetime import date, timedelta

import pytest
from werkzeug.datastructures import MultiDict

from app.hotels.services import (
    DEFAULT_SORT, SORT_LABELS, parse_dates, parse_search_args, search_query,
)


def _day(offset):
    return (date.today() + timedelta(days=offset)).isoformat()


def _args(**fields):
    items = []
    for key, value in fields.items():
        values = value if isinstance(value, (list, tuple)) else [value]
        items.extend((key, v) for v in values)
    return MultiDict(items)


# ─── parse_dates ────────────────────────────────────────────────────────────

def test_parse_dates_hop_le():
    assert parse_dates("2030-01-10", "2030-01-12") == (date(2030, 1, 10), date(2030, 1, 12))


@pytest.mark.parametrize("checkin,checkout", [
    ("2030-01-10", "2030-01-10"),
    ("2030-01-12", "2030-01-10"),
    ("2030-01-10", ""),
    ("", "2030-01-10"),
    ("", ""),
    (None, None),
    ("2030-01-10", None),
    ("abc", "2030-01-10"),
    ("2030-01-10", "2030-13-01"),
    ("2030-02-30", "2030-03-02"),
    ("10/01/2030", "12/01/2030"),
])
def test_parse_dates_khong_hop_le(checkin, checkout):
    assert parse_dates(checkin, checkout) == (None, None)


# ─── parse_search_args ──────────────────────────────────────────────────────

def test_args_mac_dinh():
    params, errors = parse_search_args(MultiDict())
    assert errors == {}
    assert params == {
        "province": "", "checkin": "", "checkout": "", "dates": (None, None),
        "guests": 1, "min_price": None, "max_price": None, "stars": None,
        "amenities": [], "sort": DEFAULT_SORT, "page": 1,
    }


def test_args_tinh_duoc_cat_khoang_trang():
    params, errors = parse_search_args(_args(province="  Đà Nẵng "))
    assert params["province"] == "Đà Nẵng"
    assert errors == {}


def test_args_ngay_hop_le():
    params, errors = parse_search_args(_args(checkin=_day(10), checkout=_day(12)))
    assert errors == {}
    assert params["dates"] == (date.today() + timedelta(days=10),
                               date.today() + timedelta(days=12))
    assert params["checkin"] == _day(10)
    assert params["checkout"] == _day(12)


def test_args_ngay_nhan_la_hom_nay_hop_le():
    params, errors = parse_search_args(_args(checkin=_day(0), checkout=_day(1)))
    assert errors == {}
    assert params["dates"][0] == date.today()


@pytest.mark.parametrize("fields", [
    {"checkin": _day(10)},
    {"checkout": _day(10)},
    {"checkin": _day(10), "checkout": _day(10)},
    {"checkin": _day(12), "checkout": _day(10)},
    {"checkin": "abc", "checkout": _day(10)},
])
def test_args_ngay_khong_hop_le_bi_bo_qua(fields):
    params, errors = parse_search_args(_args(**fields))
    assert "dates" in errors
    assert params["dates"] == (None, None)
    assert params["checkin"] == ""
    assert params["checkout"] == ""


def test_args_ngay_nhan_trong_qua_khu():
    params, errors = parse_search_args(_args(checkin=_day(-1), checkout=_day(2)))
    assert errors == {"dates": "Ngày nhận không được trong quá khứ."}
    assert params["dates"] == (None, None)
    assert params["checkin"] == ""


@pytest.mark.parametrize("raw,expected,has_error", [
    ("", 1, False),
    ("1", 1, False),
    ("5", 5, False),
    ("20", 20, False),
    ("0", 1, True),
    ("21", 1, True),
    ("-1", 1, True),
    ("abc", 1, True),
    ("2.5", 1, True),
])
def test_args_so_khach(raw, expected, has_error):
    params, errors = parse_search_args(_args(guests=raw))
    assert params["guests"] == expected
    assert ("guests" in errors) is has_error


def test_args_khoang_gia_hop_le():
    params, errors = parse_search_args(_args(min_price="100000", max_price="500000"))
    assert errors == {}
    assert params["min_price"] == 100000
    assert params["max_price"] == 500000


def test_args_gia_toi_thieu_bang_toi_da_hop_le():
    params, errors = parse_search_args(_args(min_price="100", max_price="100"))
    assert errors == {}
    assert (params["min_price"], params["max_price"]) == (100, 100)


def test_args_gia_toi_thieu_lon_hon_toi_da():
    params, errors = parse_search_args(_args(min_price="500", max_price="100"))
    assert "min_price" in errors
    assert params["min_price"] is None
    assert params["max_price"] is None


@pytest.mark.parametrize("fields,field", [
    ({"min_price": "-5"}, "min_price"),
    ({"min_price": "abc"}, "min_price"),
    ({"max_price": "-1"}, "max_price"),
    ({"max_price": "abc"}, "max_price"),
])
def test_args_gia_khong_hop_le(fields, field):
    params, errors = parse_search_args(_args(**fields))
    assert field in errors
    assert params[field] is None


@pytest.mark.parametrize("raw,expected,has_error", [
    ("", None, False),
    ("1", 1, False),
    ("5", 5, False),
    ("0", None, True),
    ("6", None, True),
    ("x", None, True),
])
def test_args_hang_sao(raw, expected, has_error):
    params, errors = parse_search_args(_args(stars=raw))
    assert params["stars"] == expected
    assert ("stars" in errors) is has_error


def test_args_tien_nghi_hop_le():
    params, errors = parse_search_args(_args(amenity=["1", "2"]))
    assert params["amenities"] == [1, 2]
    assert errors == {}


def test_args_tien_nghi_sai_bi_bo_qua():
    params, errors = parse_search_args(_args(amenity=["3", "x"]))
    assert params["amenities"] == [3]
    assert "amenity" in errors


@pytest.mark.parametrize("sort", sorted(SORT_LABELS))
def test_args_sort_hop_le(sort):
    params, errors = parse_search_args(_args(sort=sort))
    assert params["sort"] == sort
    assert errors == {}


def test_args_sort_sai_dung_mac_dinh():
    params, errors = parse_search_args(_args(sort="bogus"))
    assert params["sort"] == DEFAULT_SORT
    assert "sort" in errors


def test_args_sort_rong_dung_mac_dinh_khong_loi():
    params, errors = parse_search_args(_args(sort=""))
    assert params["sort"] == DEFAULT_SORT
    assert errors == {}


@pytest.mark.parametrize("raw,expected", [
    ("", 1), ("1", 1), ("2", 2), ("0", 1), ("-3", 1), ("abc", 1),
])
def test_args_page_khong_bao_loi(raw, expected):
    params, errors = parse_search_args(_args(page=raw))
    assert params["page"] == expected
    assert errors == {}


def test_args_nhieu_loi_cung_luc():
    params, errors = parse_search_args(_args(guests="0", sort="bogus", stars="9"))
    assert {"guests", "sort", "stars"} <= set(errors)


# ─── search_query ───────────────────────────────────────────────────────────

def test_search_query_mac_dinh_rong():
    params, _ = parse_search_args(MultiDict())
    assert search_query(params) == {}


def test_search_query_day_du_va_khong_co_page():
    params, errors = parse_search_args(_args(
        province="Đà Nẵng", checkin=_day(10), checkout=_day(12), guests="3",
        min_price="100000", max_price="500000", stars="4",
        amenity=["1", "2"], sort="price_asc", page="3",
    ))
    assert errors == {}
    assert search_query(params) == {
        "province": "Đà Nẵng", "checkin": _day(10), "checkout": _day(12),
        "guests": 3, "min_price": 100000, "max_price": 500000, "stars": 4,
        "amenity": [1, 2], "sort": "price_asc",
    }


def test_search_query_bo_gia_tri_mac_dinh():
    params, _ = parse_search_args(_args(guests="1", sort=DEFAULT_SORT, province=""))
    query = search_query(params)
    assert "guests" not in query
    assert "sort" not in query
    assert "province" not in query


def test_search_query_giu_gia_tri_0():
    params, _ = parse_search_args(_args(min_price="0"))
    assert search_query(params)["min_price"] == 0


def test_sort_labels_co_gia_tri_mac_dinh():
    assert DEFAULT_SORT in SORT_LABELS
    assert set(SORT_LABELS) == {"stars_desc", "price_asc", "price_desc"}