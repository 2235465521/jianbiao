# -*- coding: utf-8 -*-
"""
mydate 全量标准号目录：MySQL + SQL 备份 + 目录内 Excel。
入库核验时，只要标准号出现在上述任一来源，即视为「在库内」。
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import pandas as pd
import pymysql

import _path  # noqa: F401

from db_config import DB_CONFIG, SQL_DUMP_DIR

# INSERT 元组：id, std_id, std_type, std_type_no, 时间, 中文名(可 NULL), ...
_TUPLE_RE = re.compile(
    r"\((\d+),'((?:[^'\\]|\\.)*)','((?:[^'\\]|\\.)*)','(\d{2})','[^']*',(?:'((?:[^'\\]|\\.)*)'|NULL)"
)

_STD_ID_COL_NAMES = ("标准号", "标准编号", "编号", "std_id", "标准ID")


def _norm_key(std_id: str) -> str:
    return std_id.upper().replace(" ", "")


def _clean_id(text) -> str:
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    if not str(text).strip():
        return ""
    s = " ".join(str(text).upper().strip().split())
    s = s.translate(str.maketrans("∕—＿（）－", "/---(-"))
    s = s.replace("G-B", "GB").replace("GBT", "GB/T")
    for prefix in ("GB/T", "GB/Z", "GB", "ISO/IEC", "ISO", "IEC", "DB", "TB"):
        if s.startswith(prefix) and len(s) > len(prefix) and s[len(prefix)].isdigit():
            s = prefix + " " + s[len(prefix) :]
            break
    return s


def _record(
    std_id: str,
    *,
    source: str,
    std_type: str = "",
    std_type_no: str = "",
    std_chinesename: str | None = None,
    base_id: int | None = None,
) -> dict:
    return {
        "std_id": std_id,
        "std_type": std_type,
        "std_type_no": std_type_no,
        "std_chinesename": std_chinesename,
        "std_status": None,
        "id": base_id,
        "_catalog_source": source,
    }


def _merge_into_index(index: dict, rec: dict) -> None:
    sid = rec["std_id"]
    if not sid:
        return
    keys = {sid, _norm_key(sid)}
    for k in keys:
        if k not in index:
            index[k] = rec
            continue
        old = index[k]
        # MySQL > SQL > Excel
        rank = {"mysql": 3, "sql_dump": 2, "excel": 1}
        if rank.get(rec["_catalog_source"], 0) > rank.get(old["_catalog_source"], 0):
            index[k] = rec


def _load_from_sql_dump(index: dict) -> int:
    sql_file = SQL_DUMP_DIR / "mydate_std_base.sql"
    if not sql_file.is_file():
        return 0
    text = sql_file.read_text(encoding="utf-8", errors="replace")
    n = 0
    for m in _TUPLE_RE.finditer(text):
        base_id, std_id, std_type, type_no, cname = m.groups()
        rec = _record(
            std_id,
            source="sql_dump",
            std_type=std_type,
            std_type_no=type_no,
            std_chinesename=cname or None,
            base_id=int(base_id),
        )
        _merge_into_index(index, rec)
        n += 1
    return n


def _std_ids_from_excel(path: Path) -> list[str]:
    ids: list[str] = []
    try:
        if path.suffix.lower() == ".csv":
            df = pd.read_csv(path, dtype=str)
        else:
            df = pd.read_excel(path, dtype=str)
    except Exception:
        return ids
    df.columns = [str(c).strip() for c in df.columns]
    col = next((c for c in _STD_ID_COL_NAMES if c in df.columns), None)
    if col is None:
        for c in df.columns:
            sample = df[c].dropna().astype(str).head(20)
            if sample.empty:
                continue
            if sample.str.contains(r"[A-Z]{1,5}\s*/", regex=True, na=False).any():
                col = c
                break
    if col is None and len(df.columns):
        col = df.columns[0]
    if col is None:
        return ids
    for v in df[col]:
        sid = _clean_id(v)
        if sid:
            ids.append(sid)
    return ids


def _load_from_excels(index: dict) -> tuple[int, int]:
    if not SQL_DUMP_DIR.is_dir():
        return 0, 0
    files = sorted(SQL_DUMP_DIR.rglob("*.xlsx")) + sorted(SQL_DUMP_DIR.rglob("*.xls"))
    files += sorted(SQL_DUMP_DIR.rglob("*.csv"))
    file_n = 0
    id_n = 0
    for path in files:
        if path.name.startswith("~$"):
            continue
        file_n += 1
        for sid in _std_ids_from_excel(path):
            rec = _record(sid, source="excel", std_type="", std_type_no="")
            rec["_excel_file"] = path.name
            _merge_into_index(index, rec)
            id_n += 1
    return file_n, id_n


def _load_from_mysql(index: dict) -> int:
    try:
        conn = pymysql.connect(**DB_CONFIG, cursorclass=pymysql.cursors.DictCursor)
    except Exception:
        return 0
    n = 0
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, std_id, std_type, std_type_no, std_chinesename, std_status FROM std_base"
            )
            for row in cur.fetchall():
                rec = _record(
                    row["std_id"],
                    source="mysql",
                    std_type=row.get("std_type") or "",
                    std_type_no=str(row.get("std_type_no") or ""),
                    std_chinesename=row.get("std_chinesename"),
                    base_id=row.get("id"),
                )
                rec["std_status"] = row.get("std_status")
                _merge_into_index(index, rec)
                n += 1
    finally:
        conn.close()
    return n


@lru_cache(maxsize=1)
def get_mydate_catalog() -> dict:
    """返回 {标准号或紧凑键: 目录记录}，进程内缓存。"""
    index: dict = {}
    mysql_n = _load_from_mysql(index)
    sql_n = _load_from_sql_dump(index)
    excel_files, excel_ids = _load_from_excels(index)
    index["_meta"] = {
        "mysql_rows": mysql_n,
        "sql_tuples": sql_n,
        "excel_files": excel_files,
        "excel_ids": excel_ids,
        "unique_ids": len([k for k in index if not k.startswith("_")]),
    }
    return index


def catalog_meta() -> dict:
    cat = get_mydate_catalog()
    return cat.get("_meta", {})


def lookup_in_catalog(std_id_raw: str) -> tuple[bool, str, dict | None]:
    """在 mydate 全量目录中查找（不含详情表）。"""
    qid = _clean_id(std_id_raw)
    if not qid:
        return False, "", None
    cat = get_mydate_catalog()
    rec = cat.get(qid) or cat.get(_norm_key(qid))
    if rec and not str(rec.get("std_id", "")).startswith("_"):
        return True, qid, dict(rec)
    return False, qid, None


def source_label(rec: dict) -> str:
    src = rec.get("_catalog_source", "")
    if src == "mysql":
        return "MySQL"
    if src == "sql_dump":
        return "mydate SQL 备份"
    if src == "excel":
        fn = rec.get("_excel_file", "")
        return f"Excel({fn})" if fn else "mydate Excel"
    return "mydate"
