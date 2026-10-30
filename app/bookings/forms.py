from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, TextAreaField, SubmitField, HiddenField
from wtforms.validators import DataRequired, Email, Length, NumberRange, Regexp, Optional
from wtforms.fields import DateField


class BookingStep1Form(FlaskForm):
    hotel_id  = HiddenField("Hotel ID", validators=[
        DataRequired(message="Vui lòng chọn khách sạn."),
    ])
    room_id   = HiddenField("Room ID", validators=[
        DataRequired(message="Vui lòng chọn phòng."),
    ])
    check_in  = DateField("Ngày nhận phòng", validators=[
        DataRequired(message="Vui lòng chọn ngày nhận phòng."),
    ])
    check_out = DateField("Ngày trả phòng", validators=[
        DataRequired(message="Vui lòng chọn ngày trả phòng."),
    ])
    guests = IntegerField("Số khách", validators=[
        DataRequired(message="Vui lòng nhập số khách."),
        NumberRange(min=1, max=10, message="Số khách từ 1 đến 10."),
    ])
    submit = SubmitField("Tiếp tục")


class BookingStep2Form(FlaskForm):
    guest_name = StringField("Họ tên khách", validators=[
        DataRequired(message="Vui lòng nhập họ tên khách."),
        Length(min=2, max=100, message="Họ tên từ 2 đến 100 ký tự."),
    ])
    guest_phone = StringField("Số điện thoại", validators=[
        DataRequired(message="Vui lòng nhập số điện thoại."),
        Regexp(r"^[0-9]{10}$", message="Số điện thoại phải đúng 10 chữ số."),
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
    submit = SubmitField("Xác nhận")


class BookingStep3Form(FlaskForm):
    hotel_id    = HiddenField(validators=[DataRequired(message="Thiếu thông tin khách sạn.")])
    room_id     = HiddenField(validators=[DataRequired(message="Thiếu thông tin phòng.")])
    check_in    = HiddenField(validators=[DataRequired(message="Thiếu ngày nhận phòng.")])
    check_out   = HiddenField(validators=[DataRequired(message="Thiếu ngày trả phòng.")])
    guests      = HiddenField(validators=[DataRequired(message="Thiếu số khách.")])
    guest_name  = HiddenField(validators=[DataRequired(message="Thiếu họ tên khách.")])
    guest_phone = HiddenField(validators=[DataRequired(message="Thiếu số điện thoại.")])
    guest_email = HiddenField(validators=[DataRequired(message="Thiếu email.")])
    note        = HiddenField()
    submit      = SubmitField("Đặt phòng")


class CancelBookingForm(FlaskForm):
    cancel_reason = TextAreaField("Lý do hủy", validators=[
        Optional(),
        Length(max=500, message="Lý do tối đa 500 ký tự."),
    ])
    submit = SubmitField("Hủy đặt phòng")