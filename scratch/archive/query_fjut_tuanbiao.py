# -*- coding: utf-8 -*-
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pymysql
from db_config import DB_CONFIG

UNIT = "福建理工大学"
UNIT_ID = 197365
NAME_KEYS = ["手持式电动打蛋器", "小家电产品技术要求", "国际采购"]
SQL_BASE = Path(r"C:\Users\20711\Desktop\mydate\mydate_std_base.sql")
ROLE = {1: "主起草", 2: "参与起草"}


def parse_tuple_chunk(chunk):
    m = re.match(
        r"(\d+),'([^']*?)','([^']*?)','([^']*?)','[^']*?','((?:[^'\\]|\\.)*?)'",
        chunk,
    )
    if m:
        return {
            "base_id": int(m.group(1)),
            "std_id": m.group(2),
            "std_type_no": m.group(4),
            "std_chinesename": m.group(5).replace("\\'", "'"),
        }
    return None


def find_std_in_sql(keys):
    hits = []
    seen = set()
    with SQL_BASE.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if not all(k in line for k in ["手持式电动打蛋器", "国际采购"]):
                if "手持式电动打蛋器" not in line:
                    continue
            idx = 0
            while True:
                p = line.find("手持式电动打蛋器", idx)
                if p < 0:
                    break
                start = line.rfind("(", 0, p)
                end = line.find(")", p)
                if start >= 0 and end > start:
                    rec = parse_tuple_chunk(line[start + 1 : end])
                    if rec and rec["base_id"] not in seen:
                        seen.add(rec["base_id"])
                        hits.append(rec)
                idx = p + 1
    return hits


def main():
    conn = pymysql.connect(**DB_CONFIG, cursorclass=pymysql.cursors.DictCursor)
    try:
        with conn.cursor() as cur:
            print(f"单位: {UNIT}  unit_id={UNIT_ID}\n")
            print("【团标】国际采购 小家电产品技术要求 手持式电动打蛋器")
            print("-" * 70)

            cur.execute(
                """
                SELECT id, std_id, std_type_no, std_chinesename FROM std_base
                WHERE std_chinesename LIKE %s
                   OR std_chinesename LIKE %s
                """,
                ("%手持式电动打蛋器%", "%国际采购%小家电%打蛋器%"),
            )
            online = cur.fetchall()
            dump = find_std_in_sql(NAME_KEYS)

            bases = {b["id"]: b for b in online}
            for d in dump:
                if d["base_id"] not in bases:
                    bases[d["base_id"]] = {
                        "id": d["base_id"],
                        "std_id": d["std_id"],
                        "std_type_no": d["std_type_no"],
                        "std_chinesename": d["std_chinesename"],
                    }

            if not bases:
                print("未找到该标准。")
                return

            for base_id, b in bases.items():
                print(f"\n标准号: {b['std_id']}")
                print(f"中文名: {b['std_chinesename']}")
                print(f"base_id: {base_id}")

                cur.execute(
                    """
                    SELECT rank_order, role_type FROM std_unit_relation
                    WHERE base_id=%s AND unit_id=%s
                    """,
                    (base_id, UNIT_ID),
                )
                rel = cur.fetchone()
                if rel:
                    print(
                        f"★ {UNIT} → 第 {rel['rank_order']} 位 | {ROLE.get(rel['role_type'], rel['role_type'])}"
                    )
                else:
                    print(f"★ {UNIT} → 未在 std_unit_relation 中关联")

                cur.execute(
                    "SELECT draft_unit FROM std_extend_h WHERE base_id=%s LIMIT 1",
                    (base_id,),
                )
                ext = cur.fetchone()
                if ext and ext.get("draft_unit"):
                    parts = re.split(r"[，,、;；\n]", ext["draft_unit"])
                    parts = [p.strip() for p in parts if p.strip()]
                    for i, p in enumerate(parts, 1):
                        if UNIT in p:
                            print(f"★ 起草单位原文顺序 → 约第 {i} 位")
                            break

                cur.execute(
                    """
                    SELECT u.unit_name, r.rank_order, r.role_type
                    FROM std_unit_relation r
                    JOIN unit_dict u ON u.unit_id = r.unit_id
                    WHERE r.base_id=%s ORDER BY r.rank_order, r.id
                    """,
                    (base_id,),
                )
                all_u = cur.fetchall()
                if all_u:
                    print(f"全部起草单位（共 {len(all_u)} 家）:")
                    for x in all_u:
                        mark = " ★" if UNIT in x["unit_name"] else ""
                        print(
                            f"  {x['rank_order']:>3}. [{ROLE.get(x['role_type'], '?')}] {x['unit_name']}{mark}"
                        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
