import _path
from db_config import DB_CONFIG  # noqa: F401

import pymysql
import pandas as pd
import time
import os



def import_pedigree_data():
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    try:
        print("1. 正在构建 std_base 表的 ID 映射字典 (std_id -> id)...")
        # 由于可能有一对多，我们取最新的或者任一对应的 base_id。按照业务逻辑，std_id 应该是唯一的
        cursor.execute("SELECT std_id, id FROM std_base")
        base_map = {row[0]: row[1] for row in cursor.fetchall()}
        print(f"成功加载 {len(base_map)} 条标准基础数据映射。")

        # 处理《谱系表.xlsx》 -> std_pedigree
        file1 = 'E:/Downloads/谱系链/谱系表.xlsx'
        print(f"\n2. 正在读取 {file1} ...")
        df_ped = pd.read_excel(file1)
        # 字段: 'bz_id', 'new_bz_id', 'ped_id'
        
        insert_pedigree_sql = "INSERT INTO std_pedigree (base_id, std_id_latest, ped_id) VALUES (%s, %s, %s)"
        pedigree_batch = []
        skip_count = 0
        
        for index, row in df_ped.iterrows():
            bz_id = str(row['bz_id']).strip()
            new_bz_id = str(row['new_bz_id']).strip() if pd.notna(row['new_bz_id']) else None
            ped_id = str(row['ped_id']).strip() if pd.notna(row['ped_id']) else None
            
            base_id = base_map.get(bz_id)
            if base_id is None:
                skip_count += 1
                continue
                
            pedigree_batch.append((base_id, new_bz_id, ped_id))
            
        print(f"成功解析 {len(pedigree_batch)} 条谱系记录 (由于底表找不到 bz_id 而跳过了 {skip_count} 条数据)。")
        print("开始分批插入 std_pedigree 表...")
        
        batch_size = 5000
        for i in range(0, len(pedigree_batch), batch_size):
            cursor.executemany(insert_pedigree_sql, pedigree_batch[i:i+batch_size])
        print("std_pedigree 插入完成！")
        
        # 处理《谱系链表.xlsx》 -> std_ped_chain
        file2 = 'E:/Downloads/谱系链/谱系链表.xlsx'
        print(f"\n3. 正在读取 {file2} ...")
        df_chain = pd.read_excel(file2)
        # 字段: 'id', 'ped_id', 'all_chain'
        
        insert_chain_sql = "INSERT INTO std_ped_chain (ped_id, ped_chain) VALUES (%s, %s)"
        chain_batch = []
        
        for index, row in df_chain.iterrows():
            ped_id = str(row['ped_id']).strip() if pd.notna(row['ped_id']) else None
            all_chain = str(row['all_chain']).strip() if pd.notna(row['all_chain']) else None
            
            if ped_id and all_chain:
                chain_batch.append((ped_id, all_chain))
                
        print(f"成功解析 {len(chain_batch)} 条谱系链记录。")
        print("开始分批插入 std_ped_chain 表...")
        
        for i in range(0, len(chain_batch), batch_size):
            cursor.executemany(insert_chain_sql, chain_batch[i:i+batch_size])
        print("std_ped_chain 插入完成！")
        
        conn.commit()
        print("\n所有谱系数据导入圆满结束！")
        
    except Exception as e:
        conn.rollback()
        print(f"执行发生异常: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    start_time = time.time()
    import_pedigree_data()
    print(f"总耗时: {time.time() - start_time:.2f} 秒")
