from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, MultipleFileField
from wtforms import (
    DecimalField, HiddenField, IntegerField, SelectField,
    SelectMultipleField, StringField, SubmitField, TextAreaField,
)
from wtforms.validators import DataRequired, Length, NumberRange, Optional


class RoomFilterForm(FlaskForm):
    """Bộ lọc phòng của một khách sạn (POST + CSRF, rồi redirect sang GET)."""
    hotel_id = HiddenField(validators=[DataRequired()])
    room_type_id = SelectField("Loại phòng", choices=[], validators=[Optional()])
    price_min = IntegerField("Giá từ (₫)", validators=[Optional(), NumberRange(min=0)])
    price_max = IntegerField("Đến (₫)", validators=[Optional(), NumberRange(min=0)])
    checkin = StringField("Ngày nhận", validators=[Optional()])
    checkout = StringField("Ngày trả", validators=[Optional()])
    guests = IntegerField("Số khách", default=1,
                          validators=[Optional(), NumberRange(min=1, max=20)])
    submit = SubmitField("Lọc phòng")


class RoomAdminForm(FlaskForm):
    hotel_id = SelectField("Khách sạn", coerce=int, choices=[], validators=[
        DataRequired(message="Vui lòng chọn khách sạn."),
    ])
    room_type_id = SelectField("Loại phòng", coerce=int, choices=[], validators=[
        DataRequired(message="Vui lòng chọn loại phòng."),
    ])
    room_number = StringField("Số phòng", validators=[
        DataRequired(message="Vui lòng nhập số phòng."),
        Length(min=1, max=10, message="Số phòng tối đa 10 ký tự."),
    ])
    floor = IntegerField("Tầng", validators=[
        DataRequired(message="Vui lòng nhập số tầng."),
        NumberRange(min=1, max=100, message="Tầng từ 1 đến 100."),
    ])
    submit = SubmitField("Lưu phòng")


class RoomTypeAdminForm(FlaskForm):
    hotel_id = SelectField("Khách sạn", coerce=int, choices=[], validators=[
        DataRequired(message="Vui lòng chọn khách sạn."),
    ])
    name = StringField("Tên loại phòng", validators=[
        DataRequired(message="Vui lòng nhập tên loại phòng."),
        Length(min=2, max=100, message="Tên từ 2 đến 100 ký tự."),
    ])
    description = TextAreaField("Mô tả", validators=[
        Optional(),
        Length(max=1000, message="Mô tả tối đa 1000 ký tự."),
    ])
    base_price = DecimalField("Giá mỗi đêm (₫)", places=0, validators=[
        DataRequired(message="Vui lòng nhập giá."),
        NumberRange(min=1, max=100000000, message="Giá phải từ 1 đến 100.000.000 ₫."),
    ])
    capacity = IntegerField("Sức chứa (người)", validators=[
        DataRequired(message="Vui lòng nhập sức chứa."),
        NumberRange(min=1, max=20, message="Sức chứa từ 1 đến 20 người."),
    ])
    image = FileField("Ảnh bìa (ảnh đầu tiên trong carousel)", validators=[
        Optional(),
        FileAllowed(["png", "jpg", "jpeg", "webp"],
                    message="Chỉ chấp nhận ảnh png, jpg, webp."),
    ])
    extra_images = MultipleFileField("Thêm ảnh khác (có thể chọn nhiều)", validators=[
        Optional(),
    ])
    amenity_ids = SelectMultipleField("Tiện nghi", coerce=int, choices=[],
                                      validators=[Optional()])
    submit = SubmitField("Lưu loại phòng")


class AmenityForm(FlaskForm):
    name = StringField("Tên tiện nghi", validators=[
        DataRequired(message="Vui lòng nhập tên tiện nghi."),
        Length(min=2, max=80, message="Tên từ 2 đến 80 ký tự."),
    ])
    icon = StringField("Biểu tượng (Bootstrap Icons)", validators=[
        Optional(),
        Length(max=50, message="Tối đa 50 ký tự."),
    ])
    submit = SubmitField("Lưu tiện nghi")