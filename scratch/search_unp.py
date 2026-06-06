# -*- coding: utf-8 -*-
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pymysql
from db_config import DB_CONFIG

SQL = Path(r"C:\Users\20711\Desktop\mydate\mydate_std_base.sql")
UNIT_ID = 197365
ROLE = {1: "主起草", 2: "参与起草"}


def scan_sql(substr):
    out = []
    with SQL.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if substr not in line:
                continue
            idx = 0
            while True:
                p = line.find(substr, idx)
                if p < 0:
                    break
                start = line.rfind("(", 0, p)
                end = line.find(")", p)
                if start >= 0 and end > start:
                    chunk = line[start + 1 : end]
                    m = re.match(
                        r"(\d+),'([^']*?)','([^']*?)','([^']*?)','[^']*?','((?:[^'\\]|\\.)*?)'",
                        chunk,
                    )
                    if m and substr in m.group(5):
                        out.append(
                            {
                                "base_id": int(m.group(1)),
                                "std_id": m.group(2),
                                "std_type_no": m.group(4),
                                "name": m.group(5).replace("\\'", "'"),
                            }
                        )
                idx = p + 1
    return out


conn = pymysql.connect(**DB_CONFIG, cursorclass=pymysql.cursors.DictCursor)
cur = conn.cursor()

for key in [
    "小家电产品技术要求",
    "手持式电动",
    "手持式电动打蛋器",
    "国际采购  小家电",
    "国际采购 小家电",
    "国际采购",
]:
    recs = scan_sql(key)
    if not recs:
        continue
    print(f"\n=== SQL: {key!r} ({len(recs)}) ===")
    for r in recs[:15]:
        cur.execute(
            "SELECT rank_order, role_type FROM std_unit_relation WHERE base_id=%s AND unit_id=%s",
            (r["base_id"], UNIT_ID),
        )
        rel = cur.fetchone()
        mark = f"  ★ 福建理工 第{rel['rank_order']}位 {ROLE.get(rel['role_type'])}" if rel else ""
        print(f"  {r['std_id']} | {r['name'][:80]}{mark}")

# T/UNP standards with 小家电 or 打蛋
print("\n=== T/UNP + 小家电/打蛋/手持 ===")
recs = scan_sql("T/UNP")
for r in recs:
    n = r["name"]
    if any(k in n for k in ["小家电", "打蛋", "手持", "电器", "家电"]):
        cur.execute(
            "SELECT rank_order, role_type FROM std_unit_relation WHERE base_id=%s AND unit_id=%s",
            (r["base_id"], UNIT_ID),
        )
        rel = cur.fetchone()
        mark = f"  ★ 第{rel['rank_order']}位" if rel else ""
        print(f"  {r['std_id']} | {n}{mark}")

conn.close()
