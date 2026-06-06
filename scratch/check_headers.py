import pandas as pd
import json
import sys

file_path = r'e:\建表\插入文档\5.10国标提取结果全量信息.csv'

try:
    # Try reading as Excel first since previous case showed XLSX disguised as CSV
    try:
        df = pd.read_excel(file_path, engine='openpyxl')
    except:
        df = pd.read_csv(file_path)
    
    print(f"Detected Columns: {df.columns.tolist()}")
except Exception as e:
    print(f"Error: {e}")
