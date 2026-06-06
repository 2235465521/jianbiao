import pymysql
import os

def init_db():
    try:
        conn = pymysql.connect(
            host='127.0.0.1',
            port=3306,
            user='root',
            password='lsj223546',
            database='mydate',
            charset='utf8mb4'
        )
        cursor = conn.cursor()
        
        sql_file_path = r'e:\建表\init_schema.sql'
        print(f"Reading SQL file from: {sql_file_path}")
        
        with open(sql_file_path, 'r', encoding='utf-8') as f:
            # Simple split by ';' - might need better splitting if comments have ';'
            # but for DDL it usually works.
            sql_content = f.read()
            # Basic cleaning of comments and splitting
            commands = sql_content.split(';')
            
            for cmd in commands:
                clean_cmd = cmd.strip()
                if clean_cmd:
                    print(f"Executing command starting with: {clean_cmd[:50]}...")
                    cursor.execute(clean_cmd)
            
        conn.commit()
        print("Success: All tables created successfully in 'mydate' database.")
        
    except Exception as e:
        print(f"Error initializing database: {e}")
    finally:
        if 'conn' in locals() and conn.open:
            cursor.close()
            conn.close()

if __name__ == "__main__":
    init_db()
