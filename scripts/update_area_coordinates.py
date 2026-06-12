import _path
from db_config import DB_CONFIG  # noqa: F401

import pymysql
import requests
import time

# --- 配置区 ---


AMAP_API_KEY = "58aa831e6e3f6f9908c626eae6afc1ee"
GEOCODE_API_URL = "https://restapi.amap.com/v3/geocode/geo"

def update_area_coordinates():
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    try:
        # 1. 查找经纬度缺失的行政区划
        print("正在查找经纬度缺失的行政区划...")
        query = """
            SELECT area_code, province_name, city_name, county_name, level 
            FROM area_dict 
            WHERE longitude IS NULL OR latitude IS NULL
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        print(f"共发现 {len(rows)} 条缺失坐标的记录。")

        if not rows:
            print("所有坐标均已补全，无需操作。")
            return

        session = requests.Session()
        success_count = 0

        for area_code, prov, city, county, level in rows:
            # 构造搜索名称
            # 如果是省(level 1)，搜省名；如果是市(level 2)，搜省+市；如果是区(level 3)，搜省+市+区
            address = (prov or "") + (city or "") + (county or "")
            
            params = {
                'address': address,
                'key': AMAP_API_KEY
            }
            
            try:
                response = session.get(GEOCODE_API_URL, params=params, timeout=5)
                data = response.json()
                
                if data.get("status") == "1" and data.get("count") != "0":
                    location = data["geocodes"][0]["location"] # 格式: "lng,lat"
                    lng, lat = location.split(',')
                    
                    # 更新数据库
                    update_sql = "UPDATE area_dict SET longitude = %s, latitude = %s WHERE area_code = %s"
                    cursor.execute(update_sql, (lng, lat, area_code))
                    success_count += 1
                    
                    if success_count % 50 == 0:
                        print(f"已成功补全 {success_count} 条坐标...")
                        conn.commit() # 分批提交
                
                # 限流
                time.sleep(0.1)
                
            except Exception as e:
                print(f"处理 {address} 时出错: {e}")
                continue

        conn.commit()
        print(f"任务完成！共成功补全 {success_count} 条坐标记录。")

    except Exception as e:
        print(f"执行失败: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    update_area_coordinates()
