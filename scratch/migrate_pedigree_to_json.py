import pymysql
import json
import re

DB_CONFIG = {
    'host': '127.0.0.1', 
    'user': 'root', 
    'password': 'lsj223546', 
    'database': 'mydate', 
    'charset': 'utf8mb4'
}

def migrate():
    try:
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        print("Starting global pedigree migration to JSON...")
        
        # 1. 找出所有家族的族长 (最新标准)
        cursor.execute('SELECT DISTINCT ped_id, std_id_latest FROM std_pedigree')
        families = cursor.fetchall()
        total = len(families)
        print(f"Found {total} families to process.")

        # 预加载 base_id 映射
        print("Loading standard ID mappings...")
        cursor.execute('SELECT std_id, id FROM std_base')
        id_map = {row[0]: row[1] for row in cursor.fetchall()}
        rev_id_map = {v: k for k, v in id_map.items()}

        count = 0
        for ped_id, latest_std in families:
            if not latest_std: continue
            root_id = id_map.get(latest_std)
            if not root_id: continue

            # DFS 算法递归
            nodes = set()
            edges = []
            visited = set()
            
            def dfs(curr_id):
                if curr_id in visited: return
                visited.add(curr_id)
                name = rev_id_map.get(curr_id, str(curr_id))
                nodes.add(name)
                
                # 查询该标准的直接替代关系
                cursor.execute('SELECT replace_id, replace_std_name FROM std_replace WHERE base_id = %s', (curr_id,))
                for r_id, r_name in cursor.fetchall():
                    target = rev_id_map.get(r_id, r_name)
                    nodes.add(target)
                    edges.append({'source': name, 'target': target})
                    if r_id: 
                        dfs(r_id)
            
            try:
                dfs(root_id)
                # 组装 JSON 并回写
                chain_json = json.dumps({'nodes': list(nodes), 'edges': edges}, ensure_ascii=False)
                cursor.execute('UPDATE std_ped_chain SET ped_chain = %s WHERE ped_id = %s', (chain_json, ped_id))
                count += 1
                if count % 100 == 0:
                    print(f"Processed {count}/{total} families...")
            except Exception as e:
                print(f"Error processing family {ped_id}: {e}")
        
        conn.commit()
        conn.close()
        print(f"Successfully migrated {count} families to JSON format.")
        return True
    except Exception as e:
        print(f"Migration failed: {e}")
        return False

if __name__ == "__main__":
    migrate()
