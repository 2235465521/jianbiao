import _path
from db_config import DB_CONFIG  # noqa: F401

import os
import glob
import pandas as pd
import pymysql

# 数据库配置 (从 .env 中读取到的值)


def get_excel_path():
    files = glob.glob(r'E:\Downloads\ics\*.xlsx')
    if not files:
        raise FileNotFoundError("未找到 Excel 文件")
    # 找到包含 "ICS" 和 "CCS" 的文件
    for f in files:
        if "ICS" in f.upper() and "CCS" in f.upper():
            return f
    return files[0]

def import_ics(conn, excel_path):
    print("正在导入 ICS 数据...")
    # 读取第1个工作表
    df = pd.read_excel(excel_path, sheet_name=0)
    
    count = 0
    with conn.cursor() as cursor:
        for _, row in df.iterrows():
            try:
                if pd.isna(row.iloc[1]): continue # 跳过空行
                
                code = str(row.iloc[1]).strip()
                code_u = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else code
                level = int(row.iloc[3])
                name = str(row.iloc[4]).strip()
                
                # 计算 parent_code
                parent_code = None
                if level > 1 and '.' in code:
                    parent_code = code.rsplit('.', 1)[0]
                
                sql = """
                INSERT INTO std_ics_dict 
                (ics_code, ics_code_u, parent_code, level, category_name, name_level_1, name_level_2, name_level_3, extend_category, notes, extend_notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                ics_code_u=VALUES(ics_code_u), parent_code=VALUES(parent_code), level=VALUES(level), 
                category_name=VALUES(category_name), name_level_1=VALUES(name_level_1), 
                name_level_2=VALUES(name_level_2), name_level_3=VALUES(name_level_3),
                extend_category=VALUES(extend_category), notes=VALUES(notes), extend_notes=VALUES(extend_notes)
                """
                cursor.execute(sql, (
                    code, code_u, parent_code, level, name,
                    str(row.iloc[5]) if pd.notna(row.iloc[5]) else None,
                    str(row.iloc[6]) if pd.notna(row.iloc[6]) else None,
                    str(row.iloc[7]) if pd.notna(row.iloc[7]) else None,
                    str(row.iloc[8]) if pd.notna(row.iloc[8]) else None,
                    str(row.iloc[9]) if pd.notna(row.iloc[9]) else None,
                    str(row.iloc[10]) if pd.notna(row.iloc[10]) else None
                ))
                count += 1
            except Exception as e:
                print(f"跳过 ICS 行 {row.iloc[0] if pd.notna(row.iloc[0]) else '?'}: {e}")
                
    conn.commit()
    print(f"ICS 导入完成，共处理 {count} 条记录。")

def import_ccs(conn, excel_path):
    print("正在导入 CCS 数据...")
    # 读取第2个工作表
    df = pd.read_excel(excel_path, sheet_name=1)
    
    count = 0
    with conn.cursor() as cursor:
        for _, row in df.iterrows():
            try:
                if pd.isna(row.iloc[1]): continue # 跳过空行
                
                code = str(row.iloc[1]).strip()
                name = str(row.iloc[2]).strip()
                parent_code = str(row.iloc[3]).strip() if pd.notna(row.iloc[3]) else None
                notes = str(row.iloc[4]).strip() if pd.notna(row.iloc[4]) else None
                level = int(row.iloc[5])
                sort_code = str(row.iloc[6]).strip() if pd.notna(row.iloc[6]) else None
                
                sql = """
                INSERT INTO std_ccs_dict 
                (ccs_code, category_name, parent_code, notes, level, sort_code, name_level_1, name_level_2, name_level_3)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                category_name=VALUES(category_name), parent_code=VALUES(parent_code), notes=VALUES(notes),
                level=VALUES(level), sort_code=VALUES(sort_code), name_level_1=VALUES(name_level_1),
                name_level_2=VALUES(name_level_2), name_level_3=VALUES(name_level_3)
                """
                cursor.execute(sql, (
                    code, name, parent_code, notes, level, sort_code,
                    str(row.iloc[7]) if pd.notna(row.iloc[7]) else None,
                    str(row.iloc[8]) if pd.notna(row.iloc[8]) else None,
                    str(row.iloc[9]) if pd.notna(row.iloc[9]) else None
                ))
                count += 1
            except Exception as e:
                print(f"跳过 CCS 行 {row.iloc[0] if pd.notna(row.iloc[0]) else '?'}: {e}")
                
    conn.commit()
    print(f"CCS 导入完成，共处理 {count} 条记录。")

if __name__ == "__main__":
    try:
        path = get_excel_path()
        print(f"找到文件: {path}")
        connection = pymysql.connect(**DB_CONFIG)
        try:
            import_ics(connection, path)
            import_ccs(connection, path)
        finally:
            connection.close()
    except Exception as e:
        print(f"错误: {e}")
