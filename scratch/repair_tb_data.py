import pandas as pd
import pymysql
import sys
import re

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

def n(v): 
    if pd.isna(v) or not str(v).strip() or str(v).strip().lower() == 'nan':
        return None
    return str(v).strip()

def repair_tb():
    file_path = r"E:\Downloads\团标\团体标准详情信息.xlsx"
    print(f"[1/4] 正在读取 Excel: {file_path}")
    df = pd.read_excel(file_path, dtype=str)
    
    cols = df.columns.tolist()
    def find_col(keywords):
        for c in cols:
            if any(kw in str(c) for kw in keywords):
                return c
        return None

    c_sid = find_col(['标准编号'])
    c_name = find_col(['中文标题', '中文名称', '中文标准名称'])
    c_ename = find_col(['英文标题', '英文名称'])
    c_ics = find_col(['国际标准分类号'])
    c_ccs = find_col(['中国标准分类号'])
    c_gbc = find_col(['国民经济分类号'])
    c_drafter = find_col(['起草人'])
    c_scope = find_col(['范围'])
    c_main_tech = find_col(['主要技术内容'])
    c_patent = find_col(['专利信息', '是否包含专利信息'])
    c_text = find_col(['标准文本'])
    c_asso = find_col(['名称'])
    c_regi = find_col(['登记证号'])
    c_issu = find_col(['发证机关'])
    c_buss = find_col(['业务范围'])
    c_charge = find_col(['法定代表人', '负责人'])
    c_uname = find_col(['单位名称'])
    c_addr = find_col(['通讯地址'])

    print(f"匹配到的列名: 中文->{c_name}, 英文->{c_ename}")

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 2. 补录 std_base 的名字 (按照 std_id 匹配)
        print("[2/4] 正在补录 std_base 的中文/英文名称...")
        update_name_batch = []
        for i, row in df.iterrows():
            sid = n(row.get(c_sid))
            cname = n(row.get(c_name))
            ename = n(row.get(c_ename))
            if sid:
                update_name_batch.append((cname, ename, sid))
        
        # 批量更新 std_base
        cursor.executemany("""
            UPDATE std_base 
            SET std_chinesename = %s, std_englishname = %s 
            WHERE std_id = %s AND std_type_no = '03'
        """, update_name_batch)
        conn.commit()
        print(f"完成 std_base 名字更新。")

        # 3. 重置 std_tb_detail (清空并重新录入，重置 ID)
        print("[3/4] 正在清空 std_tb_detail 并重置 ID...")
        cursor.execute("TRUNCATE TABLE std_tb_detail")
        conn.commit()

        # 获取最新的 ID 映射
        cursor.execute("SELECT id, std_id FROM std_base WHERE std_type_no = '03'")
        id_mapping = {r['std_id']: r['id'] for r in cursor.fetchall()}

        # 4. 重新录入详情
        print("[4/4] 正在重新录入详情数据到 std_tb_detail (ID 将从 1 开始)...")
        detail_batch = []
        seen_base_ids = set()
        for i, row in df.iterrows():
            sid = n(row.get(c_sid))
            if sid not in id_mapping: continue
            base_id = id_mapping[sid]
            
            # 过滤重复的 base_id
            if base_id in seen_base_ids:
                continue
            seen_base_ids.add(base_id)
            
            ccs = n(row.get(c_ccs))
            ics = n(row.get(c_ics))
            gbc = n(row.get(c_gbc))
            drafter = n(row.get(c_drafter))
            scope = n(row.get(c_scope))
            main_tech_cont = n(row.get(c_main_tech))
            
            patent_val = n(row.get(c_patent))
            is_patent = 1 if patent_val and '是' in patent_val else 0
            
            text_val = n(row.get(c_text))
            std_text = 1 if text_val and '公开' in text_val and '不' not in text_val else 0
            
            tb_asso = n(row.get(c_asso))
            regi_no = n(row.get(c_regi))
            issu_auth = n(row.get(c_issu))
            buss_scope = n(row.get(c_buss))
            charge_person = n(row.get(c_charge))
            unit_name = n(row.get(c_uname))
            address = n(row.get(c_addr))

            detail_batch.append((
                base_id, ccs, ics, gbc, drafter, scope, main_tech_cont, is_patent, std_text,
                tb_asso, regi_no, issu_auth, buss_scope, charge_person, unit_name, address
            ))

        cursor.executemany("""
            INSERT INTO std_tb_detail 
            (base_id, ccs, ics, gbc, drafter, scope, main_tech_cont, is_patent, std_text, 
             tb_asso, regi_no, Issu_auth, buss_scope, charge_person, unit_name, address)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, detail_batch)
        
        conn.commit()
        print(f"修复完成！详情录入共 {len(detail_batch)} 条。")

    except Exception as e:
        conn.rollback()
        print(f"[ERROR] {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    repair_tb()
