import pandas as pd
import re
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

def clean_date(val):
    if pd.isna(val) or str(val).strip() in ('nan', '', 'NaT', 'None', '未获取到'):
        return None
    val_str = str(val).strip().split(' ')[0]
    # Handle YYYY/M/D or YYYY-M-D
    match = re.match(r'^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$', val_str)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    return None

def n(v): 
    if pd.isna(v) or not str(v).strip() or str(v).strip().lower() == 'nan':
        return None
    return str(v).strip()

def run_tb_migration():
    file_path = r"E:\Downloads\团标\团体标准详情信息.xlsx"
    print(f"[START] 正在读取团标数据文件... : {file_path}")
    
    # Read Excel
    df = pd.read_excel(file_path, dtype=str)
    print(f"[SUCCESS] Excel 读取完成，共计 {len(df)} 行数据。")
    
    # Identify columns by keywords to avoid encoding issues or slight name variations
    cols = df.columns.tolist()
    def find_col(keywords):
        for c in cols:
            if any(kw in str(c) for kw in keywords):
                return c
        return None

    c_sid = find_col(['标准编号'])
    c_name = find_col(['中文名称', '中文标准名称'])
    c_ename = find_col(['英文名称'])
    c_ics = find_col(['国际标准分类号'])
    c_ccs = find_col(['中国标准分类号'])
    c_gbc = find_col(['国民经济分类号'])
    c_rdate = find_col(['发布日期'])
    c_idate = find_col(['实施日期'])
    c_drafter = find_col(['起草人'])
    c_unit = find_col(['起草单位'])
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

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 1. std_base
        print("[PROCESS] 1/3 录入 std_base...")
        base_batch = []
        for _, row in df.iterrows():
            std_id = n(row.get(c_sid))
            if not std_id: continue
            
            std_chinesename = n(row.get(c_name))
            std_englishname = n(row.get(c_ename))
            release_date = clean_date(row.get(c_rdate))
            implement_date = clean_date(row.get(c_idate))
            
            # std_type extraction (e.g. T/CECS -> T/CECS)
            match = re.match(r'^([A-Z/]+)', std_id)
            std_type = match.group(1) if match else 'T'
            
            base_batch.append((std_id, std_type, '03', std_chinesename, std_englishname, release_date, implement_date, 1))

        cursor.executemany("""
            INSERT IGNORE INTO std_base (std_id, std_type, std_type_no, std_chinesename, std_englishname, release_date, implement_date, ex_state)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, base_batch)
        conn.commit()
        
        # 2. std_tb_detail & std_extend_h
        print("[PROCESS] 2/3 获取 ID 映射...")
        cursor.execute("SELECT id, std_id FROM std_base WHERE std_type_no = '03'")
        id_mapping = {r['std_id']: r['id'] for r in cursor.fetchall()}
        
        detail_batch = []
        extend_batch = []
        for _, row in df.iterrows():
            sid = n(row.get(c_sid))
            if sid not in id_mapping: continue
            base_id = id_mapping[sid]
            
            ccs = n(row.get(c_ccs))
            ics = n(row.get(c_ics))
            gbc = n(row.get(c_gbc))
            drafter = n(row.get(c_drafter))
            scope = n(row.get(c_scope))
            main_tech = n(row.get(c_main_tech))
            
            # patent mapping
            patent_val = n(row.get(c_patent))
            is_patent = 1 if patent_val and '是' in patent_val else 0
            
            # text availability mapping
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
                base_id, ccs, ics, gbc, drafter, scope, main_tech, is_patent, std_text,
                tb_asso, regi_no, issu_auth, buss_scope, charge_person, unit_name, address
            ))
            
            # extend_h
            draft_units = n(row.get(c_unit))
            if draft_units:
                extend_batch.append((base_id, '团标', draft_units))

        print("[PROCESS] 3/3 写入详情表与追加起草单位...")
        cursor.executemany("""
            INSERT INTO std_tb_detail 
            (base_id, ccs, ics, gbc, drafter, scope, main_tech_cont, is_patent, std_text, 
             tb_asso, regi_no, Issu_auth, buss_scope, charge_person, unit_name, address)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE base_id=base_id
        """, detail_batch)
        
        if extend_batch:
            cursor.executemany("INSERT INTO std_extend_h (base_id, std_type, draft_unit) VALUES (%s, %s, %s)", extend_batch)
            
        conn.commit()
        print(f"[FINISHED] 团标数据录入完成！共录入详情 {len(detail_batch)} 条，追加起草单位 {len(extend_batch)} 条记录。")

    except Exception as e:
        conn.rollback()
        print(f"[ERROR] {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    run_tb_migration()
