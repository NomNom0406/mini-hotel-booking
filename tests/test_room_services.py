import os
from uuid import uuid4

import pytest
from flask import current_app
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import NotFound

from app.extensions import db
from app.models import Amenity, Hotel, Room, RoomType
from app.rooms.services import (
    AmenityNameTaken,
    RoomNumberTaken,
    RoomTypeNameTaken,
    RuleViolation,
    all_hotel_choices,
    create_amenity,
    create_room,
    create_room_type,
    delete_amenity,
    get_active_room,
    hotel_room_type_choices,
    list_amenities_admin,
    list_available_rooms,
    list_hotel_rooms,
    list_room_types_admin,
    list_rooms_admin,
    room_is_free,
    room_type_choices,
    room_type_gallery,
    set_room_active,
    update_amenity,
    update_room,
    update_room_type,
)
from tests.room_helpers import (  # noqa: F401  (fixture được import để pytest nhận ra)
    add_room,
    clean_bookings,
    future,
    get_amenity,
    get_room,
    get_type,
    make_booking,
    scratch,
)


def _boom():
    raise RuntimeError("commit lỗi giả lập")


def _duplicate():
    raise IntegrityError("INSERT", {}, Exception("duplicate"))


def _room_data(info, number="T200", floor=2, type_id=None, hotel_id=None):
    return {
        "hotel_id": hotel_id or info.hotel_id,
        "room_type_id": type_id or info.type_id,
        "room_number": number,
        "floor": floor,
    }


def _type_data(info, name="Loại Mới", description="Mô tả", price=700000, capacity=3,
               hotel_id=None):
    return {
        "hotel_id": hotel_id or info.hotel_id,
        "name": name,
        "description": description,
        "base_price": price,
        "capacity": capacity,
    }


# ─── Công khai: danh sách chọn, danh sách phòng, phòng trống ────────────────

def test_hotel_room_type_choices_sorted_by_price(scratch):
    info = scratch.hotel()
    cheap = RoomType(hotel_id=info.hotel_id, name="Rẻ", base_price=100000, capacity=1)
    db.session.add(cheap)
    db.session.commit()
    assert hotel_room_type_choices(info.hotel_id) == [
        (str(cheap.id), "Rẻ"), (str(info.type_id), "Tmp Type")]
    assert hotel_room_type_choices(999999) == []


def test_list_hotel_rooms_hides_inactive_rooms_and_sorts_by_number(scratch):
    info = scratch.hotel()
    add_room(info, "T103")
    add_room(info, "T102", active=False)
    result = list_hotel_rooms(info.hotel_id)
    assert [r.room_number for r in result.items] == ["T101", "T103"]
    assert result.total == 2


def test_list_hotel_rooms_filters_by_guests_type_and_price(scratch):
    info = scratch.hotel()
    add_room(info, "T102")
    hotel_id = info.hotel_id
    assert list_hotel_rooms(hotel_id, guests=3).total == 0  # sức chứa chỉ 2
    assert list_hotel_rooms(hotel_id, guests=2).total == 2
    assert list_hotel_rooms(hotel_id, room_type_id=info.type_id).total == 2
    assert list_hotel_rooms(hotel_id, room_type_id=999999).total == 0
    assert list_hotel_rooms(hotel_id, price_min=600000).total == 0
    assert list_hotel_rooms(hotel_id, price_max=400000).total == 0
    assert list_hotel_rooms(hotel_id, price_min=500000, price_max=500000).total == 2


def test_list_hotel_rooms_excludes_booked_rooms_for_given_dates(scratch):
    info = scratch.hotel()
    second = add_room(info, "T102")
    make_booking(info.room_id, future(30), future(33))
    ci, co = future(31).isoformat(), future(34).isoformat()
    result = list_hotel_rooms(info.hotel_id, checkin=ci, checkout=co)
    assert [r.id for r in result.items] == [second]
    # Nhận phòng đúng ngày booking kia trả phòng: cả hai phòng đều trống
    adjacent = list_hotel_rooms(info.hotel_id, checkin=future(33).isoformat(),
                                checkout=future(35).isoformat())
    assert adjacent.total == 2


