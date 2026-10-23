import os
from dotenv import load_dotenv

load_dotenv()

def _build_db_uri():
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "1433")
    name = os.getenv("DB_NAME", "hotel_db")
    user = os.getenv("DB_USER", "sa")
    pwd  = os.getenv("DB_PASSWORD", "1")
    return (
        f"mssql+pymssql://{user}:{pwd}@{host}:{port}/{name}"
        f"?charset=utf8"
    )

class BaseConfig:
    SECRET_KEY = os.getenv("SECRET_KEY", "fallback-secret")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "fallback-jwt-secret")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", 5 * 1024 * 1024))
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "static/uploads")
    JWT_ACCESS_TOKEN_EXPIRES = 3600  # 1 giờ

class DevConfig(BaseConfig):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = _build_db_uri()
    SQLALCHEMY_ECHO = False  # bật True nếu muốn xem query

class TestConfig(BaseConfig):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"

class ProdConfig(BaseConfig):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = _build_db_uri()

config_map = {
    "development": DevConfig,
    "testing":     TestConfig,
    "production":  ProdConfig,
}