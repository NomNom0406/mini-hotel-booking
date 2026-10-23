import random
import string
from datetime import date
from werkzeug.security import generate_password_hash
from .extensions import db
from .models import User, Hotel, RoomType, Room, Amenity, Booking


def _random_code(n=8):
    return "BK" + "".join(random.choices(string.digits, k=n))


def _get_or_create_amenity(name, icon):
    a = Amenity.query.filter_by(name=name).first()
    if not a:
        a = Amenity(name=name, icon=icon)
        db.session.add(a)
    return a


def run_seed():
    # ------------------------------------------------------------------ #
    # 1. AMENITIES                                                         #
    # ------------------------------------------------------------------ #
    amenity_defs = [
        ("WiFi miễn phí",         "bi-wifi"),
        ("Phòng không hút thuốc", "bi-slash-circle"),
        ("Lễ tân 24 giờ",         "bi-clock"),
        ("Dịch vụ phòng",         "bi-bell"),
        ("Bãi đỗ xe miễn phí",    "bi-car-front"),
        ("Hồ bơi",                "bi-droplet"),
        ("Nhà hàng",              "bi-cup-hot"),
        ("Spa",                   "bi-flower1"),
        ("Phòng gym",             "bi-bicycle"),
        ("Bữa sáng",              "bi-egg-fried"),
        ("Sân vườn",              "bi-tree"),
        ("Xe đưa đón sân bay",    "bi-airplane"),
        ("Bãi biển riêng",        "bi-umbrella"),
        ("Phòng gia đình",        "bi-people"),
        ("Bể sục",                "bi-water"),
    ]
    amenity_objs = {}
    for name, icon in amenity_defs:
        amenity_objs[name] = _get_or_create_amenity(name, icon)
    db.session.flush()

    def am(*names):
        return [amenity_objs[n] for n in names if n in amenity_objs]

    # ------------------------------------------------------------------ #
    # 2. USERS                                                             #
    # ------------------------------------------------------------------ #
    users_data = [
        ("Admin System",      "admin@hotel.com",        "0900000001", "admin"),
        ("Lễ tân Nguyễn",     "receptionist@hotel.com", "0900000002", "receptionist"),
        ("Khách Trần Văn A",  "customer1@hotel.com",    "0900000003", "customer"),
        ("Khách Lê Thị B",    "customer2@hotel.com",    "0900000004", "customer"),
    ]
    customer = None
    for full_name, email, phone, role in users_data:
        u = User.query.filter_by(email=email).first()
        if not u:
            u = User(
                full_name=full_name, email=email, phone=phone, role=role,
                password_hash=generate_password_hash("Password123!")
            )
            db.session.add(u)
        if role == "customer":
            customer = u
    db.session.flush()

    # ------------------------------------------------------------------ #
    # 3. HOTELS                                                            #
    # ------------------------------------------------------------------ #
    if Hotel.query.count() > 0:
        db.session.commit()
        print("[seed] Dữ liệu đã tồn tại, bỏ qua.")
        return

    def img(hotel_slug, room_folder, filename):
        return f"uploads/rooms/{hotel_slug}/{room_folder}/{filename}"

    hotels_data = [
        # ── ĐÀ LẠT ──────────────────────────────────────────────────── #
        {
            "name": "Hưng Nguyên Valley Đà Lạt",
            "province": "Đà Lạt",
            "address": "20 Vạn Hạnh, Phường 8, Đà Lạt, Lâm Đồng",
            "star_rating": 2,
            "map_url": "https://maps.app.goo.gl/KErrz7QxXzR5M6Zb7",
            "description": "Khách sạn 2 sao tại trung tâm Đà Lạt, sân vườn xanh mát, gần các điểm du lịch.",
            "hotel_amenities": am("WiFi miễn phí", "Phòng không hút thuốc", "Lễ tân 24 giờ",
                                  "Dịch vụ phòng", "Sân vườn", "Phòng gia đình"),
            "room_types": [
                {
                    "name": "Phòng Giường Đôi",
                    "base_price": 302175, "capacity": 2,
                    "description": "20 m², phòng tắm riêng, TV màn hình phẳng, minibar, WiFi, cách âm.",
                    "amenities": am("WiFi miễn phí", "Phòng không hút thuốc"),
                    "image_filename": img("hung-nguyen-valley", "Phòng Giường Đôi", "32456 (1).png"),
                    "floors": 3, "rooms_per_floor": 3,
                },
                {
                    "name": "Phòng Deluxe",
                    "base_price": 241740, "capacity": 2,
                    "description": "18 m², ban công, nhìn ra sân trong, sân hiên riêng, WiFi miễn phí.",
                    "amenities": am("WiFi miễn phí", "Phòng không hút thuốc"),
                    "image_filename": img("hung-nguyen-valley", "Phòng Deluxe", "3123 (1).png"),
                    "floors": 3, "rooms_per_floor": 3,
                },
                {
                    "name": "Phòng Gia Đình",
                    "base_price": 327060, "capacity": 4,
                    "description": "27 m², nhìn ra vườn và thành phố, phù hợp gia đình, WiFi miễn phí.",
                    "amenities": am("WiFi miễn phí", "Phòng không hút thuốc", "Phòng gia đình"),
                    "image_filename": img("hung-nguyen-valley", "Phòng Gia Đình", "345673 (1).png"),
                    "floors": 3, "rooms_per_floor": 2,
                },
            ],
        },
        {
            "name": "Mơ Stay – Forest",
            "province": "Đà Lạt",
            "address": "Đường Hoa Hồng, Phường 4, Đà Lạt, Lâm Đồng",
            "star_rating": 4,
            "map_url": "https://maps.app.goo.gl/6vFSxsPb9DnKUnZH7",
            "description": "Resort 4 sao giữa rừng thông Đà Lạt, 2 nhà hàng, bãi đỗ xe miễn phí, bữa sáng.",
            "hotel_amenities": am("WiFi miễn phí", "Phòng không hút thuốc", "Lễ tân 24 giờ",
                                  "Nhà hàng", "Bãi đỗ xe miễn phí", "Sân vườn",
                                  "Bữa sáng", "Phòng gia đình"),
            "room_types": [
                {
                    "name": "Grand Deluxe King with Balcony",
                    "base_price": 1200000, "capacity": 2,
                    "description": "Phòng Deluxe King có ban công, view rừng thông, WiFi miễn phí.",
                    "amenities": am("WiFi miễn phí", "Phòng không hút thuốc", "Sân vườn"),
                    "image_filename": img("mo-stay-forest", "Grand Deluxe King with Balcony", "496829634.jpg"),
                    "floors": 3, "rooms_per_floor": 3,
                },
                {
                    "name": "Phòng Deluxe - Tầng Trệt",
                    "base_price": 850000, "capacity": 2,
                    "description": "Phòng Deluxe tầng trệt, lối ra vườn trực tiếp, WiFi miễn phí.",
                    "amenities": am("WiFi miễn phí", "Phòng không hút thuốc"),
                    "image_filename": img("mo-stay-forest", "Phòng Deluxe - Tầng Trệt", "778153888.jpg"),
                    "floors": 1, "rooms_per_floor": 4,
                },
                {
                    "name": "Phòng Deluxe Gia đình",
                    "base_price": 1800000, "capacity": 4,
                    "description": "Phòng gia đình rộng rãi, phù hợp 4 người, sân chơi trẻ em gần kề.",
                    "amenities": am("WiFi miễn phí", "Phòng không hút thuốc", "Phòng gia đình"),
                    "image_filename": img("mo-stay-forest", "Phòng Deluxe Gia đình", "496776891.jpg"),
                    "floors": 2, "rooms_per_floor": 2,
                },
            ],
        },
        # ── PHÚ QUỐC ─────────────────────────────────────────────────── #
        {
            "name": "JW Marriott Phu Quoc Emerald Bay Resort & Spa",
            "province": "Phú Quốc",
            "address": "Bãi Khem, An Thới, Phú Quốc, Kiên Giang",
            "star_rating": 5,
            "map_url": "https://maps.app.goo.gl/CuUzbYbfsx8V7AUR7",
            "description": "Resort 5 sao đẳng cấp tại Bãi Khem, 3 hồ bơi, 4 nhà hàng, spa và bãi biển riêng.",
            "hotel_amenities": am("WiFi miễn phí", "Phòng không hút thuốc", "Lễ tân 24 giờ",
                                  "Hồ bơi", "Nhà hàng", "Spa", "Bãi biển riêng", "Dịch vụ phòng"),
            "room_types": [
                {
                    "name": "Standard Room",
                    "base_price": 9025000, "capacity": 2,
                    "description": "53 m², nhìn ra vườn, ban công, bồn tắm + vòi sen, minibar.",
                    "amenities": am("WiFi miễn phí", "Phòng không hút thuốc"),
                    "image_filename": img("jw-marriott-phu-quoc", "Standard Room", "049d63b9 (1).avif"),
                    "floors": 5, "rooms_per_floor": 4,
                },
                {
                    "name": "Superior Room",
                    "base_price": 11400000, "capacity": 2,
                    "description": "53 m², view biển tuyệt đẹp, ban công, bồn tắm + vòi sen, minibar.",
                    "amenities": am("WiFi miễn phí", "Phòng không hút thuốc", "Bãi biển riêng"),
                    "image_filename": img("jw-marriott-phu-quoc", "Superior Room", "02597d90f13c3c8fdb0eb74db720629e-1600350275.jpg"),
                    "floors": 5, "rooms_per_floor": 3,
                },
                {
                    "name": "Superior Room with Pool Access",
                    "base_price": 14700000, "capacity": 2,
                    "description": "Lối ra hồ bơi riêng trực tiếp, view biển, đầy đủ tiện nghi 5 sao.",
                    "amenities": am("WiFi miễn phí", "Phòng không hút thuốc", "Hồ bơi"),
                    "image_filename": img("jw-marriott-phu-quoc", "Superior Room with Pool Access", "1-2-1024x683.jpg"),
                    "floors": 2, "rooms_per_floor": 4,
                },
                {
                    "name": "Xtra Sol Junior Suite",
                    "base_price": 18000000, "capacity": 3,
                    "description": "Junior Suite cao cấp, không gian rộng rãi, view biển panorama.",
                    "amenities": am("WiFi miễn phí", "Phòng không hút thuốc", "Bãi biển riêng", "Spa"),
                    "image_filename": img("jw-marriott-phu-quoc", "Xtra Sol Junior Suite", "637f03ce36cfd5f153df07b462ff7bf7-1600350275.avif"),
                    "floors": 3, "rooms_per_floor": 2,
                },
                {
                    "name": "Xtra Sol Suite",
                    "base_price": 25000000, "capacity": 4,
                    "description": "Suite đẳng cấp nhất, phòng khách riêng, hồ bơi riêng, butler service.",
                    "amenities": am("WiFi miễn phí", "Phòng không hút thuốc", "Hồ bơi", "Spa", "Dịch vụ phòng"),
                    "image_filename": img("jw-marriott-phu-quoc", "Xtra Sol Suite", "Cbu8zNrGQofFP3VQ2qKs.avif"),
                    "floors": 2, "rooms_per_floor": 1,
                },
            ],
        },
        {
            "name": "Sol by Meliá Phu Quoc",
            "province": "Phú Quốc",
            "address": "Khu 1, Bãi Trường, Dương Tơ, Phú Quốc, Kiên Giang",
            "star_rating": 5,
            "map_url": "https://maps.app.goo.gl/VqFDCqcKwksD3uR49",
            "description": "Resort 5 sao bãi biển riêng, 2 hồ bơi, 3 nhà hàng, xe đưa đón sân bay miễn phí.",
            "hotel_amenities": am("WiFi miễn phí", "Phòng không hút thuốc", "Lễ tân 24 giờ",
                                  "Hồ bơi", "Nhà hàng", "Spa", "Bãi biển riêng",
                                  "Xe đưa đón sân bay", "Bãi đỗ xe miễn phí"),
            "room_types": [
                {
                    "name": "Standard Room",
                    "base_price": 1700000, "capacity": 2,
                    "description": "31–35 m², view vườn, ban công kèm bàn ghế, điều hòa riêng, minibar.",
                    "amenities": am("WiFi miễn phí", "Phòng không hút thuốc"),
                    "image_filename": img("sol-melia-phu-quoc", "Standard Room", "049d63b9 (1).avif"),
                    "floors": 4, "rooms_per_floor": 5,
                },
                {
                    "name": "Superior Room",
                    "base_price": 1890000, "capacity": 2,
                    "description": "46 m², bồn tắm + vòi sen, ban công, minibar, điều hòa.",
                    "amenities": am("WiFi miễn phí", "Phòng không hút thuốc"),
                    "image_filename": img("sol-melia-phu-quoc", "Superior Room", "02597d90f13c3c8fdb0eb74db720629e-1600350275.jpg"),
                    "floors": 4, "rooms_per_floor": 4,
                },
                {
                    "name": "Superior Room with Pool Access",
                    "base_price": 2250000, "capacity": 2,
                    "description": "Lối ra hồ bơi riêng trực tiếp, đầy đủ tiện nghi Superior.",
                    "amenities": am("WiFi miễn phí", "Phòng không hút thuốc", "Hồ bơi"),
                    "image_filename": img("sol-melia-phu-quoc", "Superior Room with Pool Access", "1-2-1024x683.jpg"),
                    "floors": 2, "rooms_per_floor": 4,
                },
                {
                    "name": "Xtra Sol Junior Suite",
                    "base_price": 3500000, "capacity": 3,
                    "description": "Junior Suite view biển, không gian rộng, minibar, bồn tắm.",
                    "amenities": am("WiFi miễn phí", "Phòng không hút thuốc", "Hồ bơi"),
                    "image_filename": img("sol-melia-phu-quoc", "Xtra Sol Junior Suite", "637f03ce36cfd5f153df07b462ff7bf7-1600350275.avif"),
                    "floors": 3, "rooms_per_floor": 2,
                },
                {
                    "name": "Xtra Sol Suite",
                    "base_price": 5500000, "capacity": 4,
                    "description": "Suite cao cấp nhất, hồ bơi riêng, phòng khách tách biệt, butler service.",
                    "amenities": am("WiFi miễn phí", "Phòng không hút thuốc", "Hồ bơi", "Spa"),
                    "image_filename": img("sol-melia-phu-quoc", "Xtra Sol Suite", "Cbu8zNrGQofFP3VQ2qKs.avif"),
                    "floors": 2, "rooms_per_floor": 1,
                },
            ],
        },
        # ── ĐÀ NẴNG ──────────────────────────────────────────────────── #
        {
            "name": "Doha Central Bliss Danang Hotel",
            "province": "Đà Nẵng",
            "address": "193 Nguyễn Văn Linh, Nam Dương, Hải Châu, Đà Nẵng",
            "star_rating": 3,
            "map_url": "https://maps.app.goo.gl/ttBg3DGRkbz4BFrj9",
            "description": "Khách sạn 3 sao trung tâm Đà Nẵng, bãi đỗ xe miễn phí, xe đưa đón sân bay.",
            "hotel_amenities": am("WiFi miễn phí", "Phòng không hút thuốc", "Lễ tân 24 giờ",
                                  "Dịch vụ phòng", "Bãi đỗ xe miễn phí", "Xe đưa đón sân bay",
                                  "Phòng gia đình"),
            "room_types": [
                {
                    "name": "Phòng Deluxe Giường Đôi",
                    "base_price": 680000, "capacity": 2,
                    "description": "Phòng tắm riêng, TV màn hình phẳng, điều hòa, WiFi miễn phí.",
                    "amenities": am("WiFi miễn phí", "Phòng không hút thuốc"),
                    "image_filename": img("doha-central-danang", "Phòng Deluxe Giường Đôi", "635118225.jpg"),
                    "floors": 4, "rooms_per_floor": 4,
                },
                {
                    "name": "Phòng Deluxe 2 Giường Đơn",
                    "base_price": 750000, "capacity": 2,
                    "description": "2 giường đơn, phòng tắm riêng, TV, điều hòa, WiFi miễn phí.",
                    "amenities": am("WiFi miễn phí", "Phòng không hút thuốc"),
                    "image_filename": img("doha-central-danang", "Phòng Deluxe 2 Giường Đơn", "810240076.jpg"),
                    "floors": 4, "rooms_per_floor": 3,
                },
                {
                    "name": "Căn hộ Gia đình 1 Phòng ngủ",
                    "base_price": 1200000, "capacity": 4,
                    "description": "Căn hộ gia đình 1 phòng ngủ, bếp nhỏ, phòng khách riêng, WiFi miễn phí.",
                    "amenities": am("WiFi miễn phí", "Phòng không hút thuốc", "Phòng gia đình"),
                    "image_filename": img("doha-central-danang", "Căn hộ Gia đình 1 Phòng ngủ", "639889283.jpg"),
                    "floors": 3, "rooms_per_floor": 2,
                },
            ],
        },
        {
            "name": "Sea Vibe Boutique Hotel",
            "province": "Đà Nẵng",
            "address": "6-8 Phạm Thiều, Phước Mỹ, Sơn Trà, Đà Nẵng",
            "star_rating": 3,
            "map_url": "https://maps.app.goo.gl/tY7rLGXnsY6JS26p7",
            "description": "Boutique hotel gần biển Mỹ Khê, bể sục, bãi đỗ xe miễn phí gần đó.",
            "hotel_amenities": am("WiFi miễn phí", "Phòng không hút thuốc", "Lễ tân 24 giờ",
                                  "Dịch vụ phòng", "Bãi đỗ xe miễn phí", "Bể sục"),
            "room_types": [
                {
                    "name": "Phòng Tiêu chuẩn Giường đôi",
                    "base_price": 468000, "capacity": 2,
                    "description": "15 m², điều hòa độc lập, TV, tủ quần áo, WiFi miễn phí.",
                    "amenities": am("WiFi miễn phí", "Phòng không hút thuốc"),
                    "image_filename": img("sea-vibe-danang", "Phòng Tiêu chuẩn Giường đôi", "888157736.jpg"),
                    "floors": 4, "rooms_per_floor": 4,
                },
                {
                    "name": "Phòng Deluxe",
                    "base_price": 684000, "capacity": 2,
                    "description": "15 m², ngắm cảnh, phòng tắm riêng, TV màn hình phẳng, WiFi miễn phí.",
                    "amenities": am("WiFi miễn phí", "Phòng không hút thuốc"),
                    "image_filename": img("sea-vibe-danang", "Phòng Deluxe", "888157149.jpg"),
                    "floors": 4, "rooms_per_floor": 3,
                },
                {
                    "name": "Suite Executive",
                    "base_price": 1200000, "capacity": 2,
                    "description": "Suite Executive view biển Mỹ Khê, phòng tắm cao cấp, bể sục.",
                    "amenities": am("WiFi miễn phí", "Phòng không hút thuốc", "Bể sục"),
                    "image_filename": img("sea-vibe-danang", "Suite Executive", "888159858.jpg"),
                    "floors": 2, "rooms_per_floor": 2,
                },
            ],
        },
        # ── HỒ CHÍ MINH ──────────────────────────────────────────────── #
        {
            "name": "Liberty Central Saigon Riverside",
            "province": "Hồ Chí Minh",
            "address": "17 Tôn Đức Thắng, Bến Nghé, Quận 1, TP. Hồ Chí Minh",
            "star_rating": 4,
            "map_url": "https://maps.app.goo.gl/ddubjfQfj5eihZwR9",
            "description": "Khách sạn 4 sao bên sông Sài Gòn, hồ bơi tầng thượng, gym, spa, Sky Bar.",
            "hotel_amenities": am("WiFi miễn phí", "Phòng không hút thuốc", "Lễ tân 24 giờ",
                                  "Hồ bơi", "Nhà hàng", "Spa", "Phòng gym", "Dịch vụ phòng"),
            "room_types": [
                {
                    "name": "Deluxe Room",
                    "base_price": 2576000, "capacity": 2,
                    "description": "24 m², view thành phố, minibar, tủ lạnh, TV màn hình phẳng.",
                    "amenities": am("WiFi miễn phí", "Phòng không hút thuốc"),
                    "image_filename": img("liberty-central-saigon", "Deluxe Room", "1791698334233_60952423178943399_193116356851453905_084bbf36477dededfda85d957e099438.jpg"),
                    "floors": 5, "rooms_per_floor": 5,
                },
                {
                    "name": "Premier Room River View",
                    "base_price": 3024000, "capacity": 2,
                    "description": "26 m², nhìn ra sông Sài Gòn, minibar, tủ lạnh, két an toàn.",
                    "amenities": am("WiFi miễn phí", "Phòng không hút thuốc"),
                    "image_filename": img("liberty-central-saigon", "Premier Room River View", "1791698264015_60952423178943399_193116356851453905_f7138937a6dbd8a8136cd0d152318a26.jpg"),
                    "floors": 5, "rooms_per_floor": 4,
                },
                {
                    "name": "Signature River View (Executive)",
                    "base_price": 4256000, "capacity": 2,
                    "description": "Phòng Executive view sông, tiện nghi cao cấp, dịch vụ phòng 24h.",
                    "amenities": am("WiFi miễn phí", "Phòng không hút thuốc", "Dịch vụ phòng"),
                    "image_filename": img("liberty-central-saigon", "Signature River View (Executive)", "1791698717946_60952423178943399_193116356851453905_8ecc336fe954edfb2a105092c8a23d93.jpg"),
                    "floors": 3, "rooms_per_floor": 3,
                },
                {
                    "name": "Liberty Central Suite",
                    "base_price": 6000000, "capacity": 3,
                    "description": "Suite cao cấp nhất, phòng khách riêng, view sông Sài Gòn toàn cảnh.",
                    "amenities": am("WiFi miễn phí", "Phòng không hút thuốc", "Dịch vụ phòng", "Hồ bơi"),
                    "image_filename": img("liberty-central-saigon", "Liberty Central Suite", "1791698840438_60952423178943399_193116356851453905_3e7b48ee262937618c3ee2f0b9e1cec1.jpg"),
                    "floors": 2, "rooms_per_floor": 2,
                },
            ],
        },
        {
            "name": "Park Hyatt Saigon",
            "province": "Hồ Chí Minh",
            "address": "2 Công trường Lam Sơn, Bến Nghé, Quận 1, TP. Hồ Chí Minh",
            "star_rating": 5,
            "map_url": "https://maps.app.goo.gl/yiPcop64assMQzZR8",
            "description": "Khách sạn 5 sao biểu tượng tại Quận 1, hồ bơi, 2 nhà hàng, spa, bãi đỗ xe miễn phí.",
            "hotel_amenities": am("WiFi miễn phí", "Phòng không hút thuốc", "Lễ tân 24 giờ",
                                  "Hồ bơi", "Nhà hàng", "Spa", "Phòng gym",
                                  "Dịch vụ phòng", "Bãi đỗ xe miễn phí"),
            "room_types": [
                {
                    "name": "Park Room",
                    "base_price": 7760000, "capacity": 2,
                    "description": "34 m², nhìn ra thành phố và Nhà hát TP, bồn tắm cẩm thạch, TV 48\", loa Bose.",
                    "amenities": am("WiFi miễn phí", "Phòng không hút thuốc"),
                    "image_filename": img("park-hyatt-saigon", "Park Room", "Park+Hyatt+Saigon+Review+-6006.webp"),
                    "floors": 6, "rooms_per_floor": 4,
                },
                {
                    "name": "Park Room Garden View",
                    "base_price": 8260000, "capacity": 2,
                    "description": "34 m², cửa sổ sàn-trần nhìn ra vườn và hồ bơi, vòi sen mưa, loa Bose.",
                    "amenities": am("WiFi miễn phí", "Phòng không hút thuốc", "Hồ bơi"),
                    "image_filename": img("park-hyatt-saigon", "Park Room Garden View", "Park-Hyatt-Saigon-P645-Park-Deluxe-Suite-Living-Room-Private-Garden.16x9-600x600.webp"),
                    "floors": 6, "rooms_per_floor": 3,
                },
                {
                    "name": "Park Deluxe Room",
                    "base_price": 12760000, "capacity": 3,
                    "description": "41 m², sân thượng riêng nối thẳng hồ bơi, TV 48\", iPad mini, Nespresso.",
                    "amenities": am("WiFi miễn phí", "Phòng không hút thuốc", "Hồ bơi", "Spa"),
                    "image_filename": img("park-hyatt-saigon", "Park Deluxe Room", "0222g12000l0qyddd4895_R_960_660_R5_D.jpg"),
                    "floors": 4, "rooms_per_floor": 2,
                },
                {
                    "name": "Park Suite",
                    "base_price": 14760000, "capacity": 3,
                    "description": "Suite đẳng cấp nhất Park Hyatt, phòng khách riêng, butler service 24h.",
                    "amenities": am("WiFi miễn phí", "Phòng không hút thuốc", "Hồ bơi", "Spa", "Dịch vụ phòng"),
                    "image_filename": img("park-hyatt-saigon", "Park Suite", "park-hyatt-saigon-Lam-Son-Suite.webp"),
                    "floors": 2, "rooms_per_floor": 2,
                },
            ],
        },
        # ── HÀ NỘI ───────────────────────────────────────────────────── #
        {
            "name": "Hanoi Emerald Waters Hotel & Spa",
            "province": "Hà Nội",
            "address": "47 Lò Sũ, Lý Thái Tổ, Hoàn Kiếm, Hà Nội",
            "star_rating": 4,
            "map_url": "https://maps.app.goo.gl/n2ZVSawPc7wvQ18J6",
            "description": "Khách sạn 4 sao phố cổ Hà Nội, bồn tắm nước khoáng, spa, gym trên mái, buffet sáng.",
            "hotel_amenities": am("WiFi miễn phí", "Phòng không hút thuốc", "Lễ tân 24 giờ",
                                  "Dịch vụ phòng", "Spa", "Phòng gym", "Nhà hàng", "Bữa sáng"),
            "room_types": [
                {
                    "name": "Deluxe Room",
                    "base_price": 1071000, "capacity": 2,
                    "description": "25 m², view thành phố, bồn tắm nước khoáng, vòi sen phun mưa, minibar, cách âm.",
                    "amenities": am("WiFi miễn phí", "Phòng không hút thuốc"),
                    "image_filename": img("hanoi-emerald-waters", "Deluxe Room", "1791727077016_60952423178943399_193116356851453905_d41bd0bebd4167771bf8063c4a5d3e32.jpg"),
                    "floors": 5, "rooms_per_floor": 4,
                },
                {
                    "name": "Deluxe Family Room",
                    "base_price": 1369000, "capacity": 3,
                    "description": "38 m², tầng 4–9, view thành phố, giường King + giường đơn, bồn tắm nước khoáng.",
                    "amenities": am("WiFi miễn phí", "Phòng không hút thuốc", "Phòng gia đình"),
                    "image_filename": img("hanoi-emerald-waters", "Deluxe Family Room", "1791727559150_60952423178943399_193116356851453905_07b9b66b7343cdd0a3f814fca94552b9.jpg"),
                    "floors": 6, "rooms_per_floor": 3,
                },
            ],
        },
        {
            "name": "Sofitel Legend Metropole Hanoi",
            "province": "Hà Nội",
            "address": "15 Ngô Quyền, Hoàn Kiếm, Hà Nội",
            "star_rating": 5,
            "map_url": "https://maps.app.goo.gl/TwJDRPweF4LAxKh27",
            "description": "Khách sạn 5 sao biểu tượng Hà Nội, 364 phòng, 2 cánh Heritage & Opera, spa, hồ bơi.",
            "hotel_amenities": am("WiFi miễn phí", "Phòng không hút thuốc", "Lễ tân 24 giờ",
                                  "Dịch vụ phòng", "Spa", "Hồ bơi", "Nhà hàng",
                                  "Bữa sáng", "Phòng gia đình"),
            "room_types": [
                {
                    "name": "Luxury Room",
                    "base_price": 3400000, "capacity": 2,
                    "description": "32 m², cánh Heritage, trần cao, quạt trần, sàn gỗ, view thành phố/hồ bơi/vườn.",
                    "amenities": am("WiFi miễn phí", "Phòng không hút thuốc"),
                    "image_filename": img("sofitel-metropole-hanoi", "Luxury Room", "1791727832973_60952423178943399_193116356851453905_65280ca278b18f664d39a1d4c2cce82e.jpg"),
                    "floors": 4, "rooms_per_floor": 5,
                },
                {
                    "name": "Grand Luxury Room",
                    "base_price": 6500000, "capacity": 3,
                    "description": "37 m², bồn tắm + vòi sen riêng, đồ vệ sinh Hermès, view vườn/phố Ngô Quyền.",
                    "amenities": am("WiFi miễn phí", "Phòng không hút thuốc", "Spa"),
                    "image_filename": img("sofitel-metropole-hanoi", "Grand Luxury Room", "1791727941476_60952423178943399_193116356851453905_e78245bec86cf97d74c3db42e9c9e1ef.jpg"),
                    "floors": 4, "rooms_per_floor": 3,
                },
                {
                    "name": "Premium Room",
                    "base_price": 3400000, "capacity": 2,
                    "description": "32 m², cánh Opera, bồn tắm có vòi sen, đồ vệ sinh Lanvin, một số phòng có ban công.",
                    "amenities": am("WiFi miễn phí", "Phòng không hút thuốc"),
                    "image_filename": img("sofitel-metropole-hanoi", "Premium Room", "1791728032409_60952423178943399_193116356851453905_d7049a81f3a12a98e7bdd836d7321ce2.jpg"),
                    "floors": 5, "rooms_per_floor": 4,
                },
                {
                    "name": "Grand Premium Room",
                    "base_price": 7500000, "capacity": 3,
                    "description": "48 m², tầng 5–7 Club Floor, bồn tắm kiểu Pháp, đặc quyền Club Metropole, quản gia 24h.",
                    "amenities": am("WiFi miễn phí", "Phòng không hút thuốc", "Spa", "Dịch vụ phòng"),
                    "image_filename": img("sofitel-metropole-hanoi", "Grand Premium Room", "1791728159485_60952423178943399_193116356851453905_bd601117b21a302aa7a4a44afb1e27e5.jpg"),
                    "floors": 3, "rooms_per_floor": 3,
                },
                {
                    "name": "Prestige Suite",
                    "base_price": 14943000, "capacity": 3,
                    "description": "64 m², phòng khách riêng, đồ vệ sinh Hermès, máy Nespresso, quản gia riêng.",
                    "amenities": am("WiFi miễn phí", "Phòng không hút thuốc", "Spa", "Dịch vụ phòng"),
                    "image_filename": img("sofitel-metropole-hanoi", "Prestige Suite", "1791728299465_60952423178943399_193116356851453905_e0cdafb3f0ce7434c4a1ca3d0d072ce6.jpg"),
                    "floors": 2, "rooms_per_floor": 2,
                },
            ],
        },
    ]

    # ------------------------------------------------------------------ #
    # 4. INSERT HOTELS, ROOM TYPES, ROOMS                                  #
    # ------------------------------------------------------------------ #
    for hd in hotels_data:
        h = Hotel(
            name=hd["name"], province=hd["province"],
            address=hd["address"], star_rating=hd["star_rating"],
            map_url=hd["map_url"], description=hd["description"],
            is_active=True,
        )
        h.amenities = hd["hotel_amenities"]
        db.session.add(h)
        db.session.flush()

        floor_counter = 1
        for rtd in hd["room_types"]:
            rt = RoomType(
                hotel_id=h.id, name=rtd["name"],
                base_price=rtd["base_price"], capacity=rtd["capacity"],
                description=rtd["description"],
                image_filename=rtd["image_filename"],
            )
            rt.amenities = rtd["amenities"]
            db.session.add(rt)
            db.session.flush()

            for floor in range(1, rtd["floors"] + 1):
                for num in range(1, rtd["rooms_per_floor"] + 1):
                    room_number = f"{floor_counter}{floor:01d}{num:02d}"
                    r = Room(
                        hotel_id=h.id, room_number=room_number,
                        floor=floor, room_type_id=rt.id, is_active=True,
                    )
                    db.session.add(r)
            floor_counter += 1
        db.session.flush()

    # ------------------------------------------------------------------ #
    # 5. BOOKING MẪU                                                       #
    # ------------------------------------------------------------------ #
    if Booking.query.count() == 0:
        room = Room.query.first()
        if room and customer:
            b = Booking(
                code=_random_code(),
                user_id=customer.id, room_id=room.id,
                check_in=date(2026, 11, 10), check_out=date(2026, 11, 12),
                guests=2, guest_name=customer.full_name,
                guest_phone="0900000003", guest_email=customer.email,
                total_price=room.room_type.base_price * 2,
                status="Pending",
            )
            db.session.add(b)

    db.session.commit()
    print("[seed] Hoàn thành!")
    print(f"  Hotels:    {Hotel.query.count()}")
    print(f"  RoomTypes: {RoomType.query.count()}")
    print(f"  Rooms:     {Room.query.count()}")
    print(f"  Users:     {User.query.count()}")
    print(f"  Bookings:  {Booking.query.count()}")