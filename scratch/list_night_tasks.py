import subprocess
import csv
import io
import re

def list_night_tasks():
    result = subprocess.run(['schtasks', '/query', '/v', '/fo', 'CSV'], capture_output=True, text=True, encoding='gbk', errors='ignore')
    reader = csv.reader(io.StringIO(result.stdout))
    header = next(reader)
    
    # Try to find the 'Next Run Time' or 'Start Time' column
    # Based on previous output, Column 2 seems to be 'Next Run Time'
    # Column 19 seems to be 'Start Time'
    
    print("Tasks running at night (00:00 - 06:00):")
    for row in reader:
        try:
            # Check Column 19 (Start Time)
            start_time_str = row[19]
            # Format is usually HH:mm:ss or H:mm:ss
            match = re.search(r'(\d{1,2}):(\d{2}):(\d{2})', start_time_str)
            if match:
                hour = int(match.group(1))
                if 0 <= hour <= 6:
                    print(f"Task: {row[1]} | Start Time: {start_time_str} | Action: {row[8]}")
        except:
            continue

if __name__ == "__main__":
    list_night_tasks()
