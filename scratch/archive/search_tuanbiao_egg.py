# -*- coding: utf-8 -*-
import re
from pathlib import Path

SQL = Path(r"C:\Users\20711\Desktop\mydate\mydate_std_base.sql")
KEYS = ["国际采购", "打蛋器", "小家电", "手持式", "电动打蛋"]
UNIT = "福建理工大学"

# search std_base sql
hits = []
with SQL.open("r", encoding="utf-8", errors="replace") as f:
    for line in f:
        if "打蛋器" in line or ("国际采购" in line and "小家电" in line):
            for key in ["打蛋器", "国际采购"]:
                if key not in line:
                    continue
                idx = 0
                while True:
                    p = line.find(key, idx)
                    if p < 0:
                        break
                    start = line.rfind("(", 0, p)
                    end = line.find(")", p)
                    if start >= 0 and end > start:
                        chunk = line[start + 1 : end]
                        m = re.match(
                            r"(\d+),'([^']*?)','([^']*?)','([^']*?)','[^']*?','((?:[^'\\]|\\.)*?)'",
                            chunk,
                        )
                        if m:
                            ch = m.group(5).replace("\\'", "'")
                            hits.append(
                                (int(m.group(1)), m.group(2), m.group(4), ch)
                            )
                    idx = p + 1

print("=== std_base matches ===")
seen = set()
for bid, sid, tno, ch in hits:
    if bid in seen:
        continue
    seen.add(bid)
    print(bid, sid, tno, ch)

# search extend_h for 福建理工 + 打蛋
EXT = Path(r"C:\Users\20711\Desktop\mydate\mydate_std_extend_h.sql")
print("\n=== extend_h 福建理工 + 打蛋/小家电/国际采购 ===")
with EXT.open("r", encoding="utf-8", errors="replace") as f:
    for line in f:
        if UNIT not in line:
            continue
        if not any(k in line for k in ["打蛋", "小家电", "国际采购"]):
            continue
        for m in re.finditer(
            r"\((\d+),(\d+),'([^']*?)','((?:[^'\\]|\\.)*?)'\)", line
        ):
            if UNIT in m.group(4):
                print(m.group(2), m.group(3), m.group(4)[:120])

# grep 国际采购 in base with python line scan
print("\n=== 国际采购 + 小家电 in std_base ===")
with SQL.open("r", encoding="utf-8", errors="replace") as f:
    for line in f:
        if "国际采购" in line and "小家电" in line:
            # extract chinese names containing both
            for m in re.finditer(r"'((?:[^'\\]|\\.)*?)'", line):
                t = m.group(1).replace("\\'", "'")
                if "国际采购" in t and "小家电" in t:
                    print(" ", t[:100])
