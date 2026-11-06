import os
import re
import unicodedata
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


def slugify(text: str) -> str:
    """Chuyển tên tiếng Việt/có dấu thành slug ASCII an toàn cho tên thư mục."""
    text = text.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text or "unnamed"


def save_image(file, upload_folder: str) -> str | None:
    """Lưu ảnh upload vào upload_folder, trả về tên file hoặc None nếu không hợp lệ."""
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


def save_image_to_folder(file, folder: str, static_root: str) -> str | None:
    """Lưu ảnh vào thư mục con cụ thể (tương đối so với static/).

    folder: đường dẫn tương đối so với static/, ví dụ 'uploads/hotels/doha-central-danang'
    Trả về đường dẫn tương đối so với static/ (dùng được với url_for('static', filename=...))
    hoặc None nếu không hợp lệ.
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

    abs_folder = os.path.abspath(os.path.join(static_root, folder))
    uploads_root = os.path.abspath(os.path.join(static_root, "uploads"))
    # Chặn path traversal
    if os.path.commonpath([abs_folder, uploads_root]) != uploads_root:
        return None

    filename = secure_filename(f"{uuid.uuid4().hex}.{ext}")
    os.makedirs(abs_folder, exist_ok=True)
    file.save(os.path.join(abs_folder, filename))
    return folder.rstrip("/") + "/" + filename


def save_uploaded_image(form, upload_folder: str):
    """Lấy ảnh từ form.image, lưu và trả (filename | None, ok)."""
    file = form.image.data
    if not file or not getattr(file, "filename", ""):
        return None, True
    filename = save_image(file, upload_folder)
    if filename is None:
        form.image.errors.append("Ảnh không hợp lệ (png, jpg, webp, tối đa 2 MB).")
        return None, False
    return filename, True