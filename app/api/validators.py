import re
from datetime import date

from flask import request

from ..utils.security import sanitize
from .errors import ApiError

STATUSES = ("Pending", "Confirmed", "Cancelled", "Completed")
PHONE_RE = re.compile(r"^0[0-9]{9}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def json_body():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ApiError(400, "Body phải là một JSON object.")
    return body


def parse_iso_date(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ApiError(400, "Thiếu ngày.", {field: "Bắt buộc, định dạng YYYY-MM-DD."})
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        raise ApiError(400, "Ngày không hợp lệ.",
                       {field: "Phải đúng định dạng YYYY-MM-DD."}) from None


def date_range(checkin, checkout, allow_past=True):
    """Cả hai ngày bắt buộc, đúng ISO, checkout > checkin (và không ở quá khứ nếu allow_past=False)."""
    ci = parse_iso_date(checkin, "checkin")
    co = parse_iso_date(checkout, "checkout")
    if co <= ci:
        raise ApiError(400, "Ngày trả phải sau ngày nhận.",
                       {"checkout": "Phải sau ngày nhận."})
    if not allow_past and ci < date.today():
        raise ApiError(400, "Ngày nhận không được trong quá khứ.",
                       {"checkin": "Không được trong quá khứ."})
    return ci, co


def optional_date_range(args):
    """Không có ngày nào thì (None, None); có thì phải đủ cặp và hợp lệ."""
    checkin = (args.get("checkin") or "").strip()
    checkout = (args.get("checkout") or "").strip()
    if not checkin and not checkout:
        return None, None
    return date_range(checkin, checkout)


def int_field(value, field, minimum=None, maximum=None, required=True):
    if value is None or value == "":
        if required:
            raise ApiError(400, "Thiếu tham số.", {field: "Bắt buộc."})
        return None
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ApiError(400, "Tham số không hợp lệ.", {field: "Phải là số nguyên."})
    try:
        number = int(value)
    except ValueError:
        raise ApiError(400, "Tham số không hợp lệ.", {field: "Phải là số nguyên."}) from None
    if (minimum is not None and number < minimum) or (maximum is not None and number > maximum):
        raise ApiError(400, "Tham số không hợp lệ.", {field: "Nằm ngoài khoảng cho phép."})
    return number


def validate_status(value):
    if not isinstance(value, str) or value not in STATUSES:
        raise ApiError(400, "Trạng thái không hợp lệ.",
                       {"status": "Phải là một trong: " + ", ".join(STATUSES) + "."})
    return value


def clean_reason(value):
    if value is None or value == "":
        return None
    if not isinstance(value, str) or len(value) > 500:
        raise ApiError(400, "Lý do không hợp lệ.", {"reason": "Tối đa 500 ký tự."})
    return sanitize(value).strip() or None


def _name(value):
    if not isinstance(value, str) or not 2 <= len(value.strip()) <= 100:
        raise ValueError("Họ tên từ 2 đến 100 ký tự.")
    return value.strip()


def _phone(value):
    if not isinstance(value, str) or not PHONE_RE.match(value.strip()):
        raise ValueError("Số điện thoại phải đúng 10 chữ số, và bắt đầu bằng số 0.")
    return value.strip()


def _email(value):
    if not isinstance(value, str) or len(value) > 120 or not EMAIL_RE.match(value.strip()):
        raise ValueError("Email không đúng định dạng.")
    return value.strip().lower()


def _note(value):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 500:
        raise ValueError("Ghi chú tối đa 500 ký tự.")
    return sanitize(value).strip() or None


# tên trường: (hàm kiểm tra, bắt buộc)
BOOKING_CREATE_SPEC = {
    "guest_name": (_name, True), "guest_phone": (_phone, True),
    "guest_email": (_email, True), "note": (_note, False),
}
BOOKING_PATCH_SPEC = {
    "guest_name": (_name, False), "guest_phone": (_phone, False), "note": (_note, False),
}


def clean_fields(body, spec, partial=False):
    cleaned, errors = {}, {}
    for name, (check, required) in spec.items():
        if name not in body:
            if required and not partial:
                errors[name] = "Bắt buộc."
            continue
        try:
            cleaned[name] = check(body[name])
        except ValueError as exc:
            errors[name] = str(exc)
    if errors:
        raise ApiError(400, "Dữ liệu không hợp lệ.", errors)
    return cleaned