"""统一数据库连接配置（从 .env 读取）"""
from pathlib import Path

from dotenv import load_dotenv
import os

# 项目根目录（本文件与 .env 同级，换机器时主要改 .env）
PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "STSC_standard_database"),
    "charset": "utf8mb4",
}

# SQL 备份文件所在目录（需先导入到 MySQL，程序才能连接）
SQL_DUMP_DIR = Path(os.getenv("SQL_DUMP_DIR", r"C:\Users\20711\Desktop\mydate"))

# PDF 物理文件根目录（与 std_filepath.file_path 相对路径拼接）
# 例：file_path=国标下载/国标/xxx.pdf → Z:\磁盘阵列\标准文件下载\国标下载\国标\xxx.pdf
PDF_ROOT = Path(os.getenv("PDF_ROOT", r"Z:\磁盘阵列"))
PDF_SUBDIR = os.getenv("PDF_SUBDIR", "标准文件下载").strip("/\\")

# 项目内固定目录（一般无需修改）
APP_DIR = PROJECT_ROOT / "app"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
SQL_DIR = PROJECT_ROOT / "sql"
DATA_DIR = PROJECT_ROOT / "data"
DOCS_DIR = PROJECT_ROOT / "docs"
LOGS_DIR = PROJECT_ROOT / "logs"
