from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (StringField, TextAreaField, IntegerField,
                     SelectField, BooleanField, SubmitField, DecimalField)
from wtforms.validators import DataRequired, Length, NumberRange, Optional, URL


class HotelForm(FlaskForm):
    name = StringField("Tên khách sạn", validators=[
        DataRequired(message="Vui lòng nhập tên khách sạn."),
        Length(min=2, max=150, message="Tên từ 2 đến 150 ký tự."),
    ])
    province = StringField("Tỉnh/Thành phố", validators=[
        DataRequired(message="Vui lòng nhập tỉnh/thành phố."),
        Length(min=2, max=80, message="Tên tỉnh từ 2 đến 80 ký tự."),
    ])
    address = StringField("Địa chỉ", validators=[
        DataRequired(message="Vui lòng nhập địa chỉ."),
        Length(min=5, max=255, message="Địa chỉ từ 5 đến 255 ký tự."),
    ])
    star_rating = SelectField("Số sao", choices=[
        ("1","1 sao"),("2","2 sao"),("3","3 sao"),("4","4 sao"),("5","5 sao")
    ], coerce=int, validators=[
        DataRequired(message="Vui lòng chọn số sao."),
    ])
    description = TextAreaField("Mô tả", validators=[
        Optional(),
        Length(max=2000, message="Mô tả tối đa 2000 ký tự."),
    ])
    map_url = StringField("Link Google Maps", validators=[
        Optional(),
        URL(message="Link Google Maps không đúng định dạng."),
        Length(max=500, message="Link tối đa 500 ký tự."),
    ])
    image = FileField("Ảnh đại diện", validators=[
        Optional(),
        FileAllowed(["jpg","jpeg","png","webp"], message="Chỉ chấp nhận file ảnh jpg, png, webp."),
    ])
    is_active = BooleanField("Đang hoạt động", default=True)
    submit    = SubmitField("Lưu")


class RoomTypeForm(FlaskForm):
    name = StringField("Tên loại phòng", validators=[
        DataRequired(message="Vui lòng nhập tên loại phòng."),
        Length(min=2, max=100, message="Tên từ 2 đến 100 ký tự."),
    ])
    description = TextAreaField("Mô tả", validators=[
        Optional(),
        Length(max=1000, message="Mô tả tối đa 1000 ký tự."),
    ])
    base_price = DecimalField("Giá/đêm (VND)", validators=[
        DataRequired(message="Vui lòng nhập giá phòng."),
        NumberRange(min=0, message="Giá phải lớn hơn 0."),
    ], places=0)
    capacity = IntegerField("Sức chứa (người)", validators=[
        DataRequired(message="Vui lòng nhập sức chứa."),
        NumberRange(min=1, max=20, message="Sức chứa từ 1 đến 20 người."),
    ])
    image = FileField("Ảnh đại diện", validators=[
        Optional(),
        FileAllowed(["jpg","jpeg","png","webp","avif"], message="Chỉ chấp nhận file ảnh."),
    ])
    submit = SubmitField("Lưu")


class RoomForm(FlaskForm):
    room_number = StringField("Số phòng", validators=[
        DataRequired(message="Vui lòng nhập số phòng."),
        Length(min=1, max=10, message="Số phòng tối đa 10 ký tự."),
    ])
    floor = IntegerField("Tầng", validators=[
        DataRequired(message="Vui lòng nhập số tầng."),
        NumberRange(min=1, max=100, message="Tầng từ 1 đến 100."),
    ])
    room_type_id = SelectField("Loại phòng", coerce=int, validators=[
        DataRequired(message="Vui lòng chọn loại phòng."),
    ])
    is_active = BooleanField("Đang hoạt động", default=True)
    submit    = SubmitField("Lưu")


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