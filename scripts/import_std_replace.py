import _path  # noqa: F401

import pandas as pd
import pymysql
import time

# --- 配置区 ---
DB_CONFIG = {
    'host': '127.0.0.1',
    'port': 3306,
    'user': 'root',
    'password': 'lsj223546',
    'database': 'mydate',
    'charset': 'utf8mb4'
}

EXCEL_PATH = 'E:/Downloads/替代表/替代表最新.xlsx'

# 类型映射表 (0:部分替代, 1:全部替代, 2:部分代完)
# 自动兼容 "替代" 和 "代替" 两种写法
TYPE_MAP = {
    '部分替代': 0,
    '部分代替': 0,
    '全部替代': 1,
    '全部代替': 1,
    '部分代完': 2
}

def import_replace_data():
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    try:
        # 0. 清空表 (重置 ID)
        print("0. 正在清空 std_replace 表并重置自增 ID...")
        cursor.execute("TRUNCATE TABLE std_replace")
        conn.commit()

        # 1. 建立 std_id -> id 的映射 (包含全量标准)
        print("1. 正在加载全量标准 ID 映射关系 (std_base)...")
        cursor.execute("SELECT std_id, id FROM std_base")
        id_map = {row[0]: row[1] for row in cursor.fetchall()}
        print(f"   成功加载 {len(id_map)} 条基础映射。")

        # 2. 读取 Excel
        print(f"2. 正在读取 Excel 文件: {EXCEL_PATH} ...")
        df = pd.read_excel(EXCEL_PATH)
        print(f"   读取完成，共 {len(df)} 行原始数据。")

        # 3. 准备更新数据
        print("3. 正在执行严格过滤与类型转换...")
        insert_data = []
        skip_first_gen = 0
        skip_invalid_type = 0
        skip_missing_id = 0
        
        for _, row in df.iterrows():
            bz_id_str = str(row['bz_id']).strip() if pd.notna(row['bz_id']) else None
            replace_bz_id_str = str(row['replace_bz_id']).strip() if pd.notna(row['replace_bz_id']) else None
            type_str = str(row['replace_type']).strip() if pd.notna(row['replace_type']) else None
            
            # 规则 1: replace_bz_id 为空说明是第一代，跳过
            if not replace_bz_id_str or replace_bz_id_str.lower() == 'nan':
                skip_first_gen += 1
                continue
                
            # 规则 2: 类型为空或特殊文本，跳过
            type_val = TYPE_MAP.get(type_str)
            if type_val is None:
                skip_invalid_type += 1
                continue
            
            # 规则 3: 必须在基础表中存在
            base_id = id_map.get(bz_id_str)
            replace_id = id_map.get(replace_bz_id_str)
            
            if base_id and replace_id:
                insert_data.append((base_id, replace_id, type_val))
            else:
                skip_missing_id += 1

        print(f"   过滤结果统计:")
        print(f"   - 成功匹配: {len(insert_data)} 条")
        print(f"   - 因第一代/空前身跳过: {skip_first_gen} 条")
        print(f"   - 因类型不合法跳过: {skip_invalid_type} 条")
        print(f"   - 因标准号在库中不存在跳过: {skip_missing_id} 条")

        # 4. 批量插入
        if insert_data:
            print(f"4. 正在批量写入 std_replace 表...")
            insert_sql = "INSERT INTO std_replace (base_id, replace_id, replace_type) VALUES (%s, %s, %s)"
            
            batch_size = 5000
            for i in range(0, len(insert_data), batch_size):
                cursor.executemany(insert_sql, insert_data[i:i+batch_size])
            
            conn.commit()
            print("Import successful! ID started from 1.")
        else:
            print("Warning: No records matched after filtering.")

    except Exception as e:
        conn.rollback()
        print(f"Error: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    start_time = time.time()
    import_replace_data()
    print(f"总计耗时: {time.time() - start_time:.2f} 秒")
