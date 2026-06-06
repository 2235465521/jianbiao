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
    if re.match(r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}$', val_str):
        return val_str.replace('/', '-')
    return None

def n(v): 
    # Helper for NULLs
    if pd.isna(v) or not str(v).strip() or str(v).strip() == 'nan':
        return None
    return str(v).strip()

def run_db_migration():
    file_path = r"E:\Downloads\地标\地标提取结果起草单位.xlsx"
    print(f"[START] 正在读取地标数据文件... : {file_path}")
    
    # 全部以字符串读取以防丢失精度
    df = pd.read_excel(file_path, dtype=str)
    print(f"[SUCCESS] Excel 读取完成，共计 {len(df)} 行数据。")

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # ------- Phase 1: 录入 std_base -------
        print("[PROCESS] 1/3 正在录入地标数据至 std_base...")
        state_map = {"现行": 1, "废止": 0, "即将实施": 2}
        
        base_batch = []
        for _, row in df.iterrows():
            std_id = n(row.get('标准号'))
            if not std_id: continue
            
            # 提取标准类型 (如 DB11/T -> DB11/T)
            match = re.match(r'^([A-Za-z/]+)', std_id)
            std_type = match.group(1).upper() if match else 'DB'
            # 地标的 std_type_no 为 02
            std_type_no = '02' 
            
            c_name = n(row.get('标准名称'))
            r_date = clean_date(row.get('发布日期'))
            i_date = clean_date(row.get('实施日期'))
            e_state_str = n(row.get('标准状态'))
            e_state = state_map.get(e_state_str, 1) if e_state_str else 1
            
            base_batch.append((std_id, std_type, std_type_no, c_name, r_date, i_date, e_state))
        
        # INSERT IGNORE 保证若存在同样的标准号，不会抛错而是跳过
        cursor.executemany("""
            INSERT IGNORE INTO std_base (std_id, std_type, std_type_no, std_chinesename, release_date, implement_date, ex_state)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, base_batch)
        conn.commit()
        print(f"[SUCCESS] std_base 录入完毕（如果有重复标准号已被跳过）。")
        
        # ------- Phase 2: 获取刚插入的地标 mapped ID，录入 std_db_detail -------
        print("[PROCESS] 2/3 正在加载 ID 映射并写入 std_db_detail...")
        cursor.execute("SELECT id, std_id FROM std_base WHERE std_type_no = '02'")
        id_mapping = {r['std_id']: r['id'] for r in cursor.fetchall()}
        
        detail_batch = []
        extend_batch = []
        
        for _, row in df.iterrows():
            sid = n(row.get('标准号'))
            if sid not in id_mapping: continue
            base_id = id_mapping[sid]
            
            # std_db_detail 字段
            indu_type = n(row.get('行业分类'))
            s_indu_type = n(row.get('标准类别'))
            ccs = n(row.get('中国标准分类号'))
            ics = n(row.get('国际标准分类号'))
            rec_no = n(row.get('备案号'))
            rec_date = clean_date(row.get('备案日期'))
            rev_type = n(row.get('制修订'))
            tech_c = n(row.get('技术归口'))
            app_dept = n(row.get('批准发布部门'))
            
            detail_batch.append((
                base_id, ccs, ics, indu_type, s_indu_type, rec_no, rec_date, rev_type, tech_c, app_dept
            ))
            
            # std_extend_h 起草单位处理
            draft_u = n(row.get('起草单位'))
            if draft_u:
                extend_batch.append((base_id, '地标', draft_u))

        cursor.executemany("""
            INSERT INTO std_db_detail 
            (base_id, ccs, ics, industry_type, std_indu_type, record_no, record_date, rev_type, tech_committee, approve_dept)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                ccs=VALUES(ccs), ics=VALUES(ics), industry_type=VALUES(industry_type), std_indu_type=VALUES(std_indu_type),
                record_no=VALUES(record_no), record_date=VALUES(record_date), rev_type=VALUES(rev_type),
                tech_committee=VALUES(tech_committee), approve_dept=VALUES(approve_dept)
        """, detail_batch)
        conn.commit()
        print(f"[SUCCESS] std_db_detail 详情表录入成功，共计 {len(detail_batch)} 条记录。")

        # ------- Phase 3: 追加至 std_extend_h -------
        print("[PROCESS] 3/3 正在将起草单位追加至 std_extend_h...")
        if extend_batch:
            # 追加写入
            cursor.executemany("""
                INSERT INTO std_extend_h (base_id, std_type, draft_unit)
                VALUES (%s, %s, %s)
            """, extend_batch)
            conn.commit()
            print(f"[SUCCESS] std_extend_h 追加完毕，地标起草单位共 {len(extend_batch)} 条记录。")
        else:
            print("[INFO] Excel 中未找到起草单位数据。")
            
        print("[FINISHED] 地标所有数据迁移完成！")

    except Exception as e:
        conn.rollback()
        print(f"[ERROR] 发生致命错误: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    run_db_migration()
