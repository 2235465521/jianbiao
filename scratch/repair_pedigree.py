import pymysql
import re
import sys
import json
from pathlib import Path

# Add project root and app directory to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from db_config import DB_CONFIG
from web_import_tool import clean_id, update_pedigree

print("开始连接数据库...")
conn = pymysql.connect(**DB_CONFIG)
try:
    with conn.cursor() as cursor:
        print("1. 加载主表 ID 映射字典...")
        cursor.execute("SELECT id, std_id, ex_state FROM std_base")
        id_map = {}
        state_map = {}
        for row in cursor.fetchall():
            cid = clean_id(row[1])
            id_map[cid] = row[0]
            state_map[row[0]] = (row[1], row[2])
            
        print(f"成功加载 {len(id_map)} 条标准。")
        
        print("\n2. 查询 std_replace 中未关联成功 (replace_id 为空) 或带中文前缀的关系...")
        cursor.execute("SELECT id, base_id, replace_std_name, replace_type FROM std_replace")
        replaces = cursor.fetchall()
        
        rebuild_base_ids = set()
        repair_count = 0
        
        for r_id, base_id, rep_name, rep_type in replaces:
            if not rep_name:
                continue
                
            # 剥离前缀修饰符（兼容有无冒号）
            clean_rep_val = re.sub(r'^(全部代替|部分代替|代替|废止|废止并代替|替代)\s*[:：]?\s*', '', rep_name)
            clean_rep_key = clean_id(clean_rep_val)
            
            target_replace_id = id_map.get(clean_rep_key)
            if target_replace_id:
                # 确定关系类型
                detected_type = rep_type
                if not detected_type:
                    if '全部代替' in rep_name:
                        detected_type = '全部代替'
                    elif '部分代替' in rep_name:
                        detected_type = '部分代替'
                
                # 更新关系表
                cursor.execute("""
                    UPDATE std_replace 
                    SET replace_id = %s, replace_std_name = %s, replace_type = %s 
                    WHERE id = %s
                """, (target_replace_id, clean_rep_val, detected_type, r_id))
                
                # 级联更新状态：若新标准是现行的，废止旧标准
                new_std_name, new_ex_state = state_map.get(base_id, (None, None))
                if new_ex_state == 1:
                    cursor.execute("UPDATE std_base SET ex_state = 0 WHERE id = %s", (target_replace_id,))
                    print(f"  [状态更新] 新标准 {new_std_name} (现行) -> 被替代的旧标准 {clean_rep_val} 已被置为废止状态(0)")
                
                rebuild_base_ids.add(base_id)
                repair_count += 1
                print(f"  [修复成功] 关系 ID {r_id}: 将 '{rep_name}' 修复为标准号 '{clean_rep_val}' (ID: {target_replace_id})")
                
        print(f"\n共成功修复 {repair_count} 条替代关系。")
        
        if rebuild_base_ids:
            print(f"\n3. 开始重新构建受影响的谱系链条 (共 {len(rebuild_base_ids)} 个标准)...")
            for b_id in rebuild_base_ids:
                std_id, _ = state_map[b_id]
                
                # 查其所有的 replaced_ids
                cursor.execute("SELECT replace_id FROM std_replace WHERE base_id = %s AND replace_id IS NOT NULL", (b_id,))
                replaced_ids = [row[0] for row in cursor.fetchall()]
                
                if replaced_ids:
                    print(f"  正在重新计算 {std_id} 的谱系树...")
                    update_pedigree(cursor, b_id, std_id, replaced_ids)
            
            print("\n谱系树重建完成！")
            
        conn.commit()
        print("\n所有修复操作已提交保存到数据库中！")
        
except Exception as e:
    conn.rollback()
    print(f"\n发生错误，事务已回滚: {e}")
finally:
    conn.close()
