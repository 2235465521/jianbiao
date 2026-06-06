# -*- coding: utf-8 -*-
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pymysql
from db_config import DB_CONFIG

UNIT = "福建理工大学"


def main():
    conn = pymysql.connect(**DB_CONFIG, cursorclass=pymysql.cursors.DictCursor)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM std_base")
            print(f"std_base 总条数: {cur.fetchone()['c']}")
            cur.execute("SELECT COUNT(*) AS c FROM std_unit_relation")
            print(f"std_unit_relation 总条数: {cur.fetchone()['c']}")

            for kw in ["铁路口岸", "世界主要铁路", "追溯", "电子商务", "茶叶"]:
                cur.execute(
                    "SELECT COUNT(*) AS c FROM std_base WHERE std_chinesename LIKE %s",
                    (f"%{kw}%",),
                )
                print(f"  名称含「{kw}」: {cur.fetchone()['c']}")

            cur.execute(
                """
                SELECT b.std_id, b.std_type_no, b.std_chinesename, h.draft_unit
                FROM std_extend_h h
                JOIN std_base b ON b.id = h.base_id
                WHERE h.draft_unit LIKE %s
                LIMIT 20
                """,
                (f"%{UNIT}%",),
            )
            rows = cur.fetchall()
            print(f"\n起草单位原文含「{UNIT}」的标准（最多20条）:")
            for r in rows:
                name = r["std_chinesename"] or ""
                if "铁路" in name or "口岸" in name or ("追溯" in name and "茶" in name):
                    print(f"  ★ [{r['std_type_no']}] {r['std_id']} | {name[:60]}")
                    du = r["draft_unit"] or ""
                    # 简单算排名：按逗号顿号分割
                    parts = [p.strip() for p in du.replace("、", ",").split(",") if p.strip()]
                    rank = None
                    for i, p in enumerate(parts, 1):
                        if UNIT in p:
                            rank = i
                            break
                    print(f"     原文排名约第 {rank} 位（按标点拆分）" if rank else "     未在拆分列表中找到精确名")

            cur.execute(
                """
                SELECT b.std_id, b.std_chinesename, r.rank_order, r.role_type
                FROM std_unit_relation r
                JOIN std_base b ON b.id = r.base_id
                JOIN unit_dict u ON u.unit_id = r.unit_id
                WHERE u.unit_name = %s
                  AND (b.std_chinesename LIKE %s OR b.std_chinesename LIKE %s
                       OR b.std_chinesename LIKE %s)
                """,
                (UNIT, "%铁路%", "%口岸%", "%追溯%茶%"),
            )
            rels = cur.fetchall()
            print(f"\n结构化关系表中匹配:")
            for r in rels:
                print(f"  第{r['rank_order']}位 role={r['role_type']} | {r['std_id']} | {(r['std_chinesename'] or '')[:55]}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
