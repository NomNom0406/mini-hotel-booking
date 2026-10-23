from flask import Blueprint

rooms_bp = Blueprint("rooms", __name__)

@rooms_bp.route("/")
def index():
    return "rooms stub"