def test_list_hotel_rooms_ignores_invalid_or_partial_dates(scratch):
    info = scratch.hotel()
    add_room(info, "T102")
    make_booking(info.room_id, future(30), future(33))
    assert list_hotel_rooms(info.hotel_id, checkin="abc", checkout="xyz").total == 2
    assert list_hotel_rooms(info.hotel_id, checkin=future(31).isoformat()).total == 2


def test_list_hotel_rooms_pagination_is_safe(scratch):
    info = scratch.hotel()
    add_room(info, "T102")
    first = list_hotel_rooms(info.hotel_id, page=1, per_page=1)
    assert len(first.items) == 1
    assert first.total == 2
    assert len(list_hotel_rooms(info.hotel_id, page=0, per_page=1).items) == 1
    assert len(list_hotel_rooms(info.hotel_id, page=None, per_page=1).items) == 1


def test_get_active_room(scratch):
    info = scratch.hotel()
    assert get_active_room(info.room_id).id == info.room_id
    hidden = add_room(info, "T102", active=False)
    with pytest.raises(NotFound):
        get_active_room(hidden)
    with pytest.raises(NotFound):
        get_active_room(999999)
    inactive_hotel = scratch.hotel(active=False)
    with pytest.raises(NotFound):
        get_active_room(inactive_hotel.room_id)


def test_room_is_free(scratch):
    info = scratch.hotel()
    ci, co = future(30), future(33)
    assert room_is_free(info.room_id, ci, co) is True
    booking = make_booking(info.room_id, ci, co)
    assert room_is_free(info.room_id, future(31), future(34)) is False
    assert room_is_free(info.room_id, co, future(35)) is True  # nhận đúng ngày trả
    booking.status = "Cancelled"
    db.session.commit()
    assert room_is_free(info.room_id, ci, co) is True


def test_list_available_rooms_filters_and_skips_inactive_hotel(scratch):
    info = scratch.hotel(price=300000)
    hidden_hotel = scratch.hotel(active=False)
    ci, co = future(30), future(32)

    ids = [r.id for r in list_available_rooms(ci, co)]
    assert info.room_id in ids
    assert hidden_hotel.room_id not in ids

    assert [r.id for r in list_available_rooms(ci, co, hotel_id=info.hotel_id)] == [info.room_id]
    assert list_available_rooms(ci, co, hotel_id=info.hotel_id, guests=3) == []
    assert list_available_rooms(ci, co, hotel_id=info.hotel_id, max_price=100000) == []
    assert [r.id for r in list_available_rooms(
        ci, co, hotel_id=info.hotel_id, room_type_id=info.type_id, max_price=300000)
    ] == [info.room_id]

    make_booking(info.room_id, ci, co)
    assert list_available_rooms(ci, co, hotel_id=info.hotel_id) == []


# ─── Danh sách chọn cho form admin ──────────────────────────────────────────

def test_all_hotel_choices_sorted_and_contains_scratch_hotel(scratch):
    info = scratch.hotel()
    choices = all_hotel_choices()
    assert (info.hotel_id, info.hotel_name) in choices
    names = [name for _, name in choices]
    assert names == sorted(names)


def test_room_type_choices_label_includes_hotel_name(scratch):
    info = scratch.hotel()
    assert (info.type_id, f"{info.hotel_name} — Tmp Type") in room_type_choices()


# ─── Quản lý phòng ──────────────────────────────────────────────────────────

def test_list_rooms_admin_filters_by_hotel_and_paginates(scratch):
    info = scratch.hotel()
    add_room(info, "T102", active=False)  # admin thấy cả phòng đã ẩn
    result = list_rooms_admin(info.hotel_id)
    assert result.total == 2
    assert len(list_rooms_admin(info.hotel_id, page=1, per_page=1).items) == 1
    assert list_rooms_admin(info.hotel_id, page=0).total == 2
    assert list_rooms_admin().total >= 2


