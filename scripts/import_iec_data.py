import _path  # noqa: F401

import os
import pandas as pd
import pymysql
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 数据库配置
db_config = {
    'host': os.getenv('DB_HOST', '127.0.0.1'),
    'port': int(os.getenv('DB_PORT', 3306)),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', 'lsj223546'),
    'database': os.getenv('DB_NAME', 'mydate'),
    'charset': 'utf8mb4'
}

def setup_database():
    """创建 IEC 详情表和更新视图"""
    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()
    try:
        # 1. 创建 std_iec_detail
        print("正在检查/创建 std_iec_detail 表...")
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS `std_iec_detail` (
            `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
            `base_id` BIGINT UNSIGNED NOT NULL COMMENT '关联 std_base.id',
            `nat_issue` VARCHAR(30) DEFAULT NULL COMMENT '国际组织机构',
            `std_varsion` FLOAT DEFAULT NULL COMMENT '版本',
            `std_EN` VARCHAR(8) DEFAULT NULL COMMENT '标准语言',
            `std_rele_issue` VARCHAR(20) DEFAULT NULL COMMENT '标准发布组织',
            UNIQUE INDEX `uk_base_id` (`base_id`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='IEC国际标准详情表';
        """
        cursor.execute(create_table_sql)

        # 2. 更新 view_std_full (整合 ISO 和 IEC 详情)
        print("正在检查/更新 view_std_full 视图...")
        update_view_sql = """
        CREATE OR REPLACE VIEW view_std_full AS
        SELECT b.id, b.std_id, b.std_type, b.std_type_no, b.std_chinesename, b.std_englishname, b.release_date, b.implement_date, b.ex_state, b.create_time,
               COALESCE(g.ccs, h.ccs, d.ccs) AS ccs,
               COALESCE(g.ics, h.ics, d.ics) AS ics,
               COALESCE(g.drafter, h.drafter) AS drafter,
               COALESCE(g.report_unit, h.report_unit) AS report_unit,
               COALESCE(g.sub_report_unit, h.sub_report_unit) AS sub_report_unit,
               COALESCE(h.industry_type, d.industry_type) AS industry_type, 
               COALESCE(h.std_indu_type, d.std_indu_type) AS std_indu_type, 
               COALESCE(h.record_no, d.record_no) AS record_no, 
               COALESCE(h.record_date, d.record_date) AS record_date, 
               COALESCE(h.rev_type, d.rev_type) AS rev_type, 
               COALESCE(h.tech_committee, d.tech_committee) AS tech_committee, 
               COALESCE(h.approve_dept, d.approve_dept) AS approve_dept,
               COALESCE(i.std_varsion, ie.std_varsion) AS std_varsion,
               COALESCE(i.std_EN, ie.std_EN) AS std_EN,
               COALESCE(i.std_rele_issue, ie.std_rele_issue) AS std_rele_issue,
               ie.nat_issue
        FROM std_base b
        LEFT JOIN std_gb_detail g ON b.id = g.base_id
        LEFT JOIN std_hb_detail h ON b.id = h.base_id
        LEFT JOIN std_db_detail d ON b.id = d.base_id
        LEFT JOIN std_iso_detail i ON b.id = i.base_id
        LEFT JOIN std_iec_detail ie ON b.id = ie.base_id;
        """
        cursor.execute(update_view_sql)
        conn.commit()
        print("数据库结构准备就绪。")
    except Exception as e:
        print(f"数据库设置失败: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

def import_iec_data():
    excel_path = r'E:\Downloads\IEC国际标准目录.xlsx'
    if not os.path.exists(excel_path):
        print(f"错误: 找不到文件 {excel_path}")
        return

    print(f"正在读取 Excel 文件: {excel_path}")
    try:
        df = pd.read_excel(excel_path, engine='openpyxl')
    except Exception as e:
        print(f"读取 Excel 失败: {e}")
        return
    
    # 清洗列名
    df.columns = [str(c).strip() for c in df.columns]
    print(f"读取完成，共 {len(df)} 行数据。")
    
    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()
    
    success_count = 0
    skip_count = 0
    
    try:
        for index, row in df.iterrows():
            std_id = str(row['标准号']).strip()
            if not std_id or std_id == 'nan':
                continue
            
            # 1. 插入 std_base (追加且防重)
            base_sql = """
            INSERT IGNORE INTO std_base 
            (std_id, std_type, std_type_no, std_chinesename, std_englishname, release_date, ex_state) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            
            # 状态映射
            ex_state_str = str(row['状态']).strip()
            if ex_state_str == '现行':
                ex_state = 1
            elif ex_state_str == '废止':
                ex_state = 0
            elif ex_state_str == '即将实施':
                ex_state = 2
            else:
                ex_state = None
            
            # 日期转换
            release_date = row['发布日期']
            if pd.isna(release_date):
                release_date = None
            else:
                try:
                    release_date = pd.to_datetime(release_date).date()
                except:
                    release_date = None

            cursor.execute(base_sql, (
                std_id,
                'IEC',
                '05',
                str(row['中文名称']).strip() if pd.notna(row['中文名称']) else None,
                str(row['英文名称']).strip() if pd.notna(row['英文名称']) else None,
                release_date,
                ex_state
            ))
            
            if cursor.rowcount == 0:
                skip_count += 1
                continue
            
            base_id = cursor.lastrowid
            
            # 2. 插入 std_iec_detail
            detail_sql = """
            INSERT INTO std_iec_detail 
            (base_id, nat_issue, std_varsion, std_EN, std_rele_issue) 
            VALUES (%s, %s, %s, %s, %s)
            """
            
            # 版本转 float
            std_varsion_val = row['版本']
            try:
                if pd.notna(std_varsion_val):
                    std_varsion = float(std_varsion_val)
                else:
                    std_varsion = None
            except:
                std_varsion = None
                
            cursor.execute(detail_sql, (
                base_id,
                str(row['国际组织机构']).strip() if pd.notna(row['国际组织机构']) else None,
                std_varsion,
                str(row['标准语言']).strip() if pd.notna(row['标准语言']) else None,
                str(row['标准发布组织']).strip() if pd.notna(row['标准发布组织']) else None
            ))
            
            success_count += 1
            if success_count % 500 == 0:
                print(f"进度: 已导入 {success_count} 条...")
        
        conn.commit()
        print(f"IEC 导入任务完成！")
        print(f"--------------------------")
        print(f"总记录数: {len(df)}")
        print(f"成功导入: {success_count} 条")
        print(f"跳过已存在: {skip_count} 条")
        print(f"--------------------------")
        
    except Exception as e:
        conn.rollback()
        print(f"发生错误: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    setup_database()
    import_iec_data()
