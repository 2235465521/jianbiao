import pymysql
import json
import re
import os

DB_CONFIG = {
    'host': '127.0.0.1', 
    'user': 'root', 
    'password': 'lsj223546', 
    'database': 'mydate', 
    'charset': 'utf8mb4'
}

def get_real_data():
    try:
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # 找一个节点最多的家族
        cursor.execute('SELECT ped_id, COUNT(*) as cnt FROM std_pedigree GROUP BY ped_id ORDER BY cnt DESC LIMIT 1')
        best_ped = cursor.fetchone()
        if not best_ped: 
            print("No pedigree found in database.")
            return None
            
        ped_id = best_ped[0]
        print(f"Extracting data for ped_id: {ped_id}")
        
        # 获取家族成员
        cursor.execute('SELECT b.std_id, b.id FROM std_base b JOIN std_pedigree p ON b.id = p.base_id WHERE p.ped_id = %s', (ped_id,))
        rows = cursor.fetchall()
        id_map = {row[1]: row[0] for row in rows}
        base_ids = list(id_map.keys())
        
        nodes = list(id_map.values())
        edges = []
        
        if base_ids:
            # 这里的 base_ids 是个列表，需要转成 SQL 格式
            format_strings = ','.join(['%s'] * len(base_ids))
            cursor.execute(f'SELECT b.std_id, r.replace_std_name, r.replace_id FROM std_replace r JOIN std_base b ON r.base_id = b.id WHERE r.base_id IN ({format_strings})', tuple(base_ids))
            
            for row in cursor.fetchall():
                source, target_name, target_id = row[0], row[1], row[2]
                final_target = id_map.get(target_id, target_name)
                if final_target not in nodes: 
                    nodes.append(final_target)
                edges.append({'source': source, 'target': final_target})
        
        conn.close()
        return {'nodes': nodes, 'edges': edges, 'ped_id': ped_id}
    except Exception as e:
        print(f'DB Error: {e}')
        return None

def main():
    data = get_real_data()
    if data:
        html_path = 'e:/建表/pedigree_demo.html'
        if not os.path.exists(html_path):
            print(f"Error: {html_path} not found.")
            return
            
        with open(html_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        json_str = json.dumps({'nodes': data['nodes'], 'edges': data['edges']}, ensure_ascii=False, indent=4)
        
        # 替换 rawJsonData
        new_content = re.sub(r'const rawJsonData = \{.*?\};', f'const rawJsonData = {json_str};', content, flags=re.DOTALL)
        # 替换标题
        new_content = re.sub(r'title: \{ text: \".*?\"', f'title: {{ text: "真实谱系数据演示 (家族ID: {data["ped_id"]})"', new_content)
        
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f'Successfully injected real data for ped_id {data["ped_id"]}')
    else:
        print('Process failed.')

if __name__ == "__main__":
    main()
