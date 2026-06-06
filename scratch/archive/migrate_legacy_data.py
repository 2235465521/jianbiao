import pandas as pd
import re
import pymysql
import sys
import os

# Ensure config can be loaded
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

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

def parse_std_type(bz_id):
    """
    智能解析分类及分类编码
    """
    bz_id = str(bz_id).strip()
    match = re.match(r'^([A-Za-z/]+)', bz_id)
    std_type = match.group(1).upper() if match else 'UNKNOWN'
    
    std_type_no = '99'
    if std_type.startswith('GB') or std_type == 'GJB':
        std_type_no = '00'
    elif std_type.startswith('DB'):
        std_type_no = '02'
    elif std_type.startswith('T/'):
        std_type_no = '03'
    elif std_type.startswith('Q/'):
        std_type_no = '06'
    elif std_type in ('ISO', 'IEC', 'EN', 'DIN', 'ANSI'):
        std_type_no = '99'
    elif std_type != 'UNKNOWN':
        std_type_no = '01'
        
    return std_type, std_type_no

def clean_date(val):
    if pd.isna(val) or str(val).strip() in ('nan', '', 'NaT', 'None', '未获取到'):
        return None
    val_str = str(val).strip().split(' ')[0]
    if re.match(r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}$', val_str):
        return val_str.replace('/', '-')
    return None

def run_migration():
    file_path = r"E:\Downloads\数据库数据\基础表最最新.xlsx"
    print(f"[START] 读取 Excel 数据... : {file_path}")
    
    df = pd.read_excel(file_path, dtype=str)
    print(f"[SUCCESS] Excel 读取完成，共计 {len(df)} 行数据。")

    # 连接数据库
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 清理旧数据 (确保开始前是空的)
        print("[PROCESS] 清空旧表数据以备重新录入...")
        tables = ['std_replace', 'std_ex', 'std_detail', 'std_indu_detail', 'std_base']
        for t in tables:
            cursor.execute(f"DELETE FROM {t}")
        conn.commit()

        print("[PROCESS] 1/2 正在灌入 `std_base` 核心层 (合并字段模式)...")
        
        # 字段映射字典 (Excel -> Table)
        # 注意: 如果您的 Excel 里还有英文名，请自行根据表头修改此处映射
        base_insert_sql = """
            INSERT INTO std_base 
            (std_id, std_type, std_type_no, std_chinesename, release_date, implement_date, ex_state) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE std_chinesename=VALUES(std_chinesename)
        """
        
        state_map = {"废止": 0, "现行": 1, "即将实施": 2}
        
        base_batch = []
        for _, row in df.iterrows():
            std_id = str(row.get('bz_id', '')).strip()
            if not std_id or std_id == 'nan': continue
            
            s_type, s_no = parse_std_type(std_id)
            c_name = str(row.get('bz_name', '')).strip()
            r_date = clean_date(row.get('bz_release_date'))
            i_date = clean_date(row.get('implement_time', row.get('implement_tine')))
            e_state = state_map.get(str(row.get('ex_state')).strip(), 1)
            
            base_batch.append((std_id, s_type, s_no, c_name, r_date, i_date, e_state))
            
        cursor.executemany(base_insert_sql, base_batch)
        conn.commit()
        print(f"[SUCCESS] std_base 核心数据录入成功，共 {len(base_batch)} 条。")

        # 重新索引 ID
        print("[PROCESS] 同步关联映射表...")
        cursor.execute("SELECT id, std_id FROM std_base")
        id_mapping = {r['std_id']: r['id'] for r in cursor.fetchall()}

        print("[PROCESS] 2/2 正在灌入 `std_indu_detail` 行业分类层 (新字段模式)...")
        
        indu_batch = []
        # 注意：这里会根据您图中提到的中文字段名进行提取，如果 Excel 中对应的表头不同请微调
        for _, row in df.iterrows():
            std_id = str(row.get('bz_id', '')).strip()
            if std_id not in id_mapping: continue
            
            base_id = id_mapping[std_id]
            
            # 提取字段映射
            ccs = str(row.get('ccs', '')).strip()
            ics = str(row.get('ics', '')).strip()
            drafter = str(row.get('drafter', '')).strip()
            report_unit = str(row.get('report_unit', '')).strip()
            sub_report_unit = str(row.get('sub_report_unit', '')).strip()
            
            # --- 以下是您新添加的细化字段 (根据图中中文字段名匹配) ---
            industry_type = str(row.get('行业分类', '')).strip()
            std_indu_type = str(row.get('标准分类', row.get('标准类别', ''))).strip()
            record_no = str(row.get('备案号', '')).strip()
            record_date = clean_date(row.get('备案日期'))
            rev_type = str(row.get('制修订', '')).strip()
            tech_committee = str(row.get('技术归口', '')).strip()
            approve_dept = str(row.get('批准发布部门', '')).strip()

            # 清理 nan
            targets = [ccs, ics, drafter, report_unit, sub_report_unit, 
                      industry_type, std_indu_type, record_no, rev_type, 
                      tech_committee, approve_dept]
            cleaned = []
            for t in targets:
                cleaned.append(None if t == 'nan' or not t else t)

            indu_batch.append((base_id, *cleaned, record_date))
            
        indu_insert_sql = """
            INSERT INTO std_indu_detail 
            (base_id, ccs, ics, drafter, report_unit, sub_report_unit, 
             industry_type, std_indu_type, record_no, rev_type, 
             tech_committee, approve_dept, record_date) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.executemany(indu_insert_sql, indu_batch)
        conn.commit()
        print(f"[FINISHED] 全部重构数据已成功归位！")
        print(f"提示：您现在可以执行 `SELECT * FROM view_std_full LIMIT 10;` 来查看最新合并的大宽表了。")

    except Exception as e:
        conn.rollback()
        print(f"[ERROR] 迁移失败: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    run_migration()
