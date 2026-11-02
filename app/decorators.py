from functools import wraps
from flask import abort, current_app, request
from flask_login import current_user
from .extensions import login_manager
from .models import Booking

#  Ma trận quyền — nguồn sự thật duy nhất          
#  test_permissions.py đọc dict này để verify 

PERMISSIONS: dict[str, set[str]] = {
    "admin": {
        "booking.view_all",
        "booking.change_status",
        "booking.calendar",
        "hotel.manage",
        "room.manage",
        "dashboard.view",
        "user.manage",
    },
    "receptionist": {
        "booking.view_all",
        "booking.change_status",
        "booking.calendar",
    },
    "customer": set(),
}

def roles_required(*roles: str):
    """Kiểm tra theo vai trò. Dùng cho route chỉ dành cho nhóm vai trò cố định.
    Ví dụ: @roles_required('admin', 'receptionist')
    """
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return login_manager.unauthorized()
            if current_user.role not in roles:
                current_app.logger.warning(
                    "DENY role | user=%s role=%s path=%s need=%s",
                    current_user.id, current_user.role, request.path, roles,
                )
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def permission_required(permission: str):
    """Kiểm tra quyền chi tiết theo bảng PERMISSIONS.
    Dùng cho dashboard, confirm booking, manage user...
    """
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return login_manager.unauthorized()
            allowed = PERMISSIONS.get(current_user.role, set())
            if permission not in allowed:
                current_app.logger.warning(
                    "DENY perm | user=%s role=%s path=%s perm=%s",
                    current_user.id, current_user.role, request.path, permission,
                )
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator

def booking_owner_or_staff(view):
    """Chống IDOR: customer chỉ truy cập booking của chính mình.
    Admin/Receptionist đi qua không cần kiểm tra.
    Route phải nhận tham số id hoặc booking_id.
    """
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return login_manager.unauthorized()
        if current_user.role in ("admin", "receptionist"):
            return view(*args, **kwargs)
        booking_id = kwargs.get("id") or kwargs.get("booking_id")
        booking = Booking.query.get_or_404(booking_id)
        if booking.user_id != current_user.id:
            current_app.logger.warning(
                "IDOR attempt | user=%s tried booking_id=%s",
                current_user.id, booking_id,
            )
            abort(403)
        return view(*args, **kwargs)
    return wrapped