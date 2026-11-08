# Mini Hotel Booking System (PWD301 — Topic 4)

Ứng dụng đặt phòng khách sạn mini: khách tìm khách sạn và phòng trống, đặt phòng qua form 3 bước; lễ tân xác nhận booking; admin quản lý khách sạn, phòng, người dùng, xem lịch booking và dashboard thống kê. Có REST API (JWT) cho tích hợp bên ngoài.

**Công nghệ:** Flask, Flask-SQLAlchemy (ORM), Flask-WTF, Flask-Login, Flask-JWT-Extended, Flask-Migrate, Flask-Limiter, SQL Server (pymssql), Bootstrap 5, AJAX (Fetch), Docker.

## Ảnh chụp giao diện

<!-- Thêm ảnh chụp: trang chủ, kết quả tìm kiếm, chi tiết khách sạn, đặt phòng, lịch booking, dashboard -->

## Tính năng chính

- Tìm khách sạn theo tỉnh, ngày, số khách; lọc giá, hạng sao, tiện nghi; sắp xếp; phân trang (AJAX, không tải lại trang).
- Chi tiết khách sạn: carousel ảnh, địa chỉ, nút xem bản đồ, tiện nghi, phòng trống theo ngày kèm tổng tiền.
- Đặt phòng 3 bước (chọn ngày, thông tin khách, xác nhận) với PRG, chống đặt trùng phòng.
- Vòng đời booking: Pending, Confirmed, Cancelled, Completed. Khách chỉ tự hủy được trước ngày nhận phòng; lễ tân/Admin xác nhận, từ chối (có lý do) và hoàn tất từ ngày trả phòng trở đi.
- Cập nhật trạng thái tự động (khi mở các trang quản lý, lịch, dashboard và "Booking của tôi"): booking Pending mà đã qua hết ngày nhận phòng thì tự chuyển Cancelled kèm lý do; booking Confirmed mà đã quá ngày trả phòng 3 ngày thì tự chuyển Completed. Đây là quyết định khác với pipeline.
- Khách xem và hủy booking của mình, sửa thông tin khi còn Pending (AJAX).
- Lễ tân/Admin xác nhận, từ chối, hoàn tất booking (AJAX); lịch booking theo tháng.
- Admin: quản lý khách sạn, loại phòng, phòng, tiện nghi, người dùng; upload nhiều ảnh và xóa từng ảnh; dashboard doanh thu, công suất phòng, booking theo tháng.
- REST API 11 endpoint, JWT có hạn, JSON thống nhất.

## Phân quyền

| Vai trò | Quyền chính |
|---|---|
| Admin | Quản lý khách sạn, phòng, tiện nghi, người dùng; xem dashboard và lịch; đổi trạng thái booking |
| Receptionist | Xem và xử lý booking (xác nhận, từ chối, hoàn tất), xem lịch |
| Customer | Tìm và đặt phòng, xem/hủy/sửa booking của mình |

## Yêu cầu

- Python 3.11 trở lên (dự án chạy trên Python 3.14).
- SQL Server (local hoặc qua Docker), driver `pymssql`.
- Docker Desktop (nếu chạy bằng Docker).

## Cấu hình `.env`

```bash
cp .env.example .env          # Windows PowerShell: Copy-Item .env.example .env
```

Sửa các giá trị trong `.env`:

| Biến | Ý nghĩa |
|---|---|
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | Kết nối SQL Server |
| `SECRET_KEY`, `JWT_SECRET_KEY` | Hai chuỗi ngẫu nhiên dài, khác nhau |
| `UPLOAD_FOLDER`, `MAX_CONTENT_LENGTH` | Thư mục và giới hạn upload |

Không commit file `.env`. Mật khẩu có ký tự đặc biệt (ví dụ `@`) được mã hóa tự động khi tạo chuỗi kết nối.

## Chạy bằng Docker

```bash
docker compose up
```

Lần đầu, hệ thống tự tạo database, chạy migration và nạp dữ liệu mẫu, rồi mở ứng dụng tại http://localhost:5000.

```bash
docker compose down        # dừng, giữ dữ liệu và ảnh upload
docker compose down -v     # dừng và XÓA dữ liệu (reset DB, mất ảnh upload)
```

