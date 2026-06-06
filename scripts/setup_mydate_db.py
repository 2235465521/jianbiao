# -*- coding: utf-8 -*-
"""
将 C:\\Users\\20711\\Desktop\\mydate 目录下的 SQL 文件导入本机 MySQL，创建 mydate 库。

用法（在项目根目录下）:
    python scripts/setup_mydate_db.py

前提: 本机 MySQL 已安装并启动，.env 中账号密码正确。
"""
import _path  # noqa: F401

import os
import subprocess
import sys
from pathlib import Path

import pymysql

from db_config import DB_CONFIG, SQL_DUMP_DIR


def create_database():
    cfg = {k: v for k, v in DB_CONFIG.items() if k != "database"}
    conn = pymysql.connect(**cfg)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{DB_CONFIG['database']}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()
        print(f"✓ 数据库 `{DB_CONFIG['database']}` 已就绪")
    finally:
        conn.close()


def import_via_mysql_cli(sql_file: Path) -> bool:
    """优先用 mysql 命令行导入（大文件更稳）"""
    mysql_bin = os.getenv("MYSQL_BIN", "mysql")
    env = os.environ.copy()
    if DB_CONFIG["password"]:
        env["MYSQL_PWD"] = DB_CONFIG["password"]

    cmd = [
        mysql_bin,
        f"-h{DB_CONFIG['host']}",
        f"-P{DB_CONFIG['port']}",
        f"-u{DB_CONFIG['user']}",
        DB_CONFIG["database"],
    ]
    try:
        with sql_file.open("r", encoding="utf-8", errors="replace") as f:
            subprocess.run(cmd, stdin=f, env=env, check=True, capture_output=True)
        return True
    except FileNotFoundError:
        return False
    except subprocess.CalledProcessError as e:
        err = (e.stderr or b"").decode("utf-8", errors="replace")
        print(f"  ✗ {sql_file.name}: {err[:500]}")
        return False


def import_via_pymysql(sql_file: Path):
    conn = pymysql.connect(**DB_CONFIG)
    try:
        sql = sql_file.read_text(encoding="utf-8", errors="replace")
        with conn.cursor() as cur:
            for stmt in _split_sql_statements(sql):
                if stmt.strip():
                    cur.execute(stmt)
        conn.commit()
    finally:
        conn.close()


def _split_sql_statements(sql: str):
    buf, in_string, quote = [], False, None
    i = 0
    while i < len(sql):
        ch = sql[i]
        if in_string:
            buf.append(ch)
            if ch == quote and (i == 0 or sql[i - 1] != "\\"):
                in_string = False
            i += 1
            continue
        if ch in ("'", '"'):
            in_string, quote = True, ch
            buf.append(ch)
            i += 1
            continue
        if ch == ";" and not in_string:
            yield "".join(buf)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf)
    if tail.strip():
        yield tail


def test_connection():
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM std_base")
            n = cur.fetchone()[0]
        print(f"✓ 连接成功，std_base 现有 {n} 条记录")
        return True
    finally:
        conn.close()


def main():
    if not SQL_DUMP_DIR.is_dir():
        print(f"SQL 目录不存在: {SQL_DUMP_DIR}")
        sys.exit(1)

    sql_files = sorted(SQL_DUMP_DIR.glob("*.sql"))
    if not sql_files:
        print(f"目录下没有 .sql 文件: {SQL_DUMP_DIR}")
        sys.exit(1)

    print(f"SQL 目录: {SQL_DUMP_DIR}")
    print(f"目标库: {DB_CONFIG['database']} @ {DB_CONFIG['host']}:{DB_CONFIG['port']}")
    print(f"共 {len(sql_files)} 个文件，开始导入…\n")

    create_database()

    use_cli = import_via_mysql_cli(sql_files[0]) if sql_files else False
    if use_cli:
        print("使用 mysql 命令行导入")
    else:
        print("未找到 mysql 命令，使用 pymysql 导入（大文件可能较慢）")

    ok, fail = 0, 0
    for i, path in enumerate(sql_files, 1):
        print(f"[{i}/{len(sql_files)}] {path.name} …", end=" ", flush=True)
        try:
            if use_cli:
                if import_via_mysql_cli(path):
                    print("OK")
                    ok += 1
                else:
                    fail += 1
            else:
                import_via_pymysql(path)
                print("OK")
                ok += 1
        except Exception as e:
            print(f"失败: {e}")
            fail += 1

    print(f"\n导入完成: 成功 {ok}, 失败 {fail}")
    try:
        test_connection()
    except Exception as e:
        print(f"连接测试失败: {e}")
        print("请检查 .env 中的 DB_PASSWORD 是否与 MySQL root 密码一致。")
        sys.exit(1)


if __name__ == "__main__":
    main()
