import os
import re

# Pattern phát hiện raw SQL trong code
RAW_SQL_PATTERNS = [
    r'db\.session\.execute\s*\(\s*["\']',       # execute("SELECT...")
    r'db\.session\.execute\s*\(\s*f["\']',       # execute(f"SELECT...")
    r'db\.session\.execute\s*\(\s*["\'].*\+',    # execute("SELECT..." + var)
    r'db\.engine\.execute\s*\(',                 # engine.execute(
    r'text\s*\(\s*["\']SELECT',                 # text("SELECT
    r'text\s*\(\s*["\']INSERT',                 # text("INSERT
    r'text\s*\(\s*["\']UPDATE',                 # text("UPDATE
    r'text\s*\(\s*["\']DELETE',                 # text("DELETE
    r'(?<!getenv\()SECRET_KEY\s*=\s*["\'][^"\']{8,}',  # hardcode secret key
]

APP_DIR = os.path.join(os.path.dirname(__file__), "..", "app")


def _get_all_py_files():
    py_files = []
    for root, _, files in os.walk(APP_DIR):
        for f in files:
            if f.endswith(".py"):
                py_files.append(os.path.join(root, f))
    return py_files


def test_no_raw_sql():
    violations = []
    for filepath in _get_all_py_files():
        with open(filepath, encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                for pattern in RAW_SQL_PATTERNS:
                    if re.search(pattern, line, re.IGNORECASE):
                        violations.append(f"{filepath}:{lineno} → {line.strip()}")

    assert not violations, (
        f"Phát hiện {len(violations)} chỗ dùng raw SQL:\n" +
        "\n".join(violations)
    )


def test_no_string_format_in_query():
    """Kiểm tra không dùng f-string hoặc % format trực tiếp trong raw SQL."""
    violations = []
    pattern = r'filter\(.*f["\'].*(SELECT|INSERT|UPDATE|DELETE).*\)'
    for filepath in _get_all_py_files():
        with open(filepath, encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                if re.search(pattern, line):
                    violations.append(f"{filepath}:{lineno} → {line.strip()}")

    assert not violations, (
        f"Phát hiện {len(violations)} chỗ dùng f-string SQL trong filter:\n" +
        "\n".join(violations)
    )


def test_no_unsafe_in_templates():
    """Kiểm tra không dùng | safe với input người dùng trong templates."""
    templates_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
    if not os.path.exists(templates_dir):
        return  # templates chưa có, bỏ qua

    violations = []
    pattern = r'\|\s*safe'
    for root, _, files in os.walk(templates_dir):
        for f in files:
            if f.endswith(".html"):
                filepath = os.path.join(root, f)
                with open(filepath, encoding="utf-8") as fh:
                    for lineno, line in enumerate(fh, 1):
                        if re.search(pattern, line):
                            violations.append(f"{filepath}:{lineno} → {line.strip()}")

    assert not violations, (
        f"Phát hiện {len(violations)} chỗ dùng | safe trong template:\n" +
        "\n".join(violations)
    )