def test_create_room_success_strips_number(scratch):
    info = scratch.hotel()
    room = create_room(_room_data(info, number="  T200  ", floor=2))
    done = get_room(room.id)
    assert done.room_number == "T200"
    assert done.floor == 2
    assert done.is_active is True


def test_create_room_duplicate_number_is_rejected(scratch):
    info = scratch.hotel()
    with pytest.raises(RoomNumberTaken):
        create_room(_room_data(info, number="T101"))
    same_number_other_hotel = scratch.hotel()
    created = create_room(_room_data(same_number_other_hotel, number="T555"))
    assert created.id  # số phòng chỉ cần duy nhất trong từng khách sạn


def test_create_room_rejects_type_of_other_hotel_or_unknown_type(scratch):
    info, other = scratch.hotel(), scratch.hotel()
    with pytest.raises(RuleViolation):
        create_room(_room_data(info, number="T300", type_id=other.type_id))
    with pytest.raises(RuleViolation):
        create_room(_room_data(info, number="T300", type_id=999999))


def test_create_room_error_branches_roll_back(scratch, monkeypatch):
    info = scratch.hotel()
    monkeypatch.setattr(db.session, "commit", _duplicate)
    with pytest.raises(RoomNumberTaken):
        create_room(_room_data(info, number="T400"))
    monkeypatch.setattr(db.session, "commit", _boom)
    with pytest.raises(RuntimeError, match="commit lỗi"):
        create_room(_room_data(info, number="T400"))
    monkeypatch.undo()
    db.session.expire_all()
    assert db.session.execute(select(Room.id).filter_by(
        hotel_id=info.hotel_id, room_number="T400")).first() is None


def test_update_room_success_and_keeping_own_number(scratch):
    info = scratch.hotel()
    update_room(get_room(info.room_id), _room_data(info, number="T101", floor=5))
    assert get_room(info.room_id).floor == 5
    update_room(get_room(info.room_id), _room_data(info, number="  T150 ", floor=5))
    assert get_room(info.room_id).room_number == "T150"


def test_update_room_duplicate_number_is_rejected(scratch):
    info = scratch.hotel()
    add_room(info, "T102")
    with pytest.raises(RoomNumberTaken):
        update_room(get_room(info.room_id), _room_data(info, number="T102"))
    assert get_room(info.room_id).room_number == "T101"


def test_update_room_move_hotel_blocked_when_it_has_bookings(scratch):
    info, target = scratch.hotel(), scratch.hotel(with_room=False)
    booking = make_booking(info.room_id, future(30), future(32))
    data = _room_data(info, number="T101", type_id=target.type_id, hotel_id=target.hotel_id)
    with pytest.raises(RuleViolation):
        update_room(get_room(info.room_id), data)
    assert get_room(info.room_id).hotel_id == info.hotel_id
    booking.status = "Cancelled"  # booking vẫn tồn tại nên vẫn bị chặn
    db.session.commit()
    with pytest.raises(RuleViolation):
        update_room(get_room(info.room_id), data)


def test_update_room_move_hotel_allowed_without_bookings(scratch):
    info, target = scratch.hotel(), scratch.hotel(with_room=False)
    data = _room_data(info, number="T101", type_id=target.type_id, hotel_id=target.hotel_id)
    update_room(get_room(info.room_id), data)
    assert get_room(info.room_id).hotel_id == target.hotel_id


def test_update_room_error_branches_roll_back(scratch, monkeypatch):
    info = scratch.hotel()
    room = get_room(info.room_id)
    monkeypatch.setattr(db.session, "commit", _duplicate)
    with pytest.raises(RoomNumberTaken):
        update_room(room, _room_data(info, number="T101", floor=9))
    monkeypatch.setattr(db.session, "commit", _boom)
    with pytest.raises(RuntimeError, match="commit lỗi"):
        update_room(get_room(info.room_id), _room_data(info, number="T101", floor=9))
    monkeypatch.undo()
    assert get_room(info.room_id).floor == 1


