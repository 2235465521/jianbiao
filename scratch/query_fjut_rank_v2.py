# -*- coding: utf-8 -*-
"""查福建理工大学在指定标准中的起草排名（库 + SQL 备份）"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pymysql
from db_config import DB_CONFIG

UNIT = "福建理工大学"
UNIT_ID = 197365
TARGETS = [
    ("国标", "中国及世界主要铁路口岸及相关地点代码", ["铁路口岸", "口岸及相关地点"]),
    ("行标", "电子商务交易产品追溯信息编码与标识规范 茶叶", ["追溯信息编码与标识规范", "追溯信息编码", "茶叶"]),
]
SQL_BASE = Path(r"C:\Users\20711\Desktop\mydate\mydate_std_base.sql")
ROLE = {1: "主起草", 2: "参与起草"}


def parse_tuple_chunk(chunk):
    """从 INSERT 元组片段解析 id, std_id, std_type_no, chinese_name"""
    # 字段: id, std_id, std_type, std_type_no, created_at, chinese, english, ...
    m = re.match(
        r"(\d+),'([^']*?)','([^']*?)','([^']*?)','[^']*?','((?:[^'\\]|\\.)*?)'",
        chunk,
    )
    if m:
        return {
            "base_id": int(m.group(1)),
            "std_id": m.group(2),
            "std_type": m.group(3),
            "std_type_no": m.group(4),
            "std_chinesename": m.group(5).replace("\\'", "'"),
        }
    return None


def find_std_in_sql(keys):
    if not SQL_BASE.is_file():
        return []
    hits = []
    seen = set()
    with SQL_BASE.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if not any(k in line for k in keys):
                continue
            for key in keys:
                idx = 0
                while True:
                    p = line.find(key, idx)
                    if p < 0:
                        break
                    start = line.rfind("(", 0, p)
                    end = line.find(")", p)
                    if start >= 0 and end > start:
                        chunk = line[start + 1 : end]
                        rec = parse_tuple_chunk(chunk)
                        if rec and rec["base_id"] not in seen:
                            if any(k in rec["std_chinesename"] for k in keys):
                                seen.add(rec["base_id"])
                                hits.append(rec)
                    idx = p + len(key)
    return hits


def rank_from_draft_text(text, unit_name):
    if not text:
        return None, []
    parts = re.split(r"[，,、;；\n]", text)
    parts = [p.strip() for p in parts if p.strip()]
    rank = None
    for i, p in enumerate(parts, 1):
        if unit_name in p:
            rank = i
            break
    return rank, parts


def print_rank(cur, base_id, b, unit_id):
    print(f"\n  标准号: {b['std_id']}")
    print(f"  中文名: {b['std_chinesename']}")
    print(f"  base_id: {base_id}")

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

    cur.execute(
        "SELECT draft_unit FROM std_extend_h WHERE base_id=%s LIMIT 1", (base_id,)
    )
    ext = cur.fetchone()
    if ext and ext.get("draft_unit"):
        rank_h, parts = rank_from_draft_text(ext["draft_unit"], UNIT)
        if rank_h:
            print(f"  ★ 起草单位原文顺序 → 约第 {rank_h} 位（按标点拆分）")
        if not rel and parts:
            print("  起草单位（extend_h 原文，前15家）:")
            for i, p in enumerate(parts[:15], 1):
                mark = " ★" if UNIT in p else ""
                print(f"    {i:>3}. {p}{mark}")

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
        print(f"  全部起草单位（共 {len(all_u)} 家）:")
        for x in all_u[:25]:
            mark = " ★" if UNIT in x["unit_name"] else ""
            print(
                f"    {x['rank_order']:>3}. [{ROLE.get(x['role_type'], '?')}] {x['unit_name']}{mark}"
            )
        if len(all_u) > 25:
            print(f"    … 另有 {len(all_u) - 25} 家未列出")


def main():
    conn = pymysql.connect(**DB_CONFIG, cursorclass=pymysql.cursors.DictCursor)
    try:
        with conn.cursor() as cur:
            print(f"单位: {UNIT}  unit_id={UNIT_ID}\n")

            for label, full_name, keys in TARGETS:
                print("=" * 70)
                print(f"【{label}】{full_name}")
                print("-" * 70)

                search_keys = list({full_name, *keys})
                cur.execute(
                    "SELECT id, std_id, std_type_no, std_chinesename FROM std_base WHERE std_chinesename LIKE %s",
                    (f"%{keys[0]}%",),
                )
                online = cur.fetchall()
                dump_hits = find_std_in_sql(search_keys)

                bases = {b["id"]: b for b in online}
                for d in dump_hits:
                    bid = d["base_id"]
                    if bid not in bases:
                        bases[bid] = {
                            "id": bid,
                            "std_id": d["std_id"],
                            "std_type_no": d["std_type_no"],
                            "std_chinesename": d["std_chinesename"],
                        }

                if not bases:
                    print("  未在数据库及 SQL 备份中找到该标准。")
                    continue

                for base_id, b in bases.items():
                    print_rank(cur, base_id, b, UNIT_ID)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
