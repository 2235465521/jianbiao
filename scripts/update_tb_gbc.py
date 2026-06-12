import _path
from db_config import DB_CONFIG  # noqa: F401

import pandas as pd
import pymysql
import time

# --- 配置区 ---


EXCEL_PATH = 'E:/Downloads/团标/团体标准详情信息.xlsx'

def update_gbc():
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    try:
        # 1. 建立 std_id -> base_id 的映射
        print("1. 正在加载标准 ID 映射关系...")
        cursor.execute("SELECT std_id, id FROM std_base WHERE std_type_no = '03'")
        id_map = {row[0]: row[1] for row in cursor.fetchall()}
        print(f"   成功加载 {len(id_map)} 条团标映射。")

        # 2. 读取 Excel
        print(f"2. 正在读取 Excel 文件 (约 50MB): {EXCEL_PATH} ...")
        # 索引 2 为标准号, 索引 7 为国民经济分类 (GBC)
        df = pd.read_excel(EXCEL_PATH, usecols=[2, 7])
        print(f"   读取完成，共 {len(df)} 行数据。")

        # 3. 准备更新数据
        print("3. 正在匹配数据...")
        update_data = []
        not_found_count = 0
        
        for _, row in df.iterrows():
            std_id = str(row.iloc[0]).strip()
            gbc_val = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else None
            
            if gbc_val and gbc_val.lower() != 'nan':
                base_id = id_map.get(std_id)
                if base_id:
                    update_data.append((gbc_val, base_id))
                else:
                    not_found_count += 1

        print(f"   匹配成功: {len(update_data)} 条")
        print(f"   未匹配到标准号: {not_found_count} 条")

        # 4. 批量更新
        if update_data:
            print(f"4. 正在批量更新 std_tb_detail 表的 gbc 字段...")
            update_sql = "UPDATE std_tb_detail SET gbc = %s WHERE base_id = %s"
            
            batch_size = 5000
            for i in range(0, len(update_data), batch_size):
                cursor.executemany(update_sql, update_data[i:i+batch_size])
            
            conn.commit()
            print("🎉 更新圆满完成！")
        else:
            print("⚠️ 没有需要更新的数据。")

    except Exception as e:
        conn.rollback()
        print(f"❌ 发生错误: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    start_time = time.time()
    update_gbc()
    print(f"总计耗时: {time.time() - start_time:.2f} 秒")
