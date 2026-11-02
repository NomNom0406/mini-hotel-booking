from datetime import date

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import (
    IntegerField, SelectField, SelectMultipleField, StringField,
    SubmitField, TextAreaField,
)
from wtforms.validators import DataRequired, Length, NumberRange, Optional, URL


class HotelSearchForm(FlaskForm):
    province = SelectField("Điểm đến", choices=[], validators=[Optional()])
    checkin  = StringField("Ngày nhận", validators=[Optional()])
    checkout = StringField("Ngày trả",  validators=[Optional()])
    guests   = IntegerField("Số khách", validators=[Optional(), NumberRange(min=1)],
                            default=1)
    submit   = SubmitField("Tìm kiếm")

    def validate(self, extra_validators=None):
        """Ngày bỏ trống cả hai thì hợp lệ; nếu chọn thì phải đủ cặp và ngày trả sau ngày nhận.

        Kiểm ở cấp form vì Optional() dừng chuỗi kiểm tra khi ô rỗng,
        nên hàm validate_<ô> không chạy được cho ô đang trống.
        """
        valid = super().validate(extra_validators)
        checkin = (self.checkin.data or "").strip()
        checkout = (self.checkout.data or "").strip()
        if not checkin and not checkout:
            return valid

        parsed = {}
        for field, value, label in ((self.checkin, checkin, "nhận"),
                                    (self.checkout, checkout, "trả")):
            if not value:
                field.errors.append(f"Vui lòng chọn ngày {label}.")
                continue
            try:
                parsed[field.name] = date.fromisoformat(value)
            except ValueError:
                field.errors.append(f"Ngày {label} không đúng định dạng.")

        if len(parsed) == 2 and parsed["checkout"] <= parsed["checkin"]:
            self.checkout.errors.append("Ngày trả phải sau ngày nhận.")

        return valid and not (self.checkin.errors or self.checkout.errors)


class HotelForm(FlaskForm):
    """Admin thêm/sửa khách sạn."""
    name = StringField("Tên khách sạn", validators=[
        DataRequired(message="Vui lòng nhập tên khách sạn."),
        Length(min=2, max=150, message="Tên từ 2 đến 150 ký tự."),
    ])
    province = StringField("Tỉnh/thành", validators=[
        DataRequired(message="Vui lòng nhập tỉnh/thành."),
        Length(min=2, max=80, message="Tỉnh/thành từ 2 đến 80 ký tự."),
    ])
    address = StringField("Địa chỉ", validators=[
        DataRequired(message="Vui lòng nhập địa chỉ."),
        Length(max=255, message="Địa chỉ tối đa 255 ký tự."),
    ])
    star_rating = SelectField(
        "Hạng sao", coerce=int,
        choices=[(n, f"{n} sao") for n in range(1, 6)], default=3,
    )
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
        FileAllowed(["png", "jpg", "jpeg", "webp"],
                    message="Chỉ chấp nhận ảnh png, jpg, webp."),
    ])
    amenity_ids = SelectMultipleField("Tiện nghi", coerce=int, choices=[],
                                      validators=[Optional()])
    submit = SubmitField("Lưu khách sạn")