"""将项目根目录加入 sys.path，保证高并发 Demo 脚本能正确导入外部依赖。"""
import sys
from pathlib import Path

# demos/high_throughput_user_demo is depth 2 from root, so parents[2] is the project root
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
