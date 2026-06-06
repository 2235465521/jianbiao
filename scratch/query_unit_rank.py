# -*- coding: utf-8 -*-
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pymysql
from db_config import DB_CONFIG

UNIT = "福建理工大学"
STANDARDS = [
    ("国标", "中国及世界主要铁路口岸及相关地点代码"),
    ("行标", "电子商务交易产品追溯信息编码与标识规范 茶叶"),
]

ROLE = {1: "主起草", 2: "参与起草"}


def main():
    conn = pymysql.connect(**DB_CONFIG, cursorclass=pymysql.cursors.DictCursor)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT unit_id, unit_name FROM unit_dict WHERE unit_name LIKE %s",
                (f"%{UNIT}%",),
            )
            units = cur.fetchall()
            print("=== 单位匹配 ===")
            for u in units:
                print(f"  unit_id={u['unit_id']}  {u['unit_name']}")
            if not units:
                print("  未找到该单位")
                return
            unit_ids = [u["unit_id"] for u in units]

            for std_type_label, name_key in STANDARDS:
                print(f"\n{'='*60}")
                print(f"【{std_type_label}】{name_key}")
                cur.execute(
                    """
                    SELECT id, std_id, std_type, std_type_no, std_chinesename
                    FROM std_base
                    WHERE std_chinesename LIKE %s
                    ORDER BY id
                    LIMIT 5
                    """,
                    (f"%{name_key}%",),
                )
                bases = cur.fetchall()
                if not bases:
                    print("  未找到该标准（按中文名模糊匹配）")
                    continue
                for b in bases:
                    print(f"\n  标准号: {b['std_id']}  |  类型: {b['std_type']} ({b['std_type_no']})")
                    print(f"  中文名: {b['std_chinesename']}")
                    base_id = b["id"]
                    ph = ",".join(["%s"] * len(unit_ids))
                    cur.execute(
                        f"""
                        SELECT r.rank_order, r.role_type, u.unit_name
                        FROM std_unit_relation r
                        JOIN unit_dict u ON u.unit_id = r.unit_id
                        WHERE r.base_id = %s AND r.unit_id IN ({ph})
                        """,
                        [base_id] + unit_ids,
                    )
                    hits = cur.fetchall()
                    if not hits:
                        print(f"  → 「{UNIT}」未出现在该标准的起草单位关系中")
                    else:
                        for h in hits:
                            print(
                                f"  → 「{h['unit_name']}」排名: 第 {h['rank_order']} 位"
                                f"  |  角色: {ROLE.get(h['role_type'], h['role_type'])}"
                            )
                    cur.execute(
                        """
                        SELECT r.rank_order, r.role_type, u.unit_name
                        FROM std_unit_relation r
                        JOIN unit_dict u ON u.unit_id = r.unit_id
                        WHERE r.base_id = %s
                        ORDER BY r.rank_order, r.id
                        """,
                        (base_id,),
                    )
                    all_units = cur.fetchall()
                    print(f"\n  该标准全部起草单位（共 {len(all_units)} 家）:")
                    for r in all_units:
                        mark = "  ★" if any(u["unit_name"] == r["unit_name"] or UNIT in r["unit_name"] for u in units) and r["unit_name"] in [h["unit_name"] for h in hits] else ""
                        if not mark and UNIT in r["unit_name"]:
                            mark = "  ★"
                        print(
                            f"    {r['rank_order']:>3}. [{ROLE.get(r['role_type'], '?')}] {r['unit_name']}{mark}"
                        )
                    cur.execute(
                        "SELECT draft_unit FROM std_extend_h WHERE base_id = %s LIMIT 1",
                        (base_id,),
                    )
                    ext = cur.fetchone()
                    if ext and ext.get("draft_unit"):
                        print(f"\n  原文起草单位字段（std_extend_h）片段:")
                        txt = ext["draft_unit"]
                        if UNIT in txt:
                            idx = txt.find(UNIT)
                            print(f"    …{txt[max(0,idx-30):idx+len(UNIT)+30]}…")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
