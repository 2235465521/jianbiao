import _path
from db_config import DB_CONFIG  # noqa: F401

import pymysql
import requests
import time



AMAP_API_KEY = "58aa831e6e3f6f9908c626eae6afc1ee"
GEOCODE_API_URL = "https://restapi.amap.com/v3/geocode/geo"

def run_api_matching():
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    try:
        print("1. 正在筛选 Top 5000 的隐性高频起草单位...")
        # 筛选 area_code 依然为空的单位，按照参与起草标准的次数降序排列，取前 5000 个
        query = """
            SELECT u.unit_id, u.unit_name 
            FROM unit_dict u
            JOIN std_unit_relation r ON u.unit_id = r.unit_id
            WHERE u.area_code IS NULL
            GROUP BY u.unit_id
            ORDER BY COUNT(r.id) DESC
            LIMIT 5000
        """
        cursor.execute(query)
        top_units = cursor.fetchall()
        print(f"成功锁定 {len(top_units)} 个待调取 API 的核心单位！")
        
        update_batch = []
        success_count = 0
        fail_count = 0
        
        print("2. 开始调用高德地图 API 获取行政区划代码 (Adcode)...")
        session = requests.Session()
        
        for idx, (unit_id, unit_name) in enumerate(top_units):
            # 限流：每秒最多 10~20 个请求，防止被高德拉黑
            time.sleep(0.05)
            
            if idx > 0 and idx % 500 == 0:
                print(f"  -> 已处理 {idx}/{len(top_units)}，当前成功率：{success_count/idx*100:.1f}%")
                
            params = {
                'address': unit_name,
                'key': AMAP_API_KEY
            }
            
            try:
                response = session.get(GEOCODE_API_URL, params=params, timeout=5)
                data = response.json()
                
                if data.get("status") == "1" and data.get("count") != "0":
                    geocodes = data.get("geocodes", [])
                    if geocodes and len(geocodes) > 0:
                        adcode = geocodes[0].get("adcode")
                        if adcode and adcode.strip():
                            update_batch.append((adcode, unit_id))
                            success_count += 1
                            continue
                
                # 如果没有命中或者没有解析出 adcode
                fail_count += 1
                
            except Exception as req_err:
                # 记录单次网络请求异常，但不中断循环
                fail_count += 1
                pass

        print(f"API 爬取结束！成功: {success_count} 条，无法定位: {fail_count} 条。")
        
        print("3. 正在回写数据至数据库...")
        if update_batch:
            update_sql = "UPDATE unit_dict SET area_code = %s WHERE unit_id = %s"
            # 分批写入
            batch_size = 1000
            for i in range(0, len(update_batch), batch_size):
                cursor.executemany(update_sql, update_batch[i:i+batch_size])
            conn.commit()
            print("数据回写成功！数据库区域精度大幅提升！")
        else:
            print("没有提取到任何有效数据，无需回写。")
            
    except Exception as e:
        conn.rollback()
        print(f"执行出错: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    start_time = time.time()
    run_api_matching()
    print(f"总计耗时: {time.time() - start_time:.2f} 秒")
