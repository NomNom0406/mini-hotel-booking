from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash

from app.admin.services import (
    SELF_PROTECT_MSG,
    create_receptionist,
    list_users,
    set_user_active,
    update_user,
)
from app.auth.services import EmailTaken
from app.extensions import db
from app.models import User

ADMIN = "admin@test.com"
PASSWORD = "Password123!"


def _user(email):
    return db.session.execute(select(User).filter_by(email=email)).scalar_one()


def _new_email():
    return f"tmp-{uuid4().hex[:8]}@test.com"


def _delete_user(user_id):
    db.session.rollback()
    db.session.execute(delete(User).where(User.id == user_id))
    db.session.commit()


def _boom():
    raise RuntimeError("commit lỗi giả lập")


def _reload(user_id):
    db.session.expire_all()
    return db.session.get(User, user_id)


@pytest.fixture
def temp_user(app):
    """Lễ tân tạm để sửa/khóa, không đụng vào tài khoản test dùng chung."""
    user = create_receptionist("Lễ Tân Tạm", _new_email(), "0911111111", PASSWORD)
    user_id = user.id
    yield user
    _delete_user(user_id)


# ─── list_users ─────────────────────────────────────────────────────────────

def test_list_users_returns_newest_first(app, temp_user):
    users = list_users()
    emails = [u.email for u in users]
    assert users[0].id == temp_user.id
    assert "admin@test.com" in emails
    assert "customer@test.com" in emails


# ─── create_receptionist ────────────────────────────────────────────────────

def test_create_receptionist_normalizes_input_and_hashes_password(app):
    email = _new_email()
    user = create_receptionist("  Lễ Tân Mới  ", f"  {email.upper()}  ", "", PASSWORD)
    user_id = user.id
    try:
        assert user.email == email
        assert user.full_name == "Lễ Tân Mới"
        assert user.role == "receptionist"
        assert user.is_active is True
        assert user.phone is None
        assert user.password_hash != PASSWORD
        assert check_password_hash(user.password_hash, PASSWORD)
    finally:
        _delete_user(user_id)


def test_create_receptionist_strips_phone(app):
    user = create_receptionist("Lễ Tân Mới", _new_email(), "  0912345678 ", PASSWORD)
    user_id = user.id
    try:
        assert user.phone == "0912345678"
    finally:
        _delete_user(user_id)


def test_create_receptionist_duplicate_email_is_rejected_case_insensitive(app, temp_user):
    with pytest.raises(EmailTaken, match="đã được sử dụng"):
        create_receptionist("Người Khác", temp_user.email.upper(), "", PASSWORD)


def test_create_receptionist_integrity_error_becomes_email_taken(app, monkeypatch):
    email = _new_email()

    def duplicate():
        raise IntegrityError("INSERT", {}, Exception("duplicate"))

    monkeypatch.setattr(db.session, "commit", duplicate)
    with pytest.raises(EmailTaken):
        create_receptionist("Tên", email, "", PASSWORD)
    monkeypatch.undo()
    db.session.expire_all()
    assert db.session.execute(select(User.id).filter_by(email=email)).first() is None


def test_create_receptionist_unexpected_error_is_reraised_and_rolled_back(app, monkeypatch):
    email = _new_email()
    monkeypatch.setattr(db.session, "commit", _boom)
    with pytest.raises(RuntimeError, match="commit lỗi"):
        create_receptionist("Tên", email, "", PASSWORD)
    monkeypatch.undo()
    db.session.expire_all()
    assert db.session.execute(select(User.id).filter_by(email=email)).first() is None


# ─── update_user ────────────────────────────────────────────────────────────

def test_update_user_changes_name_role_and_active(app, temp_user):
    admin, user_id = _user(ADMIN), temp_user.id
    update_user(temp_user, admin, "  Tên Mới  ", "customer", False)
    done = _reload(user_id)
    assert done.full_name == "Tên Mới"
    assert done.role == "customer"
    assert done.is_active is False


def test_update_user_rejects_invalid_role(app, temp_user):
    admin, user_id = _user(ADMIN), temp_user.id
    with pytest.raises(ValueError, match="Vai trò"):
        update_user(temp_user, admin, "Tên Mới", "superuser", True)
    assert _reload(user_id).role == "receptionist"


def test_update_user_self_protection(app, temp_user):
    user_id = temp_user.id
    with pytest.raises(PermissionError, match="tự hạ"):
        update_user(temp_user, temp_user, "Tên", "customer", True)
    with pytest.raises(PermissionError):
        update_user(temp_user, temp_user, "Tên", "receptionist", False)
    done = _reload(user_id)
    assert done.role == "receptionist"
    assert done.is_active is True
    assert SELF_PROTECT_MSG.startswith("Bạn không thể")


def test_update_user_self_can_rename_without_changing_role_or_status(app, temp_user):
    user_id = temp_user.id
    update_user(temp_user, temp_user, "Tên Khác", "receptionist", True)
    assert _reload(user_id).full_name == "Tên Khác"


def test_update_user_rolls_back_when_commit_fails(app, temp_user, monkeypatch):
    admin, user_id = _user(ADMIN), temp_user.id
    monkeypatch.setattr(db.session, "commit", _boom)
    with pytest.raises(RuntimeError, match="commit lỗi"):
        update_user(temp_user, admin, "Không Lưu", "customer", False)
    monkeypatch.undo()
    done = _reload(user_id)
    assert done.full_name != "Không Lưu"
    assert done.role == "receptionist"
    assert done.is_active is True


# ─── set_user_active ────────────────────────────────────────────────────────

def test_set_user_active_locks_and_unlocks(app, temp_user):
    admin, user_id = _user(ADMIN), temp_user.id
    set_user_active(temp_user, admin, False)
    assert _reload(user_id).is_active is False
    set_user_active(temp_user, admin, True)
    assert _reload(user_id).is_active is True


def test_set_user_active_cannot_lock_yourself(app, temp_user):
    user_id = temp_user.id
    with pytest.raises(PermissionError, match="tự hạ"):
        set_user_active(temp_user, temp_user, False)
    assert _reload(user_id).is_active is True
    set_user_active(temp_user, temp_user, True)  # mở khóa chính mình thì được


def test_set_user_active_rolls_back_when_commit_fails(app, temp_user, monkeypatch):
    admin, user_id = _user(ADMIN), temp_user.id
    monkeypatch.setattr(db.session, "commit", _boom)
    with pytest.raises(RuntimeError, match="commit lỗi"):
        set_user_active(temp_user, admin, False)
    monkeypatch.undo()
    assert _reload(user_id).is_active is True