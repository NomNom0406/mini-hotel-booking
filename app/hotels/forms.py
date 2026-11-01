from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, SubmitField, IntegerField
from wtforms.validators import Optional, NumberRange


class HotelSearchForm(FlaskForm):
    province = SelectField("Điểm đến", choices=[], validators=[Optional()])
    checkin  = StringField("Ngày nhận", validators=[Optional()])
    checkout = StringField("Ngày trả",  validators=[Optional()])
    guests   = IntegerField("Số khách", validators=[Optional(), NumberRange(min=1)],
                            default=1)
    submit   = SubmitField("Tìm kiếm")