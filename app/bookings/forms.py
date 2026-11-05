from flask_wtf import FlaskForm
from wtforms import (
    DateField, HiddenField, IntegerField, SelectField, StringField,
    SubmitField, TextAreaField,
)
from wtforms.validators import (
    DataRequired, Email, Length, NumberRange, Optional, Regexp,
)


class BookingStep1Form(FlaskForm):
    """Bước 1: chọn ngày và số khách."""
    room_id = HiddenField()
    hotel_id = HiddenField()
    check_in = DateField("Ngày nhận phòng", format="%Y-%m-%d", validators=[
        DataRequired(message="Vui lòng chọn ngày nhận phòng."),
    ])
    check_out = DateField("Ngày trả phòng", format="%Y-%m-%d", validators=[
        DataRequired(message="Vui lòng chọn ngày trả phòng."),
    ])
    guests = IntegerField("Số khách", default=1, validators=[
        DataRequired(message="Vui lòng nhập số khách."),
        NumberRange(min=1, message="Số khách tối thiểu là 1."),
    ])
    submit = SubmitField("Tiếp tục")


class BookingStep2Form(FlaskForm):
    """Bước 2: thông tin khách."""
    guest_name = StringField("Họ tên", validators=[
        DataRequired(message="Vui lòng nhập họ tên."),
        Length(min=2, max=100, message="Họ tên từ 2 đến 100 ký tự."),
    ])
    guest_phone = StringField("Số điện thoại", validators=[
        DataRequired(message="Vui lòng nhập số điện thoại."),
        Regexp(r"^0[0-9]{9}$", message="Số điện thoại phải gồm đúng 10 chữ số và bắt đầu bằng số 0."),
    ])
    guest_email = StringField("Email", validators=[
        DataRequired(message="Vui lòng nhập email."),
        Email(message="Email không đúng định dạng."),
        Length(max=120, message="Email tối đa 120 ký tự."),
    ])
    note = TextAreaField("Ghi chú", validators=[
        Optional(),
        Length(max=500, message="Ghi chú tối đa 500 ký tự."),
    ])
    submit = SubmitField("Tiếp tục")


class BookingStep3Form(FlaskForm):
    """Bước 3: xác nhận (chỉ nút gửi + CSRF)."""
    submit = SubmitField("Xác nhận đặt phòng")


class CancelBookingForm(FlaskForm):
    cancel_reason = StringField("Lý do hủy", validators=[
        Optional(),
        Length(max=500, message="Lý do tối đa 500 ký tự."),
    ])
    submit = SubmitField("Hủy booking")


class BookingFilterForm(FlaskForm):
    """Bộ lọc trang /manage/bookings (POST + CSRF, rồi redirect sang GET)."""
    hotel_id = SelectField("Khách sạn", choices=[], validators=[Optional()])
    status = SelectField("Trạng thái", validators=[Optional()], choices=[
        ("", "Tất cả"), ("Pending", "Chờ xác nhận"), ("Confirmed", "Đã xác nhận"),
        ("Cancelled", "Đã hủy"), ("Completed", "Hoàn tất"),
    ])
    date_from = StringField("Nhận từ ngày", validators=[Optional()])
    date_to = StringField("Nhận đến ngày", validators=[Optional()])
    q = StringField("Từ khóa", validators=[Optional(), Length(max=100)])
    submit = SubmitField("Lọc")