def test_set_room_active_toggles_and_rolls_back(scratch, monkeypatch):
    info = scratch.hotel()
    set_room_active(get_room(info.room_id), False)
    assert get_room(info.room_id).is_active is False
    set_room_active(get_room(info.room_id), True)
    assert get_room(info.room_id).is_active is True
    monkeypatch.setattr(db.session, "commit", _boom)
    with pytest.raises(RuntimeError, match="commit lỗi"):
        set_room_active(get_room(info.room_id), False)
    monkeypatch.undo()
    assert get_room(info.room_id).is_active is True


# ─── Quản lý loại phòng ─────────────────────────────────────────────────────

def test_list_room_types_admin_returns_room_counts(scratch):
    info = scratch.hotel()
    add_room(info, "T102")
    room_types, counts = list_room_types_admin(info.hotel_id)
    assert [t.id for t in room_types] == [info.type_id]
    assert counts[info.type_id] == 2
    all_types, _ = list_room_types_admin()
    assert info.type_id in [t.id for t in all_types]


def test_create_room_type_success_with_amenities_and_image(scratch):
    info = scratch.hotel(with_type=False)
    amenity = scratch.amenity()
    room_type = create_room_type(
        _type_data(info, name="  Loại Mới  ", description="  Mô tả  "),
        [amenity.id], image_filename="uploads/x.jpg")
    done = get_type(room_type.id)
    assert done.name == "Loại Mới"
    assert done.description == "Mô tả"
    assert float(done.base_price) == 700000.0
    assert done.capacity == 3
    assert done.image_filename == "uploads/x.jpg"
    assert [a.name for a in done.amenities] == [amenity.name]


def test_create_room_type_blank_description_and_no_amenities(scratch):
    info = scratch.hotel(with_type=False)
    room_type = create_room_type(_type_data(info, description="   "), None)
    done = get_type(room_type.id)
    assert done.description is None
    assert done.amenities == []
    assert done.image_filename is None


def test_create_room_type_rule_violations(scratch):
    info = scratch.hotel()
    with pytest.raises(RuleViolation):
        create_room_type(_type_data(info, hotel_id=999999), [])
    with pytest.raises(RoomTypeNameTaken):
        create_room_type(_type_data(info, name="Tmp Type"), [])


def test_create_room_type_error_branches_roll_back(scratch, monkeypatch):
    info = scratch.hotel(with_type=False)
    monkeypatch.setattr(db.session, "commit", _duplicate)
    with pytest.raises(RoomTypeNameTaken):
        create_room_type(_type_data(info, name="Không Lưu"), [])
    monkeypatch.setattr(db.session, "commit", _boom)
    with pytest.raises(RuntimeError, match="commit lỗi"):
        create_room_type(_type_data(info, name="Không Lưu"), [])
    monkeypatch.undo()
    db.session.expire_all()
    assert db.session.execute(select(RoomType.id).filter_by(
        hotel_id=info.hotel_id, name="Không Lưu")).first() is None


def test_update_room_type_success_replaces_amenities(scratch):
    info = scratch.hotel()
    first, second = scratch.amenity(), scratch.amenity()
    update_room_type(get_type(info.type_id),
                     _type_data(info, name="Tmp Type", price=800000, capacity=4),
                     [first.id])
    done = get_type(info.type_id)
    assert float(done.base_price) == 800000.0
    assert done.capacity == 4
    assert [a.name for a in done.amenities] == [first.name]
    update_room_type(get_type(info.type_id), _type_data(info, name="Tmp Type"), [second.id])
    assert [a.name for a in get_type(info.type_id).amenities] == [second.name]
    update_room_type(get_type(info.type_id), _type_data(info, name="Tmp Type"), [])
    assert get_type(info.type_id).amenities == []


def test_update_room_type_duplicate_name_rejected_but_own_name_allowed(scratch):
    info = scratch.hotel()
    other = RoomType(hotel_id=info.hotel_id, name="Loại Khác", base_price=100000, capacity=1)
    db.session.add(other)
    db.session.commit()
    with pytest.raises(RoomTypeNameTaken):
        update_room_type(get_type(info.type_id), _type_data(info, name="Loại Khác"), [])
    update_room_type(get_type(info.type_id), _type_data(info, name="Tmp Type"), [])


