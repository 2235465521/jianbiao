import _path  # noqa: F401

import pymysql
import subprocess
import os
import time
from datetime import datetime

# --- 配置区 ---
DB_CONFIG = {
    'host': '127.0.0.1',
    'port': 3306,
    'user': 'root',
    'password': 'lsj223546',
    'database': 'mydate',
    'charset': 'utf8mb4'
}

# 脚本路径 (请确保这些文件在同一目录下)
GEO_SCRIPT = 'api_match_area_code.py'
TRANS_SCRIPT = 'translate_std_names.py'
AREA_COORD_SCRIPT = 'update_area_coordinates.py'
LOG_FILE = 'automation_tasks.log'

def write_log(message):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_msg = f'[{timestamp}] {message}\n'
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_msg)
    print(log_msg.strip())

def check_work():
    # --- 任务已手动关停 ---
    write_log("Notice: Nightly automation task has been disabled by user request.")
    return

    # 检查是否是半夜 (凌晨 0点 - 6点)
    current_hour = datetime.now().hour
    if not (0 <= current_hour <= 6):
        write_log("Skipping: Current time is not between 00:00 and 06:00 (Asia/Shanghai).")
        return

    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    try:
        # 1. 预检行政区划经纬度
        cursor.execute("SELECT COUNT(*) FROM area_dict WHERE longitude IS NULL OR latitude IS NULL")
        area_count = cursor.fetchone()[0]
        if area_count > 0:
            write_log(f"Detected {area_count} area_dict records missing coordinates. Starting update...")
            subprocess.run(['python', AREA_COORD_SCRIPT], check=False)
            write_log("Area coordinate update completed.")
        else:
            write_log("Area coordinates: All records complete. Skipping.")

        # 2. 预检起草单位地域赋码
        cursor.execute("SELECT COUNT(*) FROM unit_dict WHERE area_code IS NULL OR area_code = ''")
        geo_count = cursor.fetchone()[0]
        
        if geo_count > 0:
            write_log(f"Detected {geo_count} units missing area_code. Starting Geocoding...")
            subprocess.run(['python', GEO_SCRIPT], check=False)
            write_log("Geocoding task completed/paused.")
        else:
            write_log("Geocoding: No new data found. Skipping.")

        # 2. 预检标准翻译
        cursor.execute("SELECT COUNT(*) FROM std_base WHERE std_englishname IS NULL OR std_englishname = ''")
        trans_count = cursor.fetchone()[0]
        
        if trans_count > 0:
            write_log(f"Detected {trans_count} standards missing English names. Starting Translation...")
            subprocess.run(['python', TRANS_SCRIPT], check=False)
            write_log("Translation task completed/paused.")
        else:
            write_log("Translation: No new data found. Skipping.")

    except Exception as e:
        write_log(f"Error during pre-check: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    write_log("=== Automation Scheduler Heartbeat ===")
    check_work()
    write_log("=== Scheduler Session Finished ===")
