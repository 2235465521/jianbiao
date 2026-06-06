# -*- coding: utf-8 -*-
"""从库 + SQL 备份中查福建理工大学在指定标准中的起草排名"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pymysql
from db_config import DB_CONFIG

UNIT = "福建理工大学"
TARGETS = [
    ("国标", "中国及世界主要铁路口岸及相关地点代码"),
    ("行标", "电子商务交易产品追溯信息编码与标识规范 茶叶"),
]
SQL_BASE = Path(r"C:\Users\20711\Desktop\mydate\mydate_std_base.sql")
ROLE = {1: "主起草", 2: "参与起草"}


def find_base_in_sql_dump(name_key):
    """在 std_base.sql 中定位 base_id / std_id"""
    if not SQL_BASE.is_file():
        return []
    hits = []
    buf = ""
    with SQL_BASE.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if name_key not in line:
                continue
            # 拆 INSERT 中的元组
            for m in re.finditer(
                r"\((\d+),'([^']*?)','([^']*?)','([^']*?)'.*?'((?:[^'\\]|\\.)*?)'",
                line,
            ):
                bid, std_id, stype, tno, ch = m.groups()
                if name_key in ch:
                    hits.append(
                        {
                            "base_id": int(bid),
                            "std_id": std_id,
                            "std_type_no": tno,
                            "std_chinesename": ch[:120],
                        }
                    )
    return hits


def rank_from_extend_h(cur, base_id, unit_name):
    cur.execute(
        "SELECT draft_unit FROM std_extend_h WHERE base_id=%s LIMIT 1", (base_id,)
    )
    row = cur.fetchone()
    if not row or not row.get("draft_unit"):
        return None, []
    text = row["draft_unit"]
    parts = re.split(r"[，,、;；\n]", text)
    parts = [p.strip() for p in parts if p.strip()]
    rank = None
    for i, p in enumerate(parts, 1):
        if unit_name in p:
            rank = i
            break
    return rank, parts


def main():
    conn = pymysql.connect(**DB_CONFIG, cursorclass=pymysql.cursors.DictCursor)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT unit_id FROM unit_dict WHERE unit_name=%s", (UNIT,)
            )
            u = cur.fetchone()
            unit_id = u["unit_id"] if u else None
            print(f"单位: {UNIT}  unit_id={unit_id}\n")

            for label, name_key in TARGETS:
                print("=" * 70)
                print(f"【{label}】{name_key}")
                print("-" * 70)

                # 1) 在线库 std_base
                cur.execute(
                    "SELECT id, std_id, std_type_no, std_chinesename FROM std_base WHERE std_chinesename LIKE %s",
                    (f"%{name_key}%",),
                )
                online = cur.fetchall()

                # 2) SQL 备份
                dump_hits = find_base_in_sql_dump(name_key)

                bases = {b["id"]: b for b in online}
                for d in dump_hits:
                    if d["base_id"] not in bases:
                        bases[d["base_id"]] = {
                            "id": d["base_id"],
                            "std_id": d["std_id"],
                            "std_type_no": d["std_type_no"],
                            "std_chinesename": d["std_chinesename"],
                            "_from": "sql_dump",
                        }

                if not bases:
                    print("  未在数据库及 SQL 备份中找到该标准。")
                    continue

                for base_id, b in bases.items():
                    src = b.get("_from", "mysql")
                    print(f"\n  标准号: {b['std_id']}")
                    print(f"  中文名: {b['std_chinesename']}")
                    print(f"  base_id: {base_id}  (来源: {src})")

                    if not unit_id:
                        continue

                    cur.execute(
                        """
                        SELECT rank_order, role_type FROM std_unit_relation
                        WHERE base_id=%s AND unit_id=%s
                        """,
                        (base_id, unit_id),
                    )
                    rel = cur.fetchone()
                    if rel:
                        print(
                            f"  ★ {UNIT} → 第 {rel['rank_order']} 位  |  {ROLE.get(rel['role_type'], rel['role_type'])}"
                        )
                    else:
                        print(f"  ★ {UNIT} → 未在 std_unit_relation 中关联")

                    rank_h, parts = rank_from_extend_h(cur, base_id, UNIT)
                    if rank_h:
                        print(f"  ★ 起草单位原文顺序 → 约第 {rank_h} 位（按标点拆分）")

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
                        print(f"  全部起草单位（共 {len(all_u)} 家，★ 为福建理工大学）:")
                        for x in all_u[:25]:
                            mark = " ★" if UNIT in x["unit_name"] else ""
                            print(
                                f"    {x['rank_order']:>3}. [{ROLE.get(x['role_type'],'?')}] {x['unit_name']}{mark}"
                            )
                        if len(all_u) > 25:
                            print(f"    … 另有 {len(all_u)-25} 家未列出")
                    elif parts:
                        print("  起草单位（仅 extend_h 原文，前15家）:")
                        for i, p in enumerate(parts[:15], 1):
                            mark = " ★" if UNIT in p else ""
                            print(f"    {i:>3}. {p}{mark}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