Lưu ý: `DB_PASSWORD` trong `.env` phải đủ mạnh theo yêu cầu của SQL Server (có chữ hoa, chữ thường, số, ký tự đặc biệt), nếu không container SQL Server sẽ không khởi động.

## Chạy cục bộ (không Docker)

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env       # rồi sửa DB_PASSWORD theo SQL Server của bạn
```

Tạo sẵn một database rỗng tên đúng `DB_NAME` (mặc định `hotel_db`) trong SQL Server, collation `Vietnamese_CI_AS`. Sau đó:

```powershell
py -m flask db upgrade     # tạo bảng
py -m flask seed           # nạp dữ liệu mẫu
py -m flask run --debug    # chạy tại http://127.0.0.1:5000
```

Các lệnh hữu ích: `py -m flask routes` (xem toàn bộ route), `py -m flask shell`.

## Tài khoản demo

Mật khẩu chung: `Password123!`

| Vai trò | Email |
|---|---|
| Admin | admin@hotel.com |
| Receptionist | receptionist@hotel.com |
| Customer | customer1@hotel.com, customer2@hotel.com, customer3@hotel.com |

Dữ liệu mẫu gồm 10 khách sạn, 34 loại phòng, 79 phòng, 5 người dùng và 28 booking.

## Cấu trúc thư mục

```
mini-hotel-booking/
├── app/
│   ├── __init__.py          # app factory, đăng ký 6 Blueprint
│   ├── config.py            # cấu hình Dev/Test/Prod, đọc .env
│   ├── extensions.py        # db, migrate, login, csrf, jwt, limiter
│   ├── models.py            # mô hình dữ liệu (ORM)
│   ├── decorators.py        # phân quyền theo vai trò
│   ├── seed.py              # dữ liệu mẫu
│   ├── auth/                # đăng ký, đăng nhập, đổi mật khẩu
│   ├── hotels/              # tìm kiếm, chi tiết, quản lý khách sạn
│   ├── rooms/               # loại phòng, phòng, tiện nghi
│   ├── bookings/            # đặt phòng 3 bước, quản lý, lịch
│   ├── admin/               # dashboard, quản lý người dùng
│   ├── api/                 # REST API + JWT
│   └── utils/               # ngày tháng, bảo mật, upload ảnh
│       (mỗi Blueprint: routes.py mỏng, forms.py, services.py ghi DB)
├── templates/               # Jinja2 (base.html, macros, trang theo module)
├── static/                  # css, js (api.js, availability.js, ...), uploads/
├── migrations/              # lịch sử migration (Alembic)
├── docker/init_db.py        # tạo database khi khởi động Docker
├── Dockerfile
├── docker-compose.yml
├── wsgi.py
├── requirements.txt
└── .env.example
```

## REST API

Tiền tố `/api`, JSON, miễn CSRF vì dùng header `Authorization: Bearer <token>`. Thành công trả `{"data": ...}`; lỗi trả `{"error": {"code": ..., "message": ..., "fields": ...}}`.

| Phương thức | URL | Quyền | Mã trả về |
|---|---|---|---|
| POST | `/api/auth/login` | Công khai (giới hạn 5 lần/phút) | 200, 400, 401 |
| GET | `/api/rooms/available` | Công khai | 200, 400 |
| GET | `/api/rooms/<id>` | Công khai | 200, 404 |
| GET | `/api/hotels` | Công khai | 200, 400 |
| GET | `/api/hotels/<id>` | Công khai | 200, 404 |
| GET | `/api/bookings` | JWT | 200, 401 |
| GET | `/api/bookings/<id>` | JWT (chủ booking hoặc nhân viên) | 200, 401, 403, 404 |
| POST | `/api/bookings` | JWT | 201, 400, 401, 409 |
| PATCH | `/api/bookings/<id>` | JWT (chủ booking, khi còn Pending) | 200, 400, 401, 403, 404, 409 |
| PUT | `/api/bookings/<id>/status` | JWT (Receptionist, Admin) | 200, 400, 401, 403, 404, 409 |
| DELETE | `/api/bookings/<id>` | JWT (chủ booking hoặc nhân viên) | 200, 401, 403, 404 |

### Ví dụ curl

Đổi `localhost:5000` nếu chạy ở địa chỉ khác. Ngày đặt phòng không được ở quá khứ, hãy đổi cho hợp lệ. Trên PowerShell nên dùng `curl.exe`, và lưu body JSON vào file rồi gọi `-d "@body.json"` để tránh lỗi dấu nháy.

**1. Đăng nhập, lấy token**

```bash
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "customer1@hotel.com", "password": "Password123!"}'
```

Phản hồi có dạng `{"data": {"access_token": "...", "token_type": "Bearer", "expires_in": 3600, "user": {...}}}`. Token có hạn 60 phút (`expires_in` tính bằng giây). Gán token vào biến cho các lệnh sau:

```bash
TOKEN="<dán access_token vào đây>"
```

Trên PowerShell (dùng `curl.exe`, ghi body ra file để tránh lỗi dấu nháy):

```powershell
'{"email":"customer1@hotel.com","password":"Password123!"}' | Set-Content -Encoding utf8 body.json
$TOKEN = (curl.exe -s -X POST http://localhost:5000/api/auth/login -H "Content-Type: application/json" -d "@body.json" | ConvertFrom-Json).data.access_token
Remove-Item body.json
curl.exe -H "Authorization: Bearer $TOKEN" http://localhost:5000/api/bookings
```

Các ví dụ bên dưới viết theo bash. Trên PowerShell, đổi `curl` thành `curl.exe`, bỏ dấu `\` cuối dòng (viết trên một dòng) và dùng body file như trên.

**2. Phòng trống theo ngày** (tùy chọn: `guests`, `hotel_id`, `room_type`, `max_price`)

```bash
curl "http://localhost:5000/api/rooms/available?checkin=2026-12-20&checkout=2026-12-23&guests=2"
```

**3. Chi tiết phòng** (thêm `checkin`, `checkout` để tính tổng tiền)

```bash
curl "http://localhost:5000/api/rooms/1?checkin=2026-12-20&checkout=2026-12-23"
```

**4. Danh sách khách sạn** (lọc và phân trang)

```bash
curl "http://localhost:5000/api/hotels?sort=price_asc&page=1"
```

Phản hồi gồm `hotels[]` (mỗi khách sạn có `id`, `name`, `province`, `address`, `star_rating`, `image_url`, `price_from`) cùng `page`, `pages`, `per_page`, `total`, và `checkin`, `checkout`, `nights` (rỗng khi không truyền ngày). Giá trị `sort`: `price_asc`, `price_desc`, `stars_desc`. Các tham số lọc khác: `province`, `guests`, `min_price`, `max_price`, `stars`, `amenity`. Giá trị có dấu hoặc dấu cách phải mã hóa URL, ví dụ lọc Hà Nội:

```bash
curl "http://localhost:5000/api/hotels?province=H%C3%A0%20N%E1%BB%99i"
```

**5. Chi tiết khách sạn**

```bash
curl http://localhost:5000/api/hotels/5
```

**6. Danh sách booking của tôi** (nhân viên thấy tất cả; lọc `status`, phân trang `page`)

```bash
curl -H "Authorization: Bearer $TOKEN" "http://localhost:5000/api/bookings?status=Pending&page=1"
```

**7. Chi tiết một booking**

```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:5000/api/bookings/1
```

**8. Tạo booking** (trạng thái Pending; `guests` mặc định 1, `note` tùy chọn)

```bash
curl -X POST http://localhost:5000/api/bookings \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"room_id": 1, "checkin": "2026-12-20", "checkout": "2026-12-22", "guests": 2,
       "guest_name": "Nguyen Van A", "guest_phone": "0901234567",
       "guest_email": "a@example.com", "note": "Tang cao"}'
