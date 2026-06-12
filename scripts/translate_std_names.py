import _path
from db_config import DB_CONFIG  # noqa: F401

import pymysql
import requests
import hashlib
import random
import time
import json

# --- 配置区 ---


BAIDU_APP_ID = "20260430002604998"
BAIDU_SECRET_KEY = "MGC2o1ZfMIdl3qLmWm9t"
BAIDU_API_URL = "https://fanyi-api.baidu.com/api/trans/vip/translate"

# 每次批处理的条数 (百度单次请求限 6000 字节，建议 20-50 条)
BATCH_SIZE = 30
# 请求间隔 (标准版 API 每秒限 1 次请求，高级版限 10 次。这里设为 1.1s 确保安全)
REQUEST_INTERVAL = 1.1 

def make_sign(q, salt):
    str_to_sign = BAIDU_APP_ID + q + str(salt) + BAIDU_SECRET_KEY
    return hashlib.md5(str_to_sign.encode('utf-8')).hexdigest()

def translate_batch(names):
    # 将多个中文名用换行符连接
    q = "\n".join(names)
    salt = random.randint(32768, 65536)
    sign = make_sign(q, salt)
    
    params = {
        'q': q,
        'from': 'zh',
        'to': 'en',
        'appid': BAIDU_APP_ID,
        'salt': salt,
        'sign': sign
    }
    
    try:
        response = requests.get(BAIDU_API_URL, params=params, timeout=10)
        result = response.json()
        
        if 'trans_result' in result:
            # 翻译出来的英文名后面统一加个 "."
            return [res['dst'] + "." for res in result['trans_result']]
        else:
            print(f"翻译接口报错: {result}")
            return None
    except Exception as e:
        print(f"请求发生异常: {e}")
        return None

def main():
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    try:
        # 1. 锁定需要翻译的记录
        print("正在查询缺失英文名称的记录...")
        cursor.execute("""
            SELECT id, std_chinesename 
            FROM std_base 
            WHERE (std_englishname IS NULL OR std_englishname = '') 
            AND std_chinesename IS NOT NULL 
            AND std_chinesename != ''
        """)
        records = cursor.fetchall()
        total_needed = len(records)
        print(f"共发现 {total_needed} 条记录需要翻译补全。")
        
        if total_needed == 0:
            return

        # 2. 分批处理
        for i in range(0, total_needed, BATCH_SIZE):
            batch = records[i:i + BATCH_SIZE]
            ids = [r[0] for r in batch]
            ch_names = [r[1] for r in batch]
            
            print(f"正在处理第 {i+1} ~ {i + len(batch)} 条...")
            
            # 调用翻译接口
            en_names = translate_batch(ch_names)
            
            if en_names and len(en_names) == len(ids):
                # 批量更新数据库
                update_data = [(en_names[j], ids[j]) for j in range(len(ids))]
                cursor.executemany("UPDATE std_base SET std_englishname = %s WHERE id = %s", update_data)
                conn.commit()
                print(f"  -> 成功补全 {len(ids)} 条数据。")
            else:
                print(f"  -> 批处理失败，跳过本批。")
                
            # 控制频率
            time.sleep(REQUEST_INTERVAL)
            
    except Exception as e:
        print(f"主程序异常: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    main()
