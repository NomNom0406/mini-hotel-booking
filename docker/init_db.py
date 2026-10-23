import os
import pymssql
from dotenv import load_dotenv

load_dotenv()

host   = os.getenv("DB_HOST", "localhost")
port   = int(os.getenv("DB_PORT", 1433))
user   = os.getenv("DB_USER", "sa")
pwd    = os.getenv("DB_PASSWORD", "1")
dbname = os.getenv("DB_NAME", "hotel_db")

conn = pymssql.connect(host=host, port=port, user=user, password=pwd)
conn.autocommit(True)
cur = conn.cursor()
cur.execute(f"IF NOT EXISTS (SELECT 1 FROM sys.databases WHERE name='{dbname}') CREATE DATABASE [{dbname}]")
conn.close()
print(f"[init_db] Database '{dbname}' sẵn sàng.")