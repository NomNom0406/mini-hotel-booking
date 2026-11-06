import os
import uuid
from urllib.parse import urlparse, urljoin
from flask import request
from werkzeug.utils import secure_filename
import bleach

ALLOWED_TAGS: list[str] = []
ALLOWED_ATTRIBUTES: dict = {}

def sanitize(text: str) -> str:
    """Strip toàn bộ HTML ra khỏi input người dùng."""
    return bleach.clean(text, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES, strip=True)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
MAX_IMAGE_BYTES = 2 * 1024 * 1024  # 2 MB


def is_safe_url(target: str) -> bool:
    """Chỉ chấp nhận redirect nội bộ, chặn open redirect."""
    ref_url  = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return (
        test_url.scheme in ("http", "https")
        and ref_url.netloc == test_url.netloc
    )


def save_image(file, upload_folder: str) -> str | None:
    """
    Lưu ảnh upload, trả về tên file đã lưu hoặc None nếu không hợp lệ.
    Kiểm tra đuôi (png/jpg/jpeg/webp), giới hạn 2 MB, đổi tên bằng UUID.
    """
    if not file or file.filename == "":
        return None

    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return None

    content = file.read()
    if len(content) > MAX_IMAGE_BYTES:
        return None
    file.seek(0)

    filename = secure_filename(f"{uuid.uuid4().hex}.{ext}")
    os.makedirs(upload_folder, exist_ok=True)
    file.save(os.path.join(upload_folder, filename))
    return filename


def save_uploaded_image(form, upload_folder: str):
    """Lấy ảnh từ form.image, lưu và trả (filename | None, ok).

    Không chọn ảnh thì (None, True); ảnh sai thì (None, False) kèm lỗi ở form.
    """
    file = form.image.data
    if not file or not getattr(file, "filename", ""):
        return None, True
    filename = save_image(file, upload_folder)
    if filename is None:
        form.image.errors.append("Ảnh không hợp lệ (png, jpg, webp, tối đa 2 MB).")
        return None, False
    return filename, True