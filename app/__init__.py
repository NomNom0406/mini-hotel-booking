import os
from flask import Flask
from .config import config_map
from .extensions import db, migrate, login_manager, csrf, jwt, limiter

def create_app(env: str | None = None) -> Flask:
    if env is None:
        env = os.getenv("FLASK_ENV", "development")

    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )
    app.config.from_object(config_map[env])

    # Khởi tạo extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    jwt.init_app(app)
    limiter.init_app(app)

    # Import models để migrate nhận biết
    with app.app_context():
        from . import models  # noqa: F401

    # Đăng ký blueprints
    _register_blueprints(app)

    return app


def _register_blueprints(app: Flask) -> None:
    from .auth.routes     import auth_bp
    from .hotels.routes   import hotels_bp
    from .rooms.routes    import rooms_bp
    from .bookings.routes import bookings_bp
    from .admin.routes    import admin_bp
    from .api.routes      import api_bp

    app.register_blueprint(auth_bp,     url_prefix="/auth")
    app.register_blueprint(hotels_bp,   url_prefix="/hotels")
    app.register_blueprint(rooms_bp,    url_prefix="/rooms")
    app.register_blueprint(bookings_bp, url_prefix="/bookings")
    app.register_blueprint(admin_bp,    url_prefix="/admin")
    app.register_blueprint(api_bp,      url_prefix="/api")