```

**9. Sửa thông tin booking** (chỉ khi còn Pending; gửi ít nhất một trong `guest_name`, `guest_phone`, `note`)

```bash
curl -X PATCH http://localhost:5000/api/bookings/1 \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"guest_phone": "0987654321"}'
```

**10. Đổi trạng thái** (cần token Receptionist hoặc Admin; Customer gọi sẽ nhận 403). `status` là một trong `Pending`, `Confirmed`, `Cancelled`, `Completed`.

```bash
curl -X PUT http://localhost:5000/api/bookings/1/status \
  -H "Authorization: Bearer $TOKEN_LE_TAN" -H "Content-Type: application/json" \
  -d '{"status": "Confirmed", "reason": "Da xac nhan"}'
```

**11. Hủy booking** (không xóa dòng, chuyển sang Cancelled)

```bash
curl -X DELETE -H "Authorization: Bearer $TOKEN" http://localhost:5000/api/bookings/1
```

Gọi endpoint cần JWT mà không gửi token sẽ nhận 401.

## Bảo mật

- CSRF bật cho mọi form web (blueprint `api` miễn vì xác thực bằng header JWT).
- 100% truy vấn bằng ORM, không dùng SQL thô.
- Mật khẩu được băm; đăng nhập chống open redirect; giới hạn tốc độ ở đăng nhập web và `/api/auth/login`.
- Upload ảnh: kiểm tra đuôi (png, jpg, webp), tối đa 2 MB mỗi ảnh, đổi tên ngẫu nhiên; chống xóa file ngoài thư mục ảnh.
- Phân quyền bằng decorator và kiểm tra quyền sở hữu booking (chống IDOR).
- Bí mật nằm trong `.env`, không commit.

## Chạy test

Test dùng pytest với SQLite in-memory (không cần SQL Server). Chạy toàn bộ:

```powershell
py -m pytest -q
```

Đo độ phủ (luôn đo cả gói `app`):

```powershell
py -m pytest --cov=app --cov-report=term-missing -q
```

Lưu ý: không dùng `--cov` với một gói con như `--cov=app.bookings`. Cách đó từng làm fixture khởi tạo lỗi `TypeError: 'InternalTraversal' object is not callable`. Muốn xem riêng một module, lọc kết quả: `Select-String -Pattern "bookings"`.

Các file test nằm trong thư mục `tests/`:

| File | Nội dung |
|---|---|
| `conftest.py` | App test, dữ liệu mẫu, đăng nhập, tắt giới hạn đăng nhập khi test |
| `test_models.py`, `test_no_raw_sql.py` | Model và kiểm tra không dùng SQL thô |
| `test_permissions.py` | Phân quyền theo vai trò |
| `test_booking_services.py`, `test_booking_routes.py` | Nghiệp vụ và route booking |
| `test_api.py` | REST API (JWT, mã trạng thái 200/201/400/401/403/404/409) |
| `test_dashboard_services.py`, `test_user_services.py` | Thống kê dashboard, quản lý người dùng |
| `test_room_services.py`, `test_room_routes.py`, `room_helpers.py` | Phòng, loại phòng, tiện nghi |

## Lưu ý về SQL Server

- Container cần ít nhất 2 GB RAM.
- Image SQL Server chỉ có bản amd64; máy Mac chip ARM chạy qua giả lập nên chậm hơn.
- Mật khẩu SA phải đủ mạnh; ký tự đặc biệt như `@` được mã hóa tự động khi tạo chuỗi kết nối.
- Khi demo nên chạy 1 worker, vì bộ giới hạn tốc độ lưu trong bộ nhớ và mỗi worker đếm riêng.

## Phân công thành viên

| # | Thành viên | Phần phụ trách |
|---|---|---|
| 1 | Khưu Hải Nguyên | Nền tảng: app factory, config, models, migration, seed, Docker |
| 2 | Khưu Hải Nguyên, Nguyễn Quốc Anh | Booking: form 3 bước, trạng thái, lịch |
| 3 | Nguyễn Quốc Anh, Võ Ngọc Bảo Trân | REST API, JWT, AJAX (`api.js`), dashboard |
| 4 | Nguyễn Kim Ngân | Đăng nhập/đăng ký, phân quyền, quản lý người dùng |
| 5 | Lê Trường Thịnh | Khách sạn: tìm kiếm, chi tiết, quản lý, upload ảnh |
| 6 | Nguyễn Minh Tiên | Phòng, loại phòng, tiện nghi, kiểm tra phòng trống |