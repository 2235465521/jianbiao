import _path
from db_config import DB_CONFIG  # noqa: F401

import pandas as pd
import pymysql
import time

# --- 配置区 ---


FILES = {
    'main': 'E:/Downloads/替代表/替代表最新.xlsx',
    'industry': 'E:/Downloads/行标/行标提取结果起草单位.xlsx',
    'local': 'E:/Downloads/地标/地标提取结果起草单位.xlsx'
}

# 类型映射表 (0:部分替代, 1:全部替代, 2:部分代完)
TYPE_MAP = {
    '部分替代': 0, '部分代替': 0,
    '全部替代': 1, '全部代替': 1,
    '部分代完': 2
}

def clean_str(val):
    if pd.isna(val) or str(val).lower() == 'nan':
        return None
    return str(val).strip()

def import_all_replace_data():
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    try:
        # 0. 清空表 (重置 ID)
        print("0. 正在清空 std_replace 表并重置自增 ID...")
        cursor.execute("TRUNCATE TABLE std_replace")
        conn.commit()

        # 1. 加载全量映射
        print("1. 正在加载全量标准 ID 映射关系...")
        cursor.execute("SELECT std_id, id FROM std_base")
        id_map = {row[0]: row[1] for row in cursor.fetchall()}
        print(f"   成功加载 {len(id_map)} 条基础 ID。")

        # 用于去重的集合: (新标准号, 旧标准号)
        unique_pairs = set()
        final_data = []

        # 2. 处理《替代表最新.xlsx》
        print(f"2. 正在处理《替代表最新.xlsx》...")
        df_main = pd.read_excel(FILES['main'])
        for _, row in df_main.iterrows():
            bz_id = clean_str(row.iloc[0])
            replace_bz_id = clean_str(row.iloc[1])
            type_str = clean_str(row.iloc[2])
            
            if replace_bz_id and (bz_id, replace_bz_id) not in unique_pairs:
                unique_pairs.add((bz_id, replace_bz_id))
                base_id = id_map.get(bz_id)
                replace_id = id_map.get(replace_bz_id)
                type_val = TYPE_MAP.get(type_str, 1) # 默认 1
                final_data.append((base_id, replace_id, replace_bz_id, type_val))

        # 3. 处理《行标提取结果起草单位.xlsx》
        print(f"3. 正在处理《行标提取结果起草单位.xlsx》...")
        # B(1) 是标准号, R(17) 是替代标准
        df_ind = pd.read_excel(FILES['industry'], usecols=[1, 17])
        for _, row in df_ind.iterrows():
            bz_id = clean_str(row.iloc[0])
            replace_bz_id = clean_str(row.iloc[1])
            
            if replace_bz_id and (bz_id, replace_bz_id) not in unique_pairs:
                unique_pairs.add((bz_id, replace_bz_id))
                base_id = id_map.get(bz_id)
                replace_id = id_map.get(replace_bz_id)
                final_data.append((base_id, replace_id, replace_bz_id, 1)) # 默认 1

        # 4. 处理《地标提取结果起草单位.xlsx》
        print(f"4. 正在处理《地标提取结果起草单位.xlsx》...")
        # A(0) 是标准号, O(14) 是代替标准
        df_loc = pd.read_excel(FILES['local'], usecols=[0, 14])
        for _, row in df_loc.iterrows():
            bz_id = clean_str(row.iloc[0])
            replace_bz_id = clean_str(row.iloc[1])
            
            if replace_bz_id and (bz_id, replace_bz_id) not in unique_pairs:
                unique_pairs.add((bz_id, replace_bz_id))
                base_id = id_map.get(bz_id)
                replace_id = id_map.get(replace_bz_id)
                final_data.append((base_id, replace_id, replace_bz_id, 1)) # 默认 1

        # 5. 批量写入
        print(f"5. 准备写入数据库，共 {len(final_data)} 条去重后的关系...")
        if final_data:
            insert_sql = "INSERT INTO std_replace (base_id, replace_id, replace_std_name, replace_type) VALUES (%s, %s, %s, %s)"
            batch_size = 5000
            for i in range(0, len(final_data), batch_size):
                cursor.executemany(insert_sql, final_data[i:i+batch_size])
            conn.commit()
            print("Import successful! All three sources integrated. ID started from 1.")
        else:
            print("No valid data found.")

    except Exception as e:
        conn.rollback()
        print(f"Error: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    start_time = time.time()
    import_all_replace_data()
    print(f"Total time: {time.time() - start_time:.2f} seconds")
