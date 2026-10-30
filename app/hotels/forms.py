from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, SubmitField
from wtforms.validators import Optional


class HotelSearchForm(FlaskForm):
    q = StringField("Tìm kiếm", validators=[Optional()])
    province = SelectField("Tỉnh/Thành phố", choices=[], validators=[Optional()])
    star = SelectField("Số sao", choices=[
        ("", "Tất cả"),
        ("1", "1 sao"), ("2", "2 sao"), ("3", "3 sao"),
        ("4", "4 sao"), ("5", "5 sao"),
    ], validators=[Optional()])
    submit = SubmitField("Tìm")