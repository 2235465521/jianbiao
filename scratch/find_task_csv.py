import subprocess
import csv
import io

def find_task_csv():
    result = subprocess.run(['schtasks', '/query', '/v', '/fo', 'CSV'], capture_output=True, text=True, encoding='gbk', errors='ignore')
    reader = csv.reader(io.StringIO(result.stdout))
    header = next(reader)
    print(f"Header: {header}")
    for row in reader:
        if any('auto_run_governance.py' in col for col in row):
            print(f"Match Row: {row}")
            return
    print("Task not found in CSV.")

if __name__ == "__main__":
    find_task_csv()
