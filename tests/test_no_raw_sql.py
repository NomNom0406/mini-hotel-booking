import os
import re

# Pattern phát hiện raw SQL trong code
RAW_SQL_PATTERNS = [
    r'db\.session\.execute\s*\(\s*["\']',     # db.session.execute("SELECT...")
    r'db\.engine\.execute\s*\(',               # db.engine.execute(
    r'text\s*\(\s*["\']SELECT',               # text("SELECT
    r'text\s*\(\s*["\']INSERT',               # text("INSERT
    r'text\s*\(\s*["\']UPDATE',               # text("UPDATE
    r'text\s*\(\s*["\']DELETE',               # text("DELETE
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
    """Kiểm tra không dùng f-string hoặc % format trong query."""
    violations = []
    pattern = r'filter\(.*f["\'].*\)'
    for filepath in _get_all_py_files():
        with open(filepath, encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                if re.search(pattern, line):
                    violations.append(f"{filepath}:{lineno} → {line.strip()}")

    assert not violations, (
        f"Phát hiện {len(violations)} chỗ dùng f-string trong filter:\n" +
        "\n".join(violations)
    )
