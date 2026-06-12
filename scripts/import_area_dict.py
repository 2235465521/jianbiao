import _path
from db_config import DB_CONFIG  # noqa: F401

import json
import pymysql
import os

from db_config import DATA_DIR

json_path = str(DATA_DIR / "pcas-code.json")

if not os.path.exists(json_path):
    print(f"本地未找到 {json_path}，尝试从网络下载...")
    import requests
    try:
        url = 'https://registry.npmmirror.com/china-division/latest/files/dist/pcas-code.json'
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        with open(json_path, 'wb') as f:
            f.write(response.content)
        print("网络下载成功！")
    except Exception as e:
        print(f"下载失败: {e}")
        exit(1)

with open(json_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

# 连接数据库 (根据你的 .env 配置)
conn = pymysql.connect(**DB_CONFIG)
cursor = conn.cursor()

records = []

# 解析嵌套的 JSON 并扁平化
for province in data:
    p_code = province['code']
    p_name = province['name']
    # 插入省份级别 (level = 1)
    records.append((p_code, p_name, None, None, 1))
    
    for city in province.get('children', []):
        c_code = city['code']
        c_name = city['name']
        # 插入城市级别 (level = 2)
        records.append((c_code, p_name, c_name, None, 2))
        
        for area in city.get('children', []):
            a_code = area['code']
            a_name = area['name']
            # 插入区县级别 (level = 3)
            records.append((a_code, p_name, c_name, a_name, 3))

print(f"成功解析 {len(records)} 条行政区划数据，准备入库...")

# 批量插入数据库
sql = """
    INSERT IGNORE INTO area_dict 
    (area_code, province_name, city_name, county_name, level) 
    VALUES (%s, %s, %s, %s, %s)
"""

try:
    cursor.executemany(sql, records)
    conn.commit()
    print("数据导入成功！")
except Exception as e:
    conn.rollback()
    print(f"数据导入失败: {e}")
finally:
    cursor.close()
    conn.close()
