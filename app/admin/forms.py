from flask_wtf import FlaskForm
from wtforms import (StringField, TextAreaField, PasswordField,
                    SelectField, BooleanField, SubmitField)
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional

from ..auth.forms import PASSWORD_RULE, PHONE_RULE


class BookingStatusForm(FlaskForm):
    status = SelectField("Trạng thái", choices=[
        ("Pending",   "Chờ xác nhận"),
        ("Confirmed", "Đã xác nhận"),
        ("Cancelled", "Đã hủy"),
        ("Completed", "Hoàn thành"),
    ], validators=[
        DataRequired(message="Vui lòng chọn trạng thái."),
    ])
    cancel_reason = TextAreaField("Lý do hủy", validators=[
        Optional(),
        Length(max=500, message="Lý do tối đa 500 ký tự."),
    ])
    submit = SubmitField("Cập nhật")


class ReceptionistForm(FlaskForm):
    """Admin tạo tài khoản lễ tân."""
    full_name = StringField("Họ tên", validators=[
        DataRequired(message="Vui lòng nhập họ tên."),
        Length(min=2, max=100, message="Họ tên từ 2 đến 100 ký tự."),
    ])
    email = StringField("Email", validators=[
        DataRequired(message="Vui lòng nhập email."),
        Email(message="Email không đúng định dạng."),
        Length(max=120, message="Email tối đa 120 ký tự."),
    ])
    phone = StringField("Số điện thoại", validators=[Optional(), PHONE_RULE])
    password = PasswordField("Mật khẩu", validators=[
        DataRequired(message="Vui lòng nhập mật khẩu."),
        Length(min=8, message="Mật khẩu phải từ 8 ký tự."),
        PASSWORD_RULE,
    ])
    confirm_password = PasswordField("Xác nhận mật khẩu", validators=[
        DataRequired(message="Vui lòng xác nhận mật khẩu."),
        EqualTo("password", message="Mật khẩu xác nhận không khớp."),
    ])
    submit = SubmitField("Tạo tài khoản lễ tân")


class UserForm(FlaskForm):
    full_name = StringField("Họ tên", validators=[
        DataRequired(message="Vui lòng nhập họ tên."),
        Length(min=2, max=100, message="Họ tên từ 2 đến 100 ký tự."),
    ])
    role = SelectField("Vai trò", choices=[
        ("customer",     "Khách hàng"),
        ("receptionist", "Lễ tân"),
        ("admin",        "Admin"),
    ], validators=[
        DataRequired(message="Vui lòng chọn vai trò."),
    ])
    is_active = BooleanField("Đang hoạt động", default=True)
    submit    = SubmitField("Lưu")