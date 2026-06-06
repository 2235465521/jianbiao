# -*- coding: utf-8 -*-
"""根据 std_filepath 记录解析 PDF 绝对路径，并支持本机打开。"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import _path  # noqa: F401

from db_config import PDF_ROOT, PDF_SUBDIR


def _normalize_rel_path(file_path: str) -> str:
    return file_path.replace("\\", "/").lstrip("/")


def candidate_abs_paths(file_path: str) -> list[Path]:
    """
    将库中相对路径解析为若干候选绝对路径（按优先级）。
    兼容历史扫描脚本：相对路径相对于「PDF_ROOT/PDF_SUBDIR」。
    """
    if not file_path or not str(file_path).strip():
        return []

    raw = str(file_path).strip()
    if len(raw) >= 2 and raw[1] == ":":
        return [Path(raw)]

    rel = _normalize_rel_path(raw)
    rel_parts = Path(rel)

    candidates: list[Path] = []
    if PDF_SUBDIR:
        candidates.append(PDF_ROOT / PDF_SUBDIR / rel_parts)
    candidates.append(PDF_ROOT / rel_parts)
    if PDF_SUBDIR:
        candidates.append(PDF_ROOT / PDF_SUBDIR / rel)
        candidates.append(PDF_ROOT / rel)

    # 去重且保持顺序
    seen: set[str] = set()
    unique: list[Path] = []
    for p in candidates:
        key = str(p).lower()
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def resolve_pdf_abs_path(file_path: str) -> Path | None:
    """返回第一个在磁盘上存在的 PDF 绝对路径。"""
    for p in candidate_abs_paths(file_path):
        if p.is_file():
            return p
    return None


def enrich_filepath_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """为 std_filepath 查询结果补充 abs_path、exists。"""
    out = []
    for row in rows:
        rel = row.get("file_path") or ""
        abs_path = resolve_pdf_abs_path(rel)
        out.append(
            {
                **row,
                "abs_path": str(abs_path) if abs_path else "",
                "exists": bool(abs_path),
            }
        )
    return out


def fetch_pdfs_for_base(cursor, base_id: int) -> list[dict[str, Any]]:
    cursor.execute(
        """
        SELECT id, base_id, file_path, file_name, file_size
        FROM std_filepath
        WHERE base_id = %s
        ORDER BY id
        """,
        (base_id,),
    )
    return enrich_filepath_rows(list(cursor.fetchall()))


def open_pdf_local(abs_path: str) -> tuple[bool, str]:
    """在本机用默认程序打开 PDF（Windows 优先 os.startfile）。"""
    p = Path(abs_path)
    if not p.is_file():
        return False, f"文件不存在: {abs_path}"

    try:
        if sys.platform == "win32":
            os.startfile(str(p))  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.run(["open", str(p)], check=True)
        else:
            subprocess.run(["xdg-open", str(p)], check=True)
        return True, ""
    except Exception as e:
        return False, str(e)


def pdf_status_label(pdfs: list[dict[str, Any]]) -> str:
    if not pdfs:
        return "无路径记录"
    ok = [p for p in pdfs if p.get("exists")]
    if ok:
        return f"有 PDF（{len(ok)}）"
    return "有记录但文件未找到"
