from datetime import date

def nights_between(check_in: date, check_out: date) -> int:
    """Trả về số đêm giữ check_in và check_out"""
    delta = check_out - check_in
    if delta.days <= 0:
        raise ValueError("check_out phải sau check_in")
    return delta.days

def is_valid_date_range(check_in:date, check_out:date) -> bool:
    return check_out > check_in >= date.today()