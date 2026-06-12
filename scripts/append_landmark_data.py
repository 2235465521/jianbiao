import _path
from db_config import DB_CONFIG  # noqa: F401

import pandas as pd
import pymysql
import os
import re
from datetime import datetime

# --- 配置区 ---


def clean_unit_name(name):
    if not name or pd.isna(name): return None
    name = str(name).strip()
    name = re.sub(r'\(.*?\)|（.*?）', '', name)
    if len(name) <= 3: return None
    return name

def parse_date(val):
    if pd.isna(val) or str(val).strip() == '' or str(val).lower() == 'nan': return None
    try:
        return pd.to_datetime(val).date()
    except:
        return None

def append_landmark_data():
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    try:
        # 1. 寻找 Excel 文件 (通过大小精确锁定 4.3MB 的那个)
        path = 'E:/Downloads/地标'
        target_file = None
        for f in os.listdir(path):
            full_path = os.path.join(path, f)
            # 锁定 4,349,740 字节左右的文件
            if os.path.isfile(full_path) and 4300000 < os.path.getsize(full_path) < 4400000:
                target_file = full_path
                break
        
        if not target_file:
            print("Error: Could not find the landmark Excel file.")
            return
        print(f"Reading file: {target_file}")
        
        # 2. 读取全量数据
        df = pd.read_excel(target_file, header=0)
        print(f"Total rows read from Excel: {len(df)}")

        # 3. 准备数据容器
        base_data = []
        valid_rows = []
        
        for _, row in df.iterrows():
            std_id = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
            # 简单判断是否是合规的标准号 (地标通常以 DB 或 DD 开头)
            if not (std_id.startswith('DB') or std_id.startswith('DD')):
                continue
            
            valid_rows.append(row)
            base_data.append((
                std_id, 'DB', '02',
                str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else None,
                parse_date(row.iloc[13]), # 发布日期 (N)
                parse_date(row.iloc[14]), # 实施日期 (O)
                parse_date(row.iloc[15]), # 废止日期 (P)
                str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else None
            ))

        print(f"Valid landmark records found: {len(valid_rows)}")

        # 4. 批量插入 std_base (使用 INSERT IGNORE)
        print("Batch inserting into std_base...")
        insert_base_sql = """
            INSERT IGNORE INTO std_base (std_id, std_type, std_type_no, std_chinesename, release_date, implement_date, abolish_date, std_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        batch_size = 5000
        for i in range(0, len(base_data), batch_size):
            cursor.executemany(insert_base_sql, base_data[i:i+batch_size])
        conn.commit()

        # 5. 获取所有地标的 ID 映射
        print("Loading base_id mapping...")
        cursor.execute("SELECT std_id, id FROM std_base WHERE std_type_no = '02'")
        all_ids = {row[0]: row[1] for row in cursor.fetchall()}

        # 6. 准备辅助表数据
        detail_data = []
        extend_h_data = []
        replace_data = []
        relation_data = []
        unit_names_to_check = set()
        unique_rel_set = set()

        for row in valid_rows:
            std_id = str(row.iloc[0]).strip()
            base_id = all_ids.get(std_id)
            if not base_id: continue

            # Detail
            detail_data.append((
                base_id,
                str(row.iloc[5]).strip() if pd.notna(row.iloc[5]) else None,
                str(row.iloc[6]).strip() if pd.notna(row.iloc[6]) else None,
                str(row.iloc[3]).strip() if pd.notna(row.iloc[3]) else None,
                str(row.iloc[7]).strip() if pd.notna(row.iloc[7]) else None,
                parse_date(row.iloc[8]),
                str(row.iloc[9]).strip() if pd.notna(row.iloc[9]) else None,
                str(row.iloc[10]).strip() if pd.notna(row.iloc[10]) else None,
                str(row.iloc[11]).strip() if pd.notna(row.iloc[11]) else None,
                str(row.iloc[12]).strip() if pd.notna(row.iloc[12]) else None
            ))

            # Extend H & units
            draft_units_str = str(row.iloc[17]) if pd.notna(row.iloc[17]) else None
            if draft_units_str:
                extend_h_data.append((base_id, 'DB', draft_units_str))
                units = re.split(r'[，,；;、\s]', draft_units_str)
                for i, u in enumerate(units):
                    cleaned = clean_unit_name(u)
                    if cleaned:
                        unit_names_to_check.add(cleaned)
                        if (base_id, cleaned) not in unique_rel_set:
                            relation_data.append((base_id, cleaned, i+1))
                            unique_rel_set.add((base_id, cleaned))

            # Replace
            replace_std_str = str(row.iloc[16]).strip() if pd.notna(row.iloc[16]) else None
            if replace_std_str:
                rid = all_ids.get(replace_std_str)
                replace_data.append((base_id, rid, replace_std_str, 1))

        # 7. 处理 unit_dict
        print(f"Checking {len(unit_names_to_check)} unique units...")
        if unit_names_to_check:
            batch_units = [(u,) for u in unit_names_to_check]
            for i in range(0, len(batch_units), batch_size):
                cursor.executemany("INSERT IGNORE INTO unit_dict (unit_name) VALUES (%s)", batch_units[i:i+batch_size])
            conn.commit()
        
        cursor.execute("SELECT unit_name, unit_id FROM unit_dict")
        unit_map = {row[0]: row[1] for row in cursor.fetchall()}

        # 8. 批量写入详情和关系
        if detail_data:
            print("Inserting std_db_detail...")
            sql = "INSERT IGNORE INTO std_db_detail (base_id, ccs, ics, industry_type, record_no, record_date, rev_type, tech_committee, approve_dept, suggest_dept) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
            for i in range(0, len(detail_data), batch_size):
                cursor.executemany(sql, detail_data[i:i+batch_size])

        if extend_h_data:
            print("Inserting std_extend_h...")
            for i in range(0, len(extend_h_data), batch_size):
                cursor.executemany("INSERT IGNORE INTO std_extend_h (base_id, std_type, draft_unit) VALUES (%s, %s, %s)", extend_h_data[i:i+batch_size])

        if relation_data:
            print("Inserting std_unit_relation...")
            final_rel_data = []
            for bid, uname, rank in relation_data:
                uid = unit_map.get(uname)
                if uid:
                    final_rel_data.append((bid, uid, 2, rank))
            for i in range(0, len(final_rel_data), batch_size):
                cursor.executemany("INSERT IGNORE INTO std_unit_relation (base_id, unit_id, role_type, rank_order) VALUES (%s, %s, %s, %s)", final_rel_data[i:i+batch_size])

        if replace_data:
            print("Inserting std_replace...")
            for i in range(0, len(replace_data), batch_size):
                cursor.executemany("INSERT IGNORE INTO std_replace (base_id, replace_id, replace_std_name, replace_type) VALUES (%s, %s, %s, %s)", replace_data[i:i+batch_size])

        conn.commit()
        print("All data appended successfully.")

    except Exception as e:
        conn.rollback()
        print(f"Error occurred: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    start_t = datetime.now()
    append_landmark_data()
    print(f"Time taken: {datetime.now() - start_t}")
