import pandas as pd
import json
import sys

def default_json(obj):
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    return str(obj)

try:
    df = pd.read_excel('111.csv', engine='openpyxl')
    
    result = {
        "columns": df.columns.tolist(),
        "row_count": len(df),
        "sample_rows": df.head(3).to_dict(orient='records')
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, default=default_json))
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
