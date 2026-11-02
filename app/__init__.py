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

    # Đăng ký error handlers
    _register_error_handlers(app)

    # Lệnh CLI: flask seed
    from .seed import seed_command
    app.cli.add_command(seed_command)

    return app


def _register_error_handlers(app: Flask) -> None:
    from flask import render_template, request, jsonify

    @app.errorhandler(400)
    def bad_request(e):
        if request.path.startswith("/api/"):
            return jsonify(error={"code": 400, "message": "Bad request"}), 400
        return render_template("errors/400_csrf.html"), 400

    @app.errorhandler(403)
    def forbidden(e):
        if request.path.startswith("/api/"):
            return jsonify(error={"code": 403, "message": "Forbidden"}), 403
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith("/api/"):
            return jsonify(error={"code": 404, "message": "Not found"}), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(413)
    def too_large(e):
        from flask import flash, redirect, url_for
        if request.path.startswith("/api/"):
            return jsonify(error={"code": 413, "message": "Payload too large"}), 413
        flash("Tệp tải lên quá lớn (tối đa 2 MB).", "danger")
        return redirect(request.referrer or url_for("hotels.index"))

    @app.errorhandler(500)
    def internal_error(e):
        if request.path.startswith("/api/"):
            return jsonify(error={"code": 500, "message": "Internal server error"}), 500
        return render_template("errors/500.html"), 500


def _register_blueprints(app: Flask) -> None:
    from .auth.routes     import auth_bp
    from .hotels.routes   import hotels_bp
    from .rooms.routes    import rooms_bp
    from .bookings.routes import bookings_bp
    from .admin.routes    import admin_bp
    from .api.routes      import api_bp

    app.register_blueprint(auth_bp,     url_prefix="/auth")
    app.register_blueprint(hotels_bp,   url_prefix="")
    app.register_blueprint(rooms_bp,    url_prefix="")
    app.register_blueprint(bookings_bp, url_prefix="")
    app.register_blueprint(admin_bp,    url_prefix="/admin")
    app.register_blueprint(api_bp,      url_prefix="/api")