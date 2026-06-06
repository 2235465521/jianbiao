import pandas as pd
import pymysql
import sys
import os

def get_db_connection():
    return pymysql.connect(
        host='127.0.0.1',
        port=3306,
        user='root',
        password='lsj223546',
        database='mydate',
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

def run_supplemental_gb_migration():
    file_path = r"E:\Downloads\详情信息\详情信息表.xlsx"
    print(f"[START] 读取大型国标详情数据... : {file_path}")
    
    df = pd.read_excel(file_path, dtype=str)
    print(f"[SUCCESS] Excel 读取完成，共计 {len(df)} 行数据。")

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 1. 拉取现有国标 base_id 映射
        print("[PROCESS] 正在拉取国标主映射...")
        cursor.execute("SELECT id, std_id FROM std_base WHERE std_type_no = '00'")
        id_mapping = {r['std_id']: r['id'] for r in cursor.fetchall()}
        
        # 2. 灌入 std_gb_detail
        print("[PROCESS] 正在执行批量灌库 (INSERT IGNORE)...")
        detail_batch = []
        for _, row in df.iterrows():
            sid = str(row.get('bz_id', '')).strip()
            if sid not in id_mapping: continue
            
            base_id = id_mapping[sid]
            ccs = str(row.get('ccs', '')).strip()
            ics = str(row.get('ics', '')).strip()
            drafter = str(row.get('drafter', '')).strip()
            report_unit = str(row.get('report_unit', '')).strip()
            sub_report_unit = str(row.get('sub_report_unit', '')).strip()

            def n(v): return None if not v or v == 'nan' else v
            
            detail_batch.append((base_id, n(ccs), n(ics), n(drafter), n(report_unit), n(sub_report_unit)))

        if detail_batch:
            # 使用 INSERT IGNORE 以防 ID 冲突（已有记录则不录入）
            sql = """
                INSERT IGNORE INTO std_gb_detail (base_id, ccs, ics, drafter, report_unit, sub_report_unit)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.executemany(sql, detail_batch)
            conn.commit()
            print(f"[FINISHED] 国标详情补全完成！成功新增或跳过，总处理: {len(detail_batch)} 条。")
        else:
            print("[WARN] 没有找到匹配的国标记录，请检查 Excel 中 bz_id 的格式是否与数据库一致。")

    except Exception as e:
        conn.rollback()
        print(f"[ERROR] 迁移失败: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    run_supplemental_gb_migration()
