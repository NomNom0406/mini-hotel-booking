from flask import Blueprint

hotels_bp = Blueprint("hotels", __name__)

@hotels_bp.route("/")
def index():
    return "hotels stub"