from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, Length, EqualTo, Regexp, Optional


class LoginForm(FlaskForm):
    email    = StringField("Email", validators=[
        DataRequired(message="Vui lòng nhập email."),
        Email(message="Email không đúng định dạng."),
    ])
    password = PasswordField("Mật khẩu", validators=[
        DataRequired(message="Vui lòng nhập mật khẩu."),
    ])
    remember = BooleanField("Ghi nhớ đăng nhập")
    submit   = SubmitField("Đăng nhập")


class RegisterForm(FlaskForm):
    full_name = StringField("Họ tên", validators=[
        DataRequired(message="Vui lòng nhập họ tên."),
        Length(min=2, max=100, message="Họ tên từ 2 đến 100 ký tự."),
    ])
    email = StringField("Email", validators=[
        DataRequired(message="Vui lòng nhập email."),
        Email(message="Email không đúng định dạng."),
        Length(max=120, message="Email tối đa 120 ký tự."),
    ])
    phone = StringField("Số điện thoại", validators=[
        Optional(),
        Regexp(r"^[0-9]{10}$", message="Số điện thoại phải đúng 10 chữ số."),
    ])
    password = PasswordField("Mật khẩu", validators=[
        DataRequired(message="Vui lòng nhập mật khẩu."),
        Length(min=8, message="Mật khẩu phải từ 8 ký tự."),
    ])
    confirm_password = PasswordField("Xác nhận mật khẩu", validators=[
        DataRequired(message="Vui lòng xác nhận mật khẩu."),
        EqualTo("password", message="Mật khẩu xác nhận không khớp."),
    ])
    submit = SubmitField("Đăng ký")


class ChangePasswordForm(FlaskForm):
    old_password = PasswordField("Mật khẩu hiện tại", validators=[
        DataRequired(message="Vui lòng nhập mật khẩu hiện tại."),
    ])
    new_password = PasswordField("Mật khẩu mới", validators=[
        DataRequired(message="Vui lòng nhập mật khẩu mới."),
        Length(min=8, message="Mật khẩu phải từ 8 ký tự."),
    ])
    confirm_password = PasswordField("Xác nhận mật khẩu mới", validators=[
        DataRequired(message="Vui lòng xác nhận mật khẩu mới."),
        EqualTo("new_password", message="Mật khẩu xác nhận không khớp."),
    ])
    submit = SubmitField("Đổi mật khẩu")