def test_update_room_type_move_hotel_blocked_when_it_has_rooms(scratch):
    info, target = scratch.hotel(), scratch.hotel(with_type=False)
    data = _type_data(info, name="Tmp Type", hotel_id=target.hotel_id)
    with pytest.raises(RuleViolation):
        update_room_type(get_type(info.type_id), data, [])
    assert get_type(info.type_id).hotel_id == info.hotel_id
    empty = scratch.hotel(with_room=False)  # loại phòng chưa có phòng thì chuyển được
    update_room_type(get_type(empty.type_id),
                     _type_data(empty, name="Tmp Type", hotel_id=target.hotel_id), [])
    assert get_type(empty.type_id).hotel_id == target.hotel_id


def test_update_room_type_deletes_old_image_only_when_replaced(scratch, monkeypatch):
    info = scratch.hotel()
    deleted = []
    monkeypatch.setattr("app.rooms.services.delete_image", deleted.append)
    room_type = get_type(info.type_id)
    room_type.image_filename = "old.jpg"
    db.session.commit()

    update_room_type(get_type(info.type_id), _type_data(info, name="Tmp Type"), [])
    assert deleted == []
    assert get_type(info.type_id).image_filename == "old.jpg"

    update_room_type(get_type(info.type_id), _type_data(info, name="Tmp Type"), [],
                     image_filename="old.jpg")
    assert deleted == []

    update_room_type(get_type(info.type_id), _type_data(info, name="Tmp Type"), [],
                     image_filename="new.jpg")
    assert deleted == ["old.jpg"]
    assert get_type(info.type_id).image_filename == "new.jpg"


def test_update_room_type_error_branches_roll_back(scratch, monkeypatch):
    info = scratch.hotel()
    monkeypatch.setattr(db.session, "commit", _duplicate)
    with pytest.raises(RoomTypeNameTaken):
        update_room_type(get_type(info.type_id),
                         _type_data(info, name="Tmp Type", capacity=9), [])
    monkeypatch.setattr(db.session, "commit", _boom)
    with pytest.raises(RuntimeError, match="commit lỗi"):
        update_room_type(get_type(info.type_id),
                         _type_data(info, name="Tmp Type", capacity=9), [])
    monkeypatch.undo()
    assert get_type(info.type_id).capacity == 2


# ─── Quản lý tiện nghi ──────────────────────────────────────────────────────

def test_list_amenities_admin_counts_hotels_and_room_types(scratch):
    info = scratch.hotel()
    amenity = scratch.amenity()
    create_room_type(_type_data(info, name="Có Tiện Nghi"), [amenity.id])
    hotel = db.session.get(Hotel, info.hotel_id)
    hotel.amenities = [db.session.get(Amenity, amenity.id)]
    db.session.commit()

    amenities, hotel_counts, type_counts = list_amenities_admin()
    names = [a.name for a in amenities]
    assert amenity.name in names
    assert names == sorted(names)
    assert hotel_counts[amenity.id] == 1
    assert type_counts[amenity.id] == 1


def test_create_amenity_strips_name_and_blank_icon_becomes_none(scratch):
    name = "Tmp Amenity " + uuid4().hex[:8]
    amenity = create_amenity(f"  {name}  ", "   ")
    scratch.amenity_ids.append(amenity.id)
    done = get_amenity(amenity.id)
    assert done.name == name
    assert done.icon is None


def test_create_amenity_duplicate_name_is_rejected(scratch):
    existing = scratch.amenity()
    with pytest.raises(AmenityNameTaken):
        create_amenity(existing.name, "bi-star")


