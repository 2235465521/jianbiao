# -*- coding: utf-8 -*-
r"""
核对「地标.xlsx」中的记录是否已写入 MySQL。

用法:
    python verify_landmark_import.py
    python verify_landmark_import.py "C:\Users\20711\Desktop\地标.xlsx"
"""
import _path  # noqa: F401

import re
import sys
from pathlib import Path

import pandas as pd
import pymysql

from db_config import DB_CONFIG

DEFAULT_EXCEL = Path(r"C:\Users\20711\Desktop\地标.xlsx")


def clean_id(text):
    if pd.isna(text) or not str(text).strip():
        return ""
    text = " ".join(str(text).upper().strip().split())
    text = text.translate(str.maketrans("∕—＿（）－", "/---(-"))
    text = text.replace("G-B", "GB").replace("GBT", "GB/T")
    for prefix in ["GB/T", "GB/Z", "GB", "ISO/IEC", "ISO", "IEC"]:
        if text.startswith(prefix) and len(text) > len(prefix) and text[len(prefix)].isdigit():
            text = text[: len(prefix)] + " " + text[len(prefix) :]
            break
    return text


def load_std_ids_from_excel(path: Path) -> list[str]:
    df = pd.read_excel(path, sheet_name=0)
    df.columns = [str(c).strip() for c in df.columns]

    col = None
    for name in ("标准号", "标准编号", "编号"):
        if name in df.columns:
            col = name
            break
    if col is None:
        col = df.columns[0]

    ids = []
    for v in df[col]:
        sid = clean_id(v)
        if sid:
            ids.append(sid)
    return ids


def main():
    excel_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_EXCEL
    if not excel_path.is_file():
        print(f"找不到 Excel: {excel_path}")
        sys.exit(1)

    std_ids = load_std_ids_from_excel(excel_path)
    print(f"Excel: {excel_path.name}")
    print(f"共读取 {len(std_ids)} 个标准号\n")

    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            # 库中地标总数
            cur.execute(
                "SELECT COUNT(*) FROM std_base WHERE std_type_no = '02'"
            )
            total_db = cur.fetchone()[0]

            found, missing = [], []
            for sid in std_ids:
                cur.execute(
                    """
                    SELECT b.id, b.std_id, b.std_type, b.std_type_no,
                           b.std_chinesename, b.std_status, b.ex_state,
                           b.release_date, b.implement_date,
                           d.ccs, d.ics, d.suggest_dept, d.approve_dept,
                           d.industry_type, d.record_no
                    FROM std_base b
                    LEFT JOIN std_db_detail d ON d.base_id = b.id
                    WHERE b.std_id = %s
                    """,
                    (sid,),
                )
                row = cur.fetchone()
                if row:
                    found.append((sid, row))
                else:
                    # 容错：再试去掉空格后的号
                    cur.execute(
                        "SELECT std_id FROM std_base WHERE REPLACE(std_id, ' ', '') = %s",
                        (sid.replace(" ", ""),),
                    )
                    alt = cur.fetchone()
                    if alt:
                        cur.execute(
                            """
                            SELECT b.id, b.std_id, b.std_type, b.std_type_no,
                                   b.std_chinesename, b.std_status, b.ex_state,
                                   b.release_date, b.implement_date,
                                   d.ccs, d.ics, d.suggest_dept, d.approve_dept,
                                   d.industry_type, d.record_no
                            FROM std_base b
                            LEFT JOIN std_db_detail d ON d.base_id = b.id
                            WHERE REPLACE(b.std_id, ' ', '') = %s
                            """,
                            (sid.replace(" ", ""),),
                        )
                        found.append((sid, cur.fetchone()))
                    else:
                        missing.append(sid)

        print("=" * 60)
        print(f"数据库 `{DB_CONFIG['database']}` 中地标 (std_type_no=02) 总数: {total_db}")
        print(f"本次 Excel 核对: 找到 {len(found)} / {len(std_ids)}")
        print("=" * 60)

        if found:
            print("\n【已入库】")
            for excel_id, r in found:
                db_id, std_id, std_type, type_no, ch_name, status, ex_state = r[:7]
                ok_mark = "✓" if type_no == "02" else "⚠ 类型不是地标"
                print(f"\n{ok_mark} Excel号: {excel_id}")
                print(f"   库中标准号: {std_id}  |  类型: {std_type} ({type_no})  |  状态: {status}")
                print(f"   中文名: {(ch_name or '')[:50]}")
                print(f"   发布/实施: {r[7]} / {r[8]}  |  CCS/ICS: {r[9]} / {r[10]}")
                if r[11] or r[12]:
                    print(f"   提出/批准: {r[11]} / {r[12]}")
                if r[13] or r[14]:
                    print(f"   行业/备案: {r[13]} / {r[14]}  (详情表字段，Web工具可能未写入)")

        if missing:
            print("\n【未找到】")
            for sid in missing:
                print(f"  ✗ {sid}")

        # 最近导入的 20 条地标（按 id 倒序）
        print("\n" + "=" * 60)
        print("【库中最近 20 条地标（按 id 倒序，供对照）】")
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT b.std_id, b.std_chinesename, b.std_status, b.create_time
                FROM std_base b
                WHERE b.std_type_no = '02'
                ORDER BY b.id DESC
                LIMIT 20
                """
            )
            rows = cur.fetchall()
            if not rows:
                print("  (暂无 std_type_no=02 的记录)")
            for i, (sid, name, st, ct) in enumerate(rows, 1):
                print(f"  {i:2}. {sid}  |  {st}  |  {(name or '')[:30]}  |  {ct}")

        print("\n" + "=" * 60)
        if len(found) == len(std_ids) and all(r[1][3] == "02" for r in found):
            print("结论: 20 条均已入库，且类型为地标 (02)。")
        elif len(found) == len(std_ids):
            print("结论: 20 条均在 std_base 中，但部分类型编号不是 02，请检查导入时是否强制选了「地标」。")
        else:
            print(f"结论: 有 {len(missing)} 条未在库中找到，请核对标准号清洗是否与库中一致。")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
