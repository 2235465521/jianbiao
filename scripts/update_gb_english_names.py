import _path  # noqa: F401

import os
import pandas as pd
import pymysql

# 数据库配置
db_config = {
    'host': '127.0.0.1',
    'user': 'root',
    'password': 'lsj223546',
    'database': 'mydate',
    'charset': 'utf8mb4'
}

def update_gb_names():
    path = r'E:\Downloads\国标\77239国标英文名称.xlsx'
    if not os.path.exists(path):
        print(f"错误: 找不到文件 {path}")
        return

    print("正在读取 Excel 文件，请稍候...")
    df = pd.read_excel(path)
    
    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()
    
    try:
        total_rows = len(df)
        print(f"Excel 中共有 {total_rows} 条记录。开始更新数据库...")
        
        # 批量处理以提高效率
        batch_size = 2000
        total_updated = 0
        
        for i in range(0, total_rows, batch_size):
            batch = df.iloc[i:i + batch_size]
            update_data = []
            
            for _, row in batch.iterrows():
                # Column 0: 标准号, Column 2: 英文名称
                std_id = str(row.iloc[0]).strip()
                eng_name = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else None
                
                if std_id and eng_name:
                    update_data.append((eng_name, std_id))
            
            if update_data:
                sql = "UPDATE std_base SET std_englishname = %s WHERE std_id = %s"
                affected = cursor.executemany(sql, update_data)
                conn.commit()
                total_updated += affected
            
            print(f"已处理 {min(i + batch_size, total_rows)} / {total_rows}...")
            
        print(f"\n更新完成！")
        print(f"- Excel 总记录数: {total_rows}")
        print(f"- 数据库实际更新行数: {total_updated}")
        
    except Exception as e:
        conn.rollback()
        print(f"发生错误: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    update_gb_names()
