# Quy tắc làm việc nhóm

## Quy tắc nhánh
- KHÔNG push thẳng lên `main` hoặc `dev`
- Mỗi người tạo nhánh riêng theo format:
  - `feature/ten-tinh-nang` — làm tính năng mới
  - `fix/ten-loi` — sửa bug
  - Ví dụ: `feature/login-form`, `fix/booking-date`

## Quy tắc commit
Viết commit message rõ ràng theo format:
- `feat(auth): add login form`
- `fix(booking): fix date validation`
- `chore(docker): update dockerfile`
- `test(api): add room availability test`

## Quy tắc Pull Request
1. Code xong → push nhánh lên GitHub
2. Tạo PR vào nhánh `dev` (KHÔNG vào `main`)
3. Tag ít nhất 1 người review (ưu tiên leader)
4. Chờ được approve mới merge
5. Merge xong thì xóa nhánh cũ

## Luồng làm việc hàng ngày
1. Trước khi code: git pull origin dev
2. Tạo nhánh mới từ dev
3. Code → commit thường xuyên
4. Push → tạo PR → tag người review
5. Sau khi PR được merge: quay lại bước 1
