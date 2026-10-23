from flask import Blueprint

bookings_bp = Blueprint("bookings", __name__)

@bookings_bp.route("/")
def index():
    return "bookings stub"