def test_create_amenity_error_branches_roll_back(scratch, monkeypatch):
    name = "Tmp Amenity " + uuid4().hex[:8]
    monkeypatch.setattr(db.session, "commit", _duplicate)
    with pytest.raises(AmenityNameTaken):
        create_amenity(name, "bi-star")
    monkeypatch.setattr(db.session, "commit", _boom)
    with pytest.raises(RuntimeError, match="commit lỗi"):
        create_amenity(name, "bi-star")
    monkeypatch.undo()
    db.session.expire_all()
    assert db.session.execute(select(Amenity.id).filter_by(name=name)).first() is None


def test_update_amenity_success_and_duplicate(scratch):
    first, second = scratch.amenity(), scratch.amenity()
    new_name = "Tmp Amenity " + uuid4().hex[:8]
    update_amenity(get_amenity(first.id), f" {new_name} ", "bi-wifi")
    done = get_amenity(first.id)
    assert done.name == new_name
    assert done.icon == "bi-wifi"
    update_amenity(get_amenity(first.id), new_name, "")  # giữ nguyên tên của chính nó
    assert get_amenity(first.id).icon is None
    with pytest.raises(AmenityNameTaken):
        update_amenity(get_amenity(first.id), second.name, "bi-star")


def test_update_amenity_error_branches_roll_back(scratch, monkeypatch):
    amenity = scratch.amenity()
    monkeypatch.setattr(db.session, "commit", _duplicate)
    with pytest.raises(AmenityNameTaken):
        update_amenity(get_amenity(amenity.id), "Tên Không Lưu", "bi-x")
    monkeypatch.setattr(db.session, "commit", _boom)
    with pytest.raises(RuntimeError, match="commit lỗi"):
        update_amenity(get_amenity(amenity.id), "Tên Không Lưu", "bi-x")
    monkeypatch.undo()
    assert get_amenity(amenity.id).name == amenity.name


def test_delete_amenity_removes_it_and_rolls_back_on_failure(scratch, monkeypatch):
    keep, gone = scratch.amenity(), scratch.amenity()
    monkeypatch.setattr(db.session, "commit", _boom)
    with pytest.raises(RuntimeError, match="commit lỗi"):
        delete_amenity(get_amenity(keep.id))
    monkeypatch.undo()
    assert get_amenity(keep.id) is not None
    delete_amenity(get_amenity(gone.id))
    assert get_amenity(gone.id) is None


# ─── room_type_gallery ──────────────────────────────────────────────────────

def _make_gallery_dir(scratch):
    folder_name = "tmp-gallery-" + uuid4().hex[:8]
    abs_dir = os.path.join(os.path.abspath(current_app.static_folder), "uploads", folder_name)
    os.makedirs(abs_dir)
    scratch.dirs.append(abs_dir)
    for name in ("cover.jpg", "b.png", "a.webp", "notes.txt"):
        with open(os.path.join(abs_dir, name), "w", encoding="utf-8") as handle:
            handle.write("x")
    os.makedirs(os.path.join(abs_dir, "dir.jpg"))  # thư mục có đuôi ảnh: phải bị bỏ qua
    return f"uploads/{folder_name}"


def test_room_type_gallery_empty_and_bare_filename():
    assert room_type_gallery(None) == []
    assert room_type_gallery("") == []
    assert room_type_gallery("abc.jpg") == ["uploads/abc.jpg"]
    assert room_type_gallery("uploads/abc.jpg") == ["uploads/abc.jpg"]


def test_room_type_gallery_lists_cover_first_then_other_images(scratch):
    folder = _make_gallery_dir(scratch)
    cover = f"{folder}/cover.jpg"
    assert room_type_gallery(cover) == [cover, f"{folder}/a.webp", f"{folder}/b.png"]
    assert room_type_gallery(cover.replace("/", "\\")) == [
        cover, f"{folder}/a.webp", f"{folder}/b.png"]
    other_cover = f"{folder}/b.png"
    assert room_type_gallery(other_cover)[0] == other_cover


def test_room_type_gallery_missing_folder_and_path_traversal():
    missing = "uploads/khong-ton-tai-" + uuid4().hex[:8] + "/cover.jpg"
    assert room_type_gallery(missing) == [missing]
    escaping = "uploads/../x.jpg"
    assert room_type_gallery(escaping) == [escaping]