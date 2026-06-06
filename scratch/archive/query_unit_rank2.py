# -*- coding: utf-8 -*-
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pymysql
from db_config import DB_CONFIG

UNIT = "福建理工大学"
QUERIES = [
    ("国标", "铁路口岸", "00"),
    ("行标", "电子商务交易产品追溯", "01"),
    ("行标", "追溯信息编码与标识规范", "01"),
    ("行标", "茶叶", "01"),
]


def main():
    conn = pymysql.connect(**DB_CONFIG, cursorclass=pymysql.cursors.DictCursor)
    ROLE = {1: "主起草", 2: "参与起草"}
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT unit_id FROM unit_dict WHERE unit_name = %s", (UNIT,)
            )
            u = cur.fetchone()
            unit_id = u["unit_id"] if u else None
            print(f"单位: {UNIT}  unit_id={unit_id}\n")

            for label, kw, type_no in QUERIES:
                cur.execute(
                    """
                    SELECT id, std_id, std_chinesename, std_type, std_type_no
                    FROM std_base
                    WHERE std_chinesename LIKE %s
                    ORDER BY CHAR_LENGTH(std_chinesename)
                    LIMIT 8
                    """,
                    (f"%{kw}%",),
                )
                rows = cur.fetchall()
                print(f"--- 关键词「{kw}」({label}) 命中 {len(rows)} 条 ---")
                for b in rows:
                    if type_no and b["std_type_no"] != type_no:
                        continue
                    print(f"  [{b['std_type_no']}] {b['std_id']}")
                    print(f"  {b['std_chinesename'][:80]}")
                    if unit_id:
                        cur.execute(
                            """
                            SELECT rank_order, role_type FROM std_unit_relation
                            WHERE base_id=%s AND unit_id=%s
                            """,
                            (b["id"], unit_id),
                        )
                        rel = cur.fetchone()
                        if rel:
                            print(
                                f"  ★ {UNIT} → 第 {rel['rank_order']} 位, {ROLE.get(rel['role_type'])}"
                            )
                        else:
                            print(f"  （无 {UNIT} 关联）")
                    print()

            # 福建理工大学参与的标准里搜铁路/茶叶相关
            if unit_id:
                print("=" * 60)
                print(f"「{UNIT}」参与的标准中含关键词的：")
                cur.execute(
                    """
                    SELECT b.std_id, b.std_type_no, b.std_chinesename, r.rank_order, r.role_type
                    FROM std_unit_relation r
                    JOIN std_base b ON b.id = r.base_id
                    WHERE r.unit_id = %s
                      AND (b.std_chinesename LIKE %s OR b.std_chinesename LIKE %s)
                    ORDER BY b.std_type_no, r.rank_order
                    """,
                    (unit_id, "%铁路口岸%", "%追溯%茶叶%"),
                )
                for row in cur.fetchall():
                    print(
                        f"  [{row['std_type_no']}] 第{row['rank_order']}位 {row['std_id']}"
                    )
                    print(f"    {row['std_chinesename'][:70]}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
