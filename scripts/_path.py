"""将项目根目录加入 sys.path（scripts 下脚本 import db_config 前需先 import 本模块）。"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
