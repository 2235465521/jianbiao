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

def run_master_migration():
    # 文件路径
    PATH_GB_BASE = r"E:\Downloads\数据库数据\基础表最最新.xlsx"
    PATH_GB_DETAIL = r"E:\Downloads\数据库数据\详情信息表(1).xlsx"
    PATH_HB_FULL = r"E:\Downloads\数据库数据\行标提取结果起草单位.xlsx"

    # 连接数据库
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # --- PHASE 1: 国标 (GB) 处理 ---
        print("[PROCESS] 1/4 正在载入国标数据并进行内存合并...")
        df_gb_base = pd.read_excel(PATH_GB_BASE, dtype=str)
        df_gb_detail = pd.read_excel(PATH_GB_DETAIL, dtype=str)
        
        # 建立映射以合并
        # 注意: 详情表里叫 bz_id, 基础表里也叫 bz_id
        # 我们以基础表为准录入 Base，详情表为准录入 Detail
        # 只取基础表中出现的数据
        
        state_map = {"废止": 0, "现行": 1, "即将实施": 2}

        # 1.1 批量灌入 std_base (国标部分)
        print("[PROCESS] 正在执行国标 std_base 录入...")
        gb_base_batch = []
        for _, row in df_gb_base.iterrows():
            std_id = str(row.get('bz_id', '')).strip()
            if not std_id or std_id == 'nan': continue
            
            # 手动解析类型
            match = re.match(r'^([A-Za-z/]+)', std_id)
            s_type = match.group(1).upper() if match else 'GB'
            s_no = '00' # 国标固定编号

            c_name = str(row.get('bz_name', '')).strip()
            r_date = clean_date(row.get('bz_release_date'))
            i_date = clean_date(row.get('implement_time', row.get('implement_tine')))
            e_state = state_map.get(str(row.get('ex_state')).strip(), 1)
            
            gb_base_batch.append((std_id, s_type, s_no, c_name, r_date, i_date, e_state))
        
        cursor.executemany("""
            INSERT INTO std_base (std_id, std_type, std_type_no, std_chinesename, release_date, implement_date, ex_state)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, gb_base_batch)
        conn.commit()
        print(f"[SUCCESS] 国标基础数据录入成功: {len(gb_base_batch)} 条 (ID从1开始)")

        # 1.2 建立 ID 映射并录入 std_gb_detail
        print("[PROCESS] 正在执行国标 std_gb_detail 录入...")
        cursor.execute("SELECT id, std_id FROM std_base WHERE std_type_no = '00'")
        id_mapping_gb = {r['std_id']: r['id'] for r in cursor.fetchall()}
        
        gb_detail_batch = []
        for _, row in df_gb_detail.iterrows():
            sid = str(row.get('bz_id', '')).strip()
            if sid not in id_mapping_gb: continue
            
            base_id = id_mapping_gb[sid]
            ccs = str(row.get('ccs', '')).strip()
            ics = str(row.get('ics', '')).strip()
            drafter = str(row.get('drafter', '')).strip()
            report_unit = str(row.get('report_unit', '')).strip()
            sub_report_unit = str(row.get('sub_report_unit', '')).strip()

            def n(v): return None if not v or v == 'nan' else v
            gb_detail_batch.append((base_id, n(ccs), n(ics), n(drafter), n(report_unit), n(sub_report_unit)))

        cursor.executemany("""
            INSERT INTO std_gb_detail (base_id, ccs, ics, drafter, report_unit, sub_report_unit)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, gb_detail_batch)
        conn.commit()
        print(f"[SUCCESS] 国标详情数据录入成功: {len(gb_detail_batch)} 条 (ID从1开始)")

        # --- PHASE 2: 行标 (HB) 处理 ---
        print("[PROCESS] 2/4 正在载入行标数据...")
        df_hb = pd.read_excel(PATH_HB_FULL, dtype=str)
        
        hb_base_batch = []
        state_map_hb = {"现行": 1, "废止": 0, "即将实施": 2}
        
        for _, row in df_hb.iterrows():
            std_id = str(row.get('标准号', '')).strip()
            if not std_id or std_id == 'nan': continue
            
            match = re.match(r'^([A-Za-z/]+)', std_id)
            s_type = match.group(1).upper() if match else 'HB'
            s_no = '01' # 行标固定编号

            c_name = str(row.get('标准名称', '')).strip()
            r_date = clean_date(row.get('发布日期'))
            i_date = clean_date(row.get('实施日期'))
            e_state = state_map_hb.get(str(row.get('标准状态')).strip(), 1)
            
            hb_base_batch.append((std_id, s_type, s_no, c_name, r_date, i_date, e_state))
            
        cursor.executemany("""
            INSERT IGNORE INTO std_base (std_id, std_type, std_type_no, std_chinesename, release_date, implement_date, ex_state)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, hb_base_batch)
        conn.commit()
        print(f"[SUCCESS] 行标基础数据录入成功: {len(hb_base_batch)} 条 (ID紧随国标)")

        # 2.2 建立 ID 映射并录入 std_hb_detail 与 std_extend_h
        print("[PROCESS] 正在执行行标详情及起草单位录入...")
        cursor.execute("SELECT id, std_id FROM std_base WHERE std_type_no = '01'")
        id_mapping_hb = {r['std_id']: r['id'] for r in cursor.fetchall()}
        
        hb_detail_batch = []
        hb_extend_batch = []
        
        for _, row in df_hb.iterrows():
            sid = str(row.get('标准号', '')).strip()
            if sid not in id_mapping_hb: continue
            base_id = id_mapping_hb[sid]
            
            ccs = str(row.get('中国标准分类号', '')).strip()
            ics = str(row.get('国际标准分类号', '')).strip()
            drafter = str(row.get('起草人', '')).strip()
            tech_comm = str(row.get('技术归口', '')).strip()
            app_dept = str(row.get('批准发布部门', '')).strip()
            indu_type = str(row.get('行业分类', '')).strip()
            std_type = str(row.get('标准类别', str(row.get('标准分类', '')))).strip()
            rec_no = str(row.get('备案号', '')).strip()
            rec_date = clean_date(row.get('备案日期'))
            rev = str(row.get('制修订', '')).strip()

            def n(v): return None if not v or v == 'nan' else v
            
            hb_detail_batch.append((
                base_id, n(ccs), n(ics), n(drafter), n(tech_comm), None,
                n(indu_type), n(std_type), n(rec_no), rec_date, n(rev), n(tech_comm), n(app_dept)
            ))
            
            # 起草单位 (不放入 drafter)
            draft_unit = str(row.get('起草单位', '')).strip()
            if draft_unit and draft_unit != 'nan':
                hb_extend_batch.append((base_id, draft_unit))
                
        cursor.executemany("""
            INSERT INTO std_hb_detail 
            (base_id, ccs, ics, drafter, report_unit, sub_report_unit, 
             industry_type, std_indu_type, record_no, record_date, rev_type, tech_committee, approve_dept) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE base_id=base_id
        """, hb_detail_batch)
        
        if hb_extend_batch:
            cursor.executemany("INSERT INTO std_extend_h (base_id, draft_unit) VALUES (%s, %s)", hb_extend_batch)
            
        conn.commit()
        print(f"[SUCCESS] 行标详情录入完毕: {len(hb_detail_batch)} 条 (ID从1开始)")

        print(f"[FINISHED] 全库重构完成！")
        print(f"统计：国标(std_base 1-{len(gb_base_batch)}), 行标(std_base {len(gb_base_batch)+1}-...)")

    except Exception as e:
        conn.rollback()
        print(f"[ERROR] 迁移失败: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    run_master_migration()
