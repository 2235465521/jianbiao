import subprocess
import csv
import io

def list_tasks():
    result = subprocess.run(['schtasks', '/query', '/v', '/fo', 'CSV'], capture_output=True, text=True, encoding='gbk', errors='ignore')
    reader = csv.reader(io.StringIO(result.stdout))
    header = next(reader)
    for row in reader:
        if any('auto_run_governance.py' in col for col in row):
            print(f"Full Row: {row}")
            # Try to construct the TN from the row
            # Usually column 1 is the TaskName
            # Column 0 might be the Folder or HostName
            print(f"Col 0: {row[0]}")
            print(f"Col 1: {row[1]}")

if __name__ == "__main__":
    list_tasks()
