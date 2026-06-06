import subprocess

def disable_task():
    # Try different name variations
    names = [r'\标准自动', '标准自动', r'\\标准自动']
    for name in names:
        print(f"Trying to disable: {name}")
        result = subprocess.run(['schtasks', '/change', '/tn', name, '/disable'], capture_output=True, text=True, encoding='gbk', errors='ignore')
        print(f"STDOUT: {result.stdout}")
        print(f"STDERR: {result.stderr}")
        if result.returncode == 0:
            print(f"Successfully disabled: {name}")
            return True
    return False

if __name__ == "__main__":
    disable_task()
