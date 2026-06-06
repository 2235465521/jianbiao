from pathlib import Path

p = Path(__file__).resolve().parents[1] / "app" / "web_import_tool.py"
lines = p.read_text(encoding="utf-8").splitlines()
# 507-823 行 (1-based) 需再缩进一级，使其位于 try 块内
for i in range(506, 823):
    if lines[i].strip():
        lines[i] = "    " + lines[i]
p.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("ok")
