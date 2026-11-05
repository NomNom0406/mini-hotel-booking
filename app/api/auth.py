from functools import wraps

from flask import current_app, g
from flask_jwt_extended import create_access_token, get_jwt_identity, verify_jwt_in_request

from ..extensions import db, jwt
from ..models import User
from .errors import ApiError, error_response


@jwt.unauthorized_loader
def _missing_token(reason):
    return error_response(401, "Thiếu token xác thực. Gửi header Authorization: Bearer <token>.")


@jwt.invalid_token_loader
def _invalid_token(reason):
    return error_response(401, "Token không hợp lệ.")


@jwt.expired_token_loader
def _expired_token(jwt_header, jwt_payload):
    return error_response(401, "Token đã hết hạn, hãy đăng nhập lại.")


def login_token(user):
    """Token cấp bởi POST /api/auth/login: sub = str(user.id), claim role, hạn theo JWT_ACCESS_TOKEN_EXPIRES."""
    token = create_access_token(identity=str(user.id),
                                additional_claims={"role": user.role})
    return token, int(current_app.config["JWT_ACCESS_TOKEN_EXPIRES"])


def api_user_required(*roles):
    """Yêu cầu JWT hợp lệ; nạp user từ DB; nếu có roles thì phải thuộc một trong các vai trò đó."""
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            try:
                user_id = int(get_jwt_identity())
            except (TypeError, ValueError):
                raise ApiError(401, "Token không hợp lệ.") from None
            user = db.session.get(User, user_id)
            if user is None or not user.is_active:
                raise ApiError(401, "Tài khoản không tồn tại hoặc đã bị khóa.")
            if roles and user.role not in roles:
                raise ApiError(403, "Bạn không có quyền thực hiện thao tác này.")
            g.api_user = user
            return view(*args, **kwargs)
        return wrapper
    return decorator


def current_api_user():
    return g.api_user