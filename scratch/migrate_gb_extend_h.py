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

def run_gb_extend_migration():
    file_path = r"E:\Downloads\详情信息\详情信息表.xlsx"
    print(f"[START] 正在读取国标详情数据文件... : {file_path}")
    
    df = pd.read_excel(file_path, dtype=str)
    print(f"[SUCCESS] Excel 读取完成，共计 {len(df)} 行数据。")

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 1. 拉取现有国标 base_id 映射 (确保只匹配国标)
        print("[PROCESS] 正在建立国标 ID 映射映射...")
        cursor.execute("SELECT id, std_id FROM std_base WHERE std_type_no = '00'")
        id_mapping = {r['std_id']: r['id'] for r in cursor.fetchall()}
        
        # 2. 追加至 std_extend_h
        print("[PROCESS] 正在追加起草单位数据 (Mode: Append)...")
        batch_data = []
        for _, row in df.iterrows():
            sid = str(row.get('bz_id', '')).strip()
            if sid not in id_mapping: continue
            
            base_id = id_mapping[sid]
            draft_unit = str(row.get('draft_unit', '')).strip()
            
            if not draft_unit or draft_unit == 'nan':
                continue
            
            # (base_id, std_type, draft_unit)
            batch_data.append((base_id, '国标', draft_unit))

        if batch_data:
            sql = "INSERT INTO std_extend_h (base_id, std_type, draft_unit) VALUES (%s, %s, %s)"
            cursor.executemany(sql, batch_data)
            conn.commit()
            print(f"[FINISHED] 国标起草单位追加成功！本次新增: {len(batch_data)} 条记录。")
        else:
            print("[WARN] Excel 中未发现可录入的起草单位数据。")

    except Exception as e:
        conn.rollback()
        print(f"[ERROR] 迁移失败: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    run_gb_extend_migration()
