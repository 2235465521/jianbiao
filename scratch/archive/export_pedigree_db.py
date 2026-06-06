import pymysql
import json
import os

DB_CONFIG = {
    'host': '127.0.0.1', 
    'user': 'root', 
    'password': 'lsj223546', 
    'database': 'mydate', 
    'charset': 'utf8mb4'
}

def export_all():
    try:
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        print("正在导出标准号索引...")
        # 1. 建立 标准号 -> ped_id 的索引
        cursor.execute('SELECT b.std_id, p.ped_id FROM std_base b JOIN std_pedigree p ON b.id = p.base_id')
        std_to_ped = {row[0]: row[1] for row in cursor.fetchall()}
        
        print(f"已加载 {len(std_to_ped)} 条标准映射。")
        
        print("正在导出谱系家族数据...")
        # 2. 导出所有 ped_id 对应的 JSON 链条
        cursor.execute('SELECT ped_id, ped_chain FROM std_ped_chain')
        ped_chains = {}
        for row in cursor.fetchall():
            pid, pchain = row[0], row[1]
            try:
                # 尝试解析 JSON，如果不是合法 JSON (比如是老的大括号格式)，我们跳过或处理
                json.loads(pchain)
                ped_chains[pid] = pchain
            except:
                continue
        
        conn.close()
        
        # 写入一个 JS 文件供网页直接调用
        js_path = 'e:/建表/pedigree_db.js'
        with open(js_path, 'w', encoding='utf-8') as f:
            f.write('const STD_TO_PED = ' + json.dumps(std_to_ped, ensure_ascii=False) + ';\n')
            f.write('const PED_CHAINS = ' + json.dumps(ped_chains, ensure_ascii=False) + ';\n')
        
        print(f'Successfully exported to: {js_path}')
        return True
    except Exception as e:
        print(f'Export failed: {e}')
        return False

if __name__ == "__main__":
    export_all()
