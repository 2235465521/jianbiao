# -*- coding: utf-8 -*-
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pymysql
from db_config import DB_CONFIG

UNIT = "福建理工大学"
ROLE = {1: "主起草", 2: "参与起草"}


def main():
    conn = pymysql.connect(**DB_CONFIG, cursorclass=pymysql.cursors.DictCursor)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT unit_id FROM unit_dict WHERE unit_name = %s", (UNIT,)
            )
            u = cur.fetchone()
            if not u:
                print("无此单位")
                return
            uid = u["unit_id"]

            cur.execute(
                """
                SELECT b.std_id, b.std_type, b.std_type_no, b.std_chinesename,
                       r.rank_order, r.role_type
                FROM std_unit_relation r
                LEFT JOIN std_base b ON b.id = r.base_id
                WHERE r.unit_id = %s
                ORDER BY r.id DESC
                LIMIT 30
                """,
                (uid,),
            )
            print(f"「{UNIT}」最近30条起草关系:")
            for r in cur.fetchall():
                name = (r["std_chinesename"] or "(主表无名称)")[:50]
                print(
                    f"  第{r['rank_order']}位 {ROLE.get(r['role_type'],'?')} "
                    f"[{r['std_type_no']}] {r['std_id']} | {name}"
                )

            # 全库搜标准名
            for kw, tno, title in [
                ("铁路口岸", "00", "国标-铁路口岸"),
                ("铁路口岸及相关地点", "00", "国标-铁路口岸完整"),
                ("地点代码", "00", "国标-地点代码"),
                ("追溯", "01", "行标-追溯"),
                ("电子商务交易", "01", "行标-电商追溯"),
                ("茶叶", "01", "行标-茶叶"),
            ]:
                cur.execute(
                    """
                    SELECT b.id, b.std_id, b.std_chinesename, r.rank_order, r.role_type
                    FROM std_unit_relation r
                    JOIN std_base b ON b.id = r.base_id
                    WHERE r.unit_id = %s AND b.std_chinesename LIKE %s
                    """,
                    (uid, f"%{kw}%"),
                )
                hits = cur.fetchall()
                if hits:
                    print(f"\n【{title}】命中 {len(hits)} 条:")
                    for h in hits:
                        print(
                            f"  第 {h['rank_order']} 位 | {ROLE.get(h['role_type'])} | "
                            f"{h['std_id']} | {h['std_chinesename']}"
                        )

            # 电子商务那条
            cur.execute(
                "SELECT id, std_id, std_chinesename FROM std_base WHERE std_chinesename LIKE %s",
                ("%电子商务%",),
            )
            for b in cur.fetchall():
                print(f"\n库中「电子商务」相关: {b['std_id']} | {b['std_chinesename']}")
                cur.execute(
                    """
                    SELECT u.unit_name, r.rank_order, r.role_type
                    FROM std_unit_relation r
                    JOIN unit_dict u ON u.unit_id = r.unit_id
                    WHERE r.base_id = %s ORDER BY r.rank_order LIMIT 15
                    """,
                    (b["id"],),
                )
                for x in cur.fetchall():
                    m = " ★" if UNIT in x["unit_name"] else ""
                    print(f"  {x['rank_order']}. {x['unit_name']}{m}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
