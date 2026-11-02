from datetime import timedelta

from flask_jwt_extended import create_access_token
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db
from ..models import User

API_TOKEN_MINUTES = 15


class EmailTaken(ValueError):
    """Email đã có tài khoản."""


class WrongPassword(ValueError):
    """Mật khẩu hiện tại không đúng."""


def authenticate(email: str, password: str):
    """Trả User nếu đúng email + mật khẩu và tài khoản còn hoạt động, ngược lại None."""
    user = db.session.execute(
        db.select(User).filter_by(email=email.strip().lower(), is_active=True)
    ).scalar_one_or_none()
    if user and check_password_hash(user.password_hash, password):
        return user
    return None


def register_customer(full_name: str, email: str, phone: str, password: str) -> User:
    """Đăng ký công khai: luôn tạo customer."""
    email = email.strip().lower()
    if db.session.execute(db.select(User.id).filter_by(email=email)).first():
        raise EmailTaken("Email đã được sử dụng.")
    user = User(
        full_name=full_name.strip(),
        email=email,
        phone=(phone or "").strip() or None,
        password_hash=generate_password_hash(password),
        role="customer",
    )
    try:
        db.session.add(user)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise EmailTaken("Email đã được sử dụng.") from None
    except Exception:
        db.session.rollback()
        raise
    return user


def change_password(user: User, old_password: str, new_password: str) -> None:
    if not check_password_hash(user.password_hash, old_password):
        raise WrongPassword("Mật khẩu hiện tại không đúng.")
    try:
        user.password_hash = generate_password_hash(new_password)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def update_profile(user: User, full_name: str, phone: str) -> None:
    try:
        user.full_name = full_name.strip()
        user.phone = (phone or "").strip() or None
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def issue_api_token(user: User) -> tuple[str, int]:
    """JWT ngắn hạn (15 phút) cho AJAX. Trả (token, số giây hiệu lực)."""
    token = create_access_token(
        identity=str(user.id),
        additional_claims={"role": user.role},
        expires_delta=timedelta(minutes=API_TOKEN_MINUTES),
    )
    return token, API_TOKEN_MINUTES * 60