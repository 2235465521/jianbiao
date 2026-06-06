import _path  # noqa: F401

import pymysql
import re
import time

DB_CONFIG = {
    'host': '127.0.0.1',
    'port': 3306,
    'user': 'root',
    'password': 'lsj223546',
    'database': 'mydate',
    'charset': 'utf8mb4'
}

def clean_and_split_units(text):
    if not text:
        return []
    
    text = text.strip()
    
    # 1. 过滤末尾的 "等"
    if text.endswith('等'):
        text = text[:-1].strip()
        
    # 2. 保护纯英文单词之间的空格 (将其替换为特殊占位符)
    text = re.sub(r'([a-zA-Z])\s+([a-zA-Z])', r'\1_SPACE_\2', text)
    
    # 3. 将常见的分隔符统一替换为特殊的全角竖线 ｜
    text = re.sub(r'[、，,；;]', '｜', text)
    
    # 4. 将两个及以上的空格视为明确的分隔符
    text = re.sub(r'\s{2,}', '｜', text)
    
    parts = text.split('｜')
    final_units = []
    
    # 定义常见实体后缀，用于在单空格分割时判断是否为独立单位
    pattern = r'((?:公司|企业|大学|学院|中心|研究院|科学院|所|局|厂|部|委员会|协会|学会|集团|分院)(?:[(（][^)）]+[)）])?)\s+(?=[\u4e00-\u9fa5])'
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
            
        if ' ' in part:
            # 利用正则将紧跟在实体后缀后面的单空格替换为分隔符 ｜
            part = re.sub(pattern, r'\1｜', part)
            sub_parts = part.split('｜')
            
            for sp in sub_parts:
                sp = sp.strip()
                if sp:
                    # 去除中文汉字之间残留的误加空格（例如 "北 京" -> "北京"）
                    sp = re.sub(r'(?<=[\u4e00-\u9fa5])\s+(?=[\u4e00-\u9fa5])', '', sp)
                    final_units.append(sp)
        else:
            final_units.append(part)
            
    # 5. 恢复英文字母间的空格，并进行去重
    res = []
    seen = set()
    for u in final_units:
        u = u.replace('_SPACE_', ' ').strip()
        if u and u not in seen:
            seen.add(u)
            res.append(u)
            
    return res

def migrate():
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    try:
        print("1. 正在从 std_extend_h 读取起草单位原始文本...")
        # 查出所有的 base_id 和 draft_unit
        cursor.execute("SELECT base_id, draft_unit FROM std_extend_h WHERE draft_unit IS NOT NULL AND draft_unit != ''")
        rows = cursor.fetchall()
        
        print(f"共读取到 {len(rows)} 条待处理数据。开始清洗拆分...")
        
        all_unique_names = set()
        base_id_to_units = [] # 保存 [(base_id, [unit1, unit2...]), ...]
        
        for base_id, draft_unit in rows:
            units = clean_and_split_units(draft_unit)
            if units:
                all_unique_names.update(units)
                base_id_to_units.append((base_id, units))
                
        print(f"清洗完毕，共提取出 {len(all_unique_names)} 个独立单位实体。")
        
        # 2. 批量插入字典表 (unit_dict)
        print("2. 正在将独立单位实体插入 unit_dict 表...")
        insert_dict_sql = "INSERT IGNORE INTO unit_dict (unit_name) VALUES (%s)"
        # 分批插入以避免单条 SQL 过大
        batch_size = 10000
        unique_names_list = list(all_unique_names)
        for i in range(0, len(unique_names_list), batch_size):
            batch = [(name,) for name in unique_names_list[i:i+batch_size]]
            cursor.executemany(insert_dict_sql, batch)
        conn.commit()
        
        # 3. 重新拉取字典表获取 ID 映射关系
        print("3. 正在加载 unit_dict 的 ID 映射表...")
        cursor.execute("SELECT unit_name, unit_id FROM unit_dict")
        name_to_id = {row[0]: row[1] for row in cursor.fetchall()}
        
        # 4. 构建多对多关系表数据 (std_unit_relation)
        print("4. 正在构建标准与起草单位的多对多关系数据...")
        relation_batch = []
        for base_id, units in base_id_to_units:
            # 保证同一个 standard 下不会重复插入同一个 unit
            seen_for_base = set()
            for idx, unit_name in enumerate(units):
                if unit_name in seen_for_base:
                    continue
                seen_for_base.add(unit_name)
                
                unit_id = name_to_id.get(unit_name)
                if unit_id is None:
                    continue
                    
                # 第一位为 主起草(1)，后面为 参与起草(2)
                role_type = 1 if idx == 0 else 2
                rank_order = idx + 1
                relation_batch.append((base_id, unit_id, role_type, rank_order))
                
        print(f"构建完成，共产生 {len(relation_batch)} 条关系记录。开始插入 std_unit_relation...")
        
        insert_rel_sql = """
            INSERT IGNORE INTO std_unit_relation 
            (base_id, unit_id, role_type, rank_order) 
            VALUES (%s, %s, %s, %s)
        """
        for i in range(0, len(relation_batch), batch_size):
            batch = relation_batch[i:i+batch_size]
            cursor.executemany(insert_rel_sql, batch)
            
        conn.commit()
        print("全量数据迁移入库成功！")
        
    except Exception as e:
        conn.rollback()
        print(f"执行出错: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    start_time = time.time()
    migrate()
    print(f"耗时: {time.time() - start_time:.2f} 秒")
