import _path
from db_config import DB_CONFIG  # noqa: F401

import os
import pandas as pd
import pymysql

# 数据库配置


def format_tree_code(code, level):
    """根据层级对代码进行补零处理"""
    code_str = str(code).strip()
    # 如果是纯数字且长度不足，则根据层级补零
    if code_str.isdigit():
        if level == 2:
            return code_str.zfill(2)
        elif level == 3:
            return code_str.zfill(3)
        elif level == 4:
            return code_str.zfill(4)
    return code_str

def format_search_code(code):
    """搜索宽表代码均为末级(4位)"""
    code_str = str(code).strip()
    if code_str.isdigit() and len(code_str) < 4:
        return code_str.zfill(4)
    return code_str

def import_industry_data():
    path = r'E:\Downloads\4757\std_4757_from_pdf.xlsx'
    if not os.path.exists(path):
        print(f"错误: 找不到文件 {path}")
        return

    xl = pd.ExcelFile(path)
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    try:
        # 1. 导入 Tree 表 (std_4754_tree)
        print("正在从工作表 std_4757_tree 导入到数据库表 std_4754_tree...")
        df_tree = xl.parse('std_4757_tree')
        tree_count = 0
        for _, row in df_tree.iterrows():
            level = int(row['level'])
            code = format_tree_code(row['code'], level)
            parent = format_tree_code(row['parent_code'], level - 1) if pd.notna(row['parent_code']) else None
            
            sql = """
            INSERT INTO std_4754_tree (code, name, level, parent_code, description) 
            VALUES (%s, %s, %s, %s, %s) 
            ON DUPLICATE KEY UPDATE 
            name=VALUES(name), level=VALUES(level), parent_code=VALUES(parent_code), description=VALUES(description)
            """
            cursor.execute(sql, (
                code,
                str(row['name']).strip(),
                level,
                parent,
                str(row['description']).strip() if pd.notna(row['description']) else None
            ))
            tree_count += 1
        
        # 2. 导入 Search 表 (std_4757_search)
        print("正在从工作表 std_4757_search 导入到数据库表 std_4757_search...")
        df_search = xl.parse('std_4757_search')
        search_count = 0
        for _, row in df_search.iterrows():
            code = format_search_code(row['target_code'])
            
            sql = """
            INSERT INTO std_4757_search 
            (target_code, target_name, level_1_name, level_2_name, level_3_name, full_description) 
            VALUES (%s, %s, %s, %s, %s, %s) 
            ON DUPLICATE KEY UPDATE 
            target_name=VALUES(target_name), level_1_name=VALUES(level_1_name), 
            level_2_name=VALUES(level_2_name), level_3_name=VALUES(level_3_name), 
            full_description=VALUES(full_description)
            """
            cursor.execute(sql, (
                code,
                str(row['target_name']).strip(),
                str(row['level_1_name']).strip() if pd.notna(row['level_1_name']) else None,
                str(row['level_2_name']).strip() if pd.notna(row['level_2_name']) else None,
                str(row['level_3_name']).strip() if pd.notna(row['level_3_name']) else None,
                str(row['full_description']).strip() if pd.notna(row['full_description']) else None
            ))
            search_count += 1
            
        conn.commit()
        print(f"导入完成！\n- Tree表: {tree_count} 条\n- Search表: {search_count} 条")
        
    except Exception as e:
        conn.rollback()
        print(f"导入过程中发生错误: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    import_industry_data()
