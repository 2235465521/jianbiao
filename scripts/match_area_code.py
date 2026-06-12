import _path
from db_config import DB_CONFIG  # noqa: F401

import pymysql
import re
import time



def clean_area_name(name):
    """去除行政区划名称的常见后缀，提取核心地名"""
    if not name:
        return ""
    suffixes = ['特别行政区', '维吾尔自治区', '壮族自治区', '回族自治区', '自治区', '省', '市', '自治州', '地区', '盟']
    for suffix in suffixes:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break
    return name

def build_area_keywords(cursor):
    """从 area_dict 构建省市地名词库字典"""
    cursor.execute("SELECT area_code, province_name, city_name, level FROM area_dict WHERE level IN (1, 2)")
    rows = cursor.fetchall()
    
    keywords_map = {}
    
    for area_code, prov, city, level in rows:
        if level == 1:
            name = prov
        else:
            name = city
            
        if not name:
            continue
            
        # 存入全称
        if name not in keywords_map:
            keywords_map[name] = area_code
            
        # 存入简称
        short_name = clean_area_name(name)
        if len(short_name) >= 2 and short_name not in keywords_map:
            # 避免简称覆盖，例如吉林省(22)和吉林市(2202)，保留省级优先或者保留市级均可
            # 我们采取不覆盖策略，或者全称优先
            keywords_map[short_name] = area_code
            
    return keywords_map

def find_best_area_code(unit_name, keywords_map):
    """在单位名称中寻找最佳的 area_code"""
    # 1. 优先提取括号内的文本
    brackets_content = re.findall(r'[(（](.*?)[)）]', unit_name)
    if brackets_content:
        # 倒序遍历括号（如果有多个括号，优先看最后的）
        for content in reversed(brackets_content):
            # 检查括号内容是否包含地名
            best_match = None
            best_idx = -1
            for kw, code in keywords_map.items():
                idx = content.rfind(kw)
                if idx > best_idx:
                    best_match = code
                    best_idx = idx
            if best_match:
                return best_match
                
    # 2. 如果没有括号或括号内没有地名，全文应用“最右侧匹配原则”
    best_match = None
    best_idx = -1
    for kw, code in keywords_map.items():
        idx = unit_name.rfind(kw)
        if idx > best_idx:
            best_match = code
            best_idx = idx
            
    return best_match

def match_units():
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    try:
        print("1. 正在从 area_dict 加载行政区划地名词库...")
        keywords_map = build_area_keywords(cursor)
        print(f"成功加载 {len(keywords_map)} 个地名词条（含全称与简称）。")
        
        print("2. 正在读取 unit_dict 中尚未匹配的起草单位...")
        cursor.execute("SELECT unit_id, unit_name FROM unit_dict WHERE area_code IS NULL")
        units = cursor.fetchall()
        print(f"共获取到 {len(units)} 个待匹配单位。开始执行地名特征提取...")
        
        update_batch = []
        match_count = 0
        
        for unit_id, unit_name in units:
            code = find_best_area_code(unit_name, keywords_map)
            if code:
                update_batch.append((code, unit_id))
                match_count += 1
                
        print(f"提取完毕，成功从名称中识别出 {match_count} 个单位的归属地（命中率：{match_count/len(units)*100:.2f}%）。")
        
        print("3. 正在将匹配到的 area_code 批量回写至数据库...")
        update_sql = "UPDATE unit_dict SET area_code = %s WHERE unit_id = %s"
        
        batch_size = 10000
        for i in range(0, len(update_batch), batch_size):
            batch = update_batch[i:i+batch_size]
            cursor.executemany(update_sql, batch)
            
        conn.commit()
        print("回写成功！第一阶段字典匹配任务圆满完成！")
        
    except Exception as e:
        conn.rollback()
        print(f"执行出错: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    start_time = time.time()
    match_units()
    print(f"总耗时: {time.time() - start_time:.2f} 秒")
