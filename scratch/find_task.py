import subprocess

def find_task_name():
    result = subprocess.run(['schtasks', '/query', '/v', '/fo', 'LIST'], capture_output=True, text=True, encoding='gbk', errors='ignore')
    blocks = result.stdout.split('\n\n')
    for block in blocks:
        if 'auto_run_governance.py' in block:
            for line in block.split('\n'):
                if '任务名:' in line or 'TaskName:' in line:
                    print(line.strip())
                    return
    print("Task not found in blocks.")

if __name__ == "__main__":
    find_task_name()
