import pymysql
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))
from web_import_tool import update_pedigree

DB_CONFIG = {
    'host': '127.0.0.1',
    'port': 3306,
    'user': 'root',
    'password': 'lsj223546',
    'database': 'mydate',
    'charset': 'utf8mb4'
}

conn = pymysql.connect(**DB_CONFIG)
cursor = conn.cursor()

# Insert replace logic first
cursor.execute("INSERT IGNORE INTO std_replace (base_id, replace_id, replace_std_name, replace_type) VALUES (842143, 318, 'GB 11557-2011', '全部代替')")

# Run update_pedigree
update_pedigree(cursor, 842143, 'GB 11557-2026', [318])

conn.commit()
print("Done")
