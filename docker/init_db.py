import os
import re
import sys
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy_utils import create_database, database_exists

load_dotenv()

DB_USER = os.getenv("DB_USER", "sa")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = os.getenv("DB_PORT", "1433")
DB_NAME = os.getenv("DB_NAME", "hotel_booking")
DB_NAME_TEST = os.getenv("DB_NAME_TEST", "hotel_booking_test")

_NAME_RE = re.compile(r'^[A-Za-z0-9_]+$')


def make_url(dbname):
    pw = quote_plus(DB_PASSWORD)
    return (
        f"mssql+pymssql://{DB_USER}:{pw}"
        f"@{DB_HOST}:{DB_PORT}/{dbname}?charset=utf8"
    )


def ensure_db(dbname):
    if not _NAME_RE.match(dbname):
        print(f"[init_db] Tên DB không hợp lệ: {dbname}", file=sys.stderr)
        sys.exit(1)
    url = make_url(dbname)
    if not database_exists(url):
        create_database(url)
        print(f"[init_db] Đã tạo database '{dbname}'.")
    else:
        print(f"[init_db] Database '{dbname}' đã tồn tại.")


ensure_db(DB_NAME)
ensure_db(DB_NAME_TEST)