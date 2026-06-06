import subprocess
import csv
import io

def disable_matching_task():
    result = subprocess.run(['schtasks', '/query', '/v', '/fo', 'CSV'], capture_output=True, text=True, encoding='gbk', errors='ignore')
    reader = csv.reader(io.StringIO(result.stdout))
    header = next(reader)
    for row in reader:
        if any('auto_run_governance.py' in col for col in row):
            task_name = row[1]
            print(f"Found matching task: {task_name}")
            # Try to disable it using the exact string from the CSV
            cmd = ['schtasks', '/change', '/tn', task_name, '/disable']
            print(f"Running command: {' '.join(cmd)}")
            res = subprocess.run(cmd, capture_output=True, text=True, encoding='gbk', errors='ignore')
            print(f"STDOUT: {res.stdout}")
            print(f"STDERR: {res.stderr}")
            if res.returncode == 0:
                print("Successfully disabled the task!")
                return True
    return False

if __name__ == "__main__":
    disable_matching_task()
