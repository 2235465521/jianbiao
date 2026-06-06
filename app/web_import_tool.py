import os
import pymysql
import re
import hashlib
import random
import requests
import time
import uuid
import json
import streamlit as st
import pandas as pd
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import _path  # noqa: F401 — 保证可 import 根目录下的 db_config

from db_config import DB_CONFIG, PDF_ROOT, PDF_SUBDIR, SQL_DUMP_DIR
from mydate_catalog import catalog_meta, lookup_in_catalog, source_label
from pdf_resolver import (
    fetch_pdfs_for_base,
    open_pdf_local,
    pdf_status_label,
    resolve_pdf_abs_path,
)

# ==========================================
# 🚀 傻瓜式增量数据入库 Web 工具
# 使用方法: 双击根目录「启动平台.bat」，或:
#   streamlit run app/web_import_tool.py
# ==========================================

# --- 百度翻译配置 (从 translate_std_names.py 提取) ---
BAIDU_APP_ID = "20260430002604998"
BAIDU_SECRET_KEY = "MGC2o1ZfMIdl3qLmWm9t"
BAIDU_API_URL = "https://fanyi-api.baidu.com/api/trans/vip/translate"

# --- 核心清洗工具 ---
def clean_id(text):
    if pd.isna(text) or not str(text).strip(): return ""
    # 规范化空格，保留用户在 Excel 中原有的空格
    text = ' '.join(str(text).upper().strip().split())
    text = text.translate(str.maketrans('∕—＿（）－', '/---(-'))
    text = text.replace('G-B', 'GB').replace('GBT', 'GB/T')
    
    # 强制在常见前缀后补充空格（如果用户漏写了）
    for prefix in ['GB/T', 'GB/Z', 'GB', 'ISO/IEC', 'ISO', 'IEC', 'DB', 'TB']:
        if text.startswith(prefix) and len(text) > len(prefix) and text[len(prefix)].isdigit():
            text = text[:len(prefix)] + ' ' + text[len(prefix):]
            break
            
    return text


def extract_std_id_from_cell(val):
    """从单元格文本中提取标准号（去掉括号说明等后缀）。"""
    if pd.isna(val) or not str(val).strip():
        return ""
    text = str(val).strip().split("\n")[0]
    for sep in ("（", "(", "；", ";", "，", ","):
        if sep in text:
            text = text.split(sep)[0].strip()
    return clean_id(text)


# 行内出现即识别（按优先级，先匹配先生效）
_TYPE_MATCH_RULES = [
  # (type_no, type_name, 正则列表)
    ("04", "ISO", [
        r"ISO\s*/\s*IEC", r"ISO/IEC", r"ISO\.IEC",
        r"\bISO\s*\d{3,5}\b", r"\bISO\s*/\s*[A-Z0-9]",
    ]),
    ("05", "IEC", [
        r"\bIEC\s*\d{3,5}\b", r"\bIEC\s*/\s*[A-Z0-9]", r"\bIEC/TR\b", r"\bIEC\b",
    ]),
    ("00", "国标", [
        r"GB\s*/\s*T", r"GB/T", r"GB\s*/\s*Z", r"GB/Z",
        r"\bGB\s*\d", r"\bGB\s+[0-9]",
    ]),
    ("02", "地标", [
        r"\bDB\s*\d", r"\bDB\s*/\s*T", r"\bDB\s*/", r"\bDB\s+[0-9]",
        r"\bDD\s*\d", r"\bDD\s+[0-9]",
    ]),
    ("03", "团标", [
        r"\bT\s*/\s*[A-Z0-9]", r"\bT/", r"\bTB\s*/\s*T", r"\bTB/T",
    ]),
    ("01", "行标", [
        r"\bJB\s*/", r"\bYY\s*/", r"\bHG\s*/", r"\bSH\s*/", r"\bNB\s*/",
        r"\bDL\s*/", r"\bSY\s*/", r"\bMT\s*/", r"\bAQ\s*/", r"\bGA\s*/",
        r"\bJR\s*/", r"\bLY\s*/", r"\bNY\s*/", r"\bQC\s*/", r"\bSC\s*/",
    ]),
]

STD_TYPE_LABELS = {
    "00": "国标",
    "01": "行标",
    "02": "地标",
    "03": "团标",
    "04": "ISO",
    "05": "IEC",
}


def format_in_db_label(type_no, type_name=None):
    """入库核验状态文案：已入库(团标)、已入库(地标) …"""
    no = str(type_no).strip() if type_no is not None else ""
    if len(no) == 1:
        no = "0" + no
    label = STD_TYPE_LABELS.get(no) or (str(type_name).strip() if type_name else "其它")
    return f"✅ 已在库({label})"


def format_in_db_row(base: dict, payload: dict | None = None) -> str:
    """表格「是否在库」列：类型 + 数据来源。"""
    cell = format_in_db_label(base.get("std_type_no"), base.get("std_type"))
    src = source_label(base)
    if src:
        cell = f"{cell} · {src}"
    if payload and payload.get("_catalog_only"):
        cell += "（仅目录）"
    return cell


_TYPE_KEYWORD_RULES = [
    ("00", "国标", ("国标", "国家标准", "GB标准")),
    ("02", "地标", ("地标", "地方标准", "DB标准")),
    ("03", "团标", ("团标", "团体标准", "T/团标")),
    ("01", "行标", ("行标", "行业标准", "JB行标")),
    ("04", "ISO", ("ISO标准", "国际标准ISO")),
    ("05", "IEC", ("IEC标准", "国际标准IEC")),
]


def get_std_type_from_text(text):
    """在任意文本中查找标准类型标记（标准号或整行任一单元格）。"""
    if pd.isna(text) or not str(text).strip() or str(text).strip().lower() == "nan":
        return None
    raw = str(text)
    upper = raw.upper()
    compact = re.sub(r"\s+", "", upper)

    for no, name, patterns in _TYPE_MATCH_RULES:
        for pat in patterns:
            if re.search(pat, upper, re.IGNORECASE) or re.search(
                pat.replace(r"\s*", ""), compact, re.IGNORECASE
            ):
                if no == "05" and re.search(r"ISO\s*/\s*IEC|ISO/IEC|ISO\.IEC", upper):
                    continue
                return no, name

    for no, name, keywords in _TYPE_KEYWORD_RULES:
        if any(kw in raw for kw in keywords):
            return no, name

    return None


def get_std_type_no_from_std_id(std_id):
    """从标准号单元格识别类型。"""
    return get_std_type_from_text(extract_std_id_from_cell(std_id))


def get_std_type_from_row(row):
    """扫描整行所有单元格，任一位置出现类型标记即识别。"""
    parts = []
    for v in row.values:
        if pd.notna(v) and str(v).strip() and str(v).strip().lower() != "nan":
            parts.append(str(v))
    if not parts:
        return None
    return get_std_type_from_text(" | ".join(parts))


def get_std_type_no_from_category(name):
    """根据 Excel「标准类别」列文字识别（标准号无法识别时使用）。"""
    name = str(name).upper()
    if "国" in name or name.strip() == "GB":
        return "00", "国标"
    if "ISO" in name:
        return "04", "ISO"
    if "IEC" in name:
        return "05", "IEC"
    if "地" in name or "地方" in name:
        return "02", "地标"
    if "团" in name:
        return "03", "团标"
    if "行" in name or "行业" in name:
        return "01", "行标"
    return "01", str(name).strip() if name.strip() else "其它"


def resolve_std_type(std_id, raw_type_name, type_override, row=None):
    """
    分类优先级（每一行单独判断）：
    1. 标准号列中的 GB / DB / T/ / ISO / IEC / JB …
    2. 整行任意单元格出现上述标记
    3. 侧边栏强制指定（仅无法识别时）
    4. Excel「标准类别」列
    """
    from_id = get_std_type_no_from_std_id(std_id)
    if from_id:
        return from_id

    if row is not None:
        from_row = get_std_type_from_row(row)
        if from_row:
            return from_row

    if type_override != "自动检测":
        no = type_override.split("(")[1][:2]
        name = type_override.split(" ")[0]
        return no, name

    raw = str(raw_type_name).strip() if raw_type_name and str(raw_type_name) != "nan" else "未知"
    no, name = get_std_type_no_from_category(raw)
    if raw != "未知" and no == "01":
        name = raw
    return no, name


def clean_unit_name(name):
    if pd.isna(name) or not str(name).strip(): return None
    return str(name).strip()


def cell_str(row, col):
    if col not in row.index or pd.isna(row[col]):
        return None
    s = str(row[col]).strip()
    return s if s and s.lower() != "nan" else None


def yes_no_flag(row, col, kind="patent"):
    v = cell_str(row, col)
    if not v:
        return 0
    if kind == "text":
        return 1 if ("公开" in v or "查看" in v) and "不公开" not in v else 0
    return 1 if "是" in v else 0


# 入库核验展示用（中文标签）
BASE_DISPLAY_FIELDS = [
    ("std_id", "标准号"),
    ("std_type", "标准类型"),
    ("std_type_no", "类型编号"),
    ("std_chinesename", "中文名称"),
    ("std_englishname", "英文名称"),
    ("std_status", "标准状态"),
    ("release_date", "发布日期"),
    ("implement_date", "实施日期"),
    ("abolish_date", "废止日期"),
    ("ex_state", "执行状态码"),
    ("create_time", "录入时间"),
]

TB_DETAIL_DISPLAY = [
    ("ccs", "中国标准分类号"),
    ("ics", "国际标准分类号"),
    ("gbc", "国民经济分类"),
    ("drafter", "起草人"),
    ("scope", "范围"),
    ("main_tech_cont", "主要技术内容"),
    ("is_patent", "是否包含专利信息"),
    ("std_text", "标准文本"),
    ("tb_asso", "团体名称"),
    ("regi_no", "登记证号"),
    ("Issu_auth", "发证机关"),
    ("buss_scope", "业务范围"),
    ("charge_person", "法定代表人/负责人"),
    ("unit_name", "依托单位名称"),
    ("address", "通讯地址"),
]

GB_DETAIL_DISPLAY = [
    ("ccs", "CCS分类"),
    ("ics", "ICS分类"),
    ("drafter", "起草人"),
    ("report_unit", "归口单位"),
    ("sub_report_unit", "副归口单位"),
    ("implementing_unit", "执行单位"),
    ("technical_committee", "技术委员会"),
    ("department_in_charge", "主管部门"),
    ("adopt_status", "采标情况"),
    ("product_type", "产品类别"),
]

DB_DETAIL_DISPLAY = [
    ("ccs", "CCS分类"),
    ("ics", "ICS分类"),
    ("industry_type", "行业分类"),
    ("record_no", "备案号"),
    ("suggest_dept", "提出单位"),
    ("approve_dept", "批准单位"),
    ("tech_committee", "技术委员会"),
]

HB_DETAIL_DISPLAY = [
    ("ccs", "CCS分类"),
    ("ics", "ICS分类"),
    ("industry_type", "行业分类"),
    ("record_no", "备案号"),
]


def _format_field_value(key, val):
    if val is None or (isinstance(val, str) and not str(val).strip()):
        return "—"
    if key in ("is_patent", "std_text"):
        return "是" if int(val) == 1 else "否" if str(val).isdigit() else str(val)
    return str(val)


def _field_filled(val):
    if val is None:
        return False
    if isinstance(val, str) and not str(val).strip():
        return False
    return True


def _render_field_table(title, field_defs, data: dict, skip_keys=("_label", "id", "base_id")):
    with st.container(border=True):
        st.markdown(f'<p class="card-title">{title}</p>', unsafe_allow_html=True)
        rows = []
        filled = 0
        for key, label in field_defs:
            if key in skip_keys:
                continue
            val = data.get(key) if data else None
            if _field_filled(val):
                filled += 1
            rows.append({"字段": label, "内容": _format_field_value(key, val)})
        if not rows:
            st.caption("暂无数据。")
            return 0, 0
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    return filled, len(rows)


def inject_custom_css():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700&display=swap');
        html, body, [class*="css"] { font-family: 'DM Sans', 'Segoe UI', 'Microsoft YaHei', system-ui, sans-serif; }
        .block-container { padding-top: 1rem; max-width: 1180px; }

        /* 顶栏 */
        .app-hero {
            background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 52%, #0ea5e9 100%);
            border-radius: 16px; padding: 1.5rem 1.75rem; margin-bottom: 1rem;
            color: #fff; box-shadow: 0 8px 32px rgba(37, 99, 235, 0.28);
        }
        .app-hero h1 { margin: 0; font-size: 1.65rem; font-weight: 700; letter-spacing: -0.02em; color: #fff !important; }
        .app-hero p { margin: 0.4rem 0 0; opacity: 0.93; font-size: 0.92rem; color: #e0f2fe !important; }

        /* 卡片标题：跟随主题文字色，避免深色模式下发灰看不见 */
        .card-title {
            font-size: 1.05rem; font-weight: 700;
            color: var(--text-color) !important;
            margin: 0 0 0.35rem 0; letter-spacing: -0.01em;
        }

        .status-badge {
            display: inline-block; padding: 0.45rem 0.9rem; border-radius: 999px;
            font-size: 0.88rem; font-weight: 600; margin-bottom: 0.75rem;
        }
        .status-ok { background: #14532d; color: #bbf7d0; border: 1px solid #22c55e; }
        .status-warn { background: #713f12; color: #fde68a; border: 1px solid #f59e0b; }

        /* 侧边栏 */
        div[data-testid="stSidebar"] {
            background: var(--secondary-background-color);
            border-right: 1px solid rgba(148, 163, 184, 0.25);
        }
        div[data-testid="stSidebar"] .block-container { padding-top: 1.25rem; }
        div[data-testid="stSidebar"] h3 { color: var(--text-color); font-size: 1rem; }

        /* 指标卡 */
        div[data-testid="stMetric"] {
            background: var(--secondary-background-color);
            border: 1px solid rgba(148, 163, 184, 0.22);
            border-radius: 12px; padding: 0.6rem 0.8rem;
        }
        div[data-testid="stMetric"] label {
            font-size: 0.78rem !important; color: rgba(148, 163, 184, 0.95) !important;
        }
        div[data-testid="stMetric"] [data-testid="stMetricValue"] {
            font-size: 1.1rem !important; color: var(--text-color) !important;
        }

        /* 分段标签：高对比胶囊式，修复「白底白字」 */
        .stTabs [data-baseweb="tab-list"] {
            gap: 6px;
            background: rgba(15, 23, 42, 0.55);
            padding: 5px;
            border-radius: 14px;
            border: 1px solid rgba(148, 163, 184, 0.28);
            margin-bottom: 0.75rem;
        }
        .stTabs [data-baseweb="tab"] {
            height: auto !important;
            min-height: 44px;
            border-radius: 10px !important;
            padding: 0.55rem 1.35rem !important;
            font-weight: 600 !important;
            font-size: 0.95rem !important;
            color: #cbd5e1 !important;
            background: transparent !important;
        }
        .stTabs [data-baseweb="tab"]:hover {
            color: #f1f5f9 !important;
            background: rgba(51, 65, 85, 0.65) !important;
        }
        .stTabs [aria-selected="true"] {
            background: linear-gradient(135deg, #2563eb, #1d4ed8) !important;
            color: #ffffff !important;
            box-shadow: 0 2px 12px rgba(37, 99, 235, 0.45);
        }
        .stTabs [data-baseweb="tab-highlight"],
        .stTabs [data-baseweb="tab-border"] {
            display: none !important;
        }

        /* 带边框容器 */
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-color: rgba(148, 163, 184, 0.28) !important;
            border-radius: 14px !important;
            background: rgba(15, 23, 42, 0.35);
            padding: 0.25rem;
        }

        /* 单选、说明文字 */
        .stRadio label, .stRadio label p, .stRadio label span { color: var(--text-color) !important; }
        .stCaption, [data-testid="stCaptionContainer"] { color: #94a3b8 !important; }

        /* 输入框 */
        .stTextInput input, .stTextArea textarea {
            border-radius: 10px !important;
            border-color: rgba(148, 163, 184, 0.35) !important;
        }
        .stTextInput label, .stTextArea label { color: var(--text-color) !important; font-weight: 500; }

        /* 文件上传区 */
        div[data-testid="stFileUploader"] {
            border: 2px dashed rgba(148, 163, 184, 0.45);
            border-radius: 14px; padding: 0.5rem;
            background: rgba(30, 41, 59, 0.35);
        }
        div[data-testid="stFileUploader"]:hover {
            border-color: #3b82f6;
            background: rgba(37, 99, 235, 0.12);
        }
        div[data-testid="stFileUploader"] label,
        div[data-testid="stFileUploader"] small {
            color: var(--text-color) !important;
        }

        /* 主按钮 */
        .stButton > button[kind="primary"] {
            background: linear-gradient(135deg, #2563eb, #1d4ed8) !important;
            color: #fff !important;
            border: none !important;
            border-radius: 10px !important;
            font-weight: 600 !important;
            padding: 0.55rem 1.2rem !important;
            box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35) !important;
        }
        .stButton > button[kind="primary"]:hover {
            box-shadow: 0 6px 20px rgba(37, 99, 235, 0.5) !important;
            filter: brightness(1.06);
        }
        .stButton > button[kind="secondary"] {
            border-radius: 10px !important;
            color: var(--text-color) !important;
            border-color: rgba(148, 163, 184, 0.4) !important;
        }

        /* 展开面板标题 */
        .streamlit-expanderHeader {
            font-weight: 600;
            color: var(--text-color) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_page_header():
    st.markdown(
        """
        <div class="app-hero">
            <h1>标准数据极速入库平台</h1>
            <p>拖入 Excel 或 CSV · 自动分类 · 一键入库 · 入库核验</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_section(title):
    st.sidebar.markdown(f"**{title}**")


def parse_date(val):
    if pd.isna(val) or str(val).strip() == '': return None
    try:
        return pd.to_datetime(val).date()
    except:
        return None

def translate_text(q):
    """调用百度翻译 API (单条翻译)"""
    if not q or not str(q).strip(): return None
    salt = random.randint(32768, 65536)
    sign = hashlib.md5((BAIDU_APP_ID + q + str(salt) + BAIDU_SECRET_KEY).encode('utf-8')).hexdigest()
    params = {'q': q, 'from': 'zh', 'to': 'en', 'appid': BAIDU_APP_ID, 'salt': salt, 'sign': sign}
    try:
        r = requests.get(BAIDU_API_URL, params=params, timeout=5)
        res = r.json()
        if 'trans_result' in res:
            # 机器翻译统一加 "."
            return res['trans_result'][0]['dst'].strip() + "."
    except:
        pass
    return None

def generate_ped_id():
    """生成谱系家族唯一标识"""
    return "P" + str(uuid.uuid4().hex)[:8].upper()

def update_pedigree(cursor, new_base_id, new_std_id, replaced_base_ids):
    """图遍历算法：更新或创建谱系家族，并递归计算全链路 JSON"""
    if not replaced_base_ids:
        return
        
    # 1. 查找被替代标准是否已有 ped_id (判断是新建家族还是继承家族)
    existing_ped_ids = set()
    for rid in replaced_base_ids:
        cursor.execute("SELECT ped_id FROM std_pedigree WHERE base_id = %s", (rid,))
        for r in cursor.fetchall():
            existing_ped_ids.add(r[0])
            
    # 2. 决定当前的 ped_id
    if not existing_ped_ids:
        current_ped_id = generate_ped_id()
    else:
        # 家族合并：取第一个作为主 ped_id
        existing_ped_ids = list(existing_ped_ids)
        current_ped_id = existing_ped_ids[0]
        if len(existing_ped_ids) > 1:
            for old_ped in existing_ped_ids[1:]:
                cursor.execute("UPDATE std_pedigree SET ped_id = %s WHERE ped_id = %s", (current_ped_id, old_ped))
                cursor.execute("DELETE FROM std_ped_chain WHERE ped_id = %s", (old_ped,))
                
    # 3. 将新标准 A 和被替代标准纳入该家族
    cursor.execute("SELECT id FROM std_pedigree WHERE base_id = %s", (new_base_id,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO std_pedigree (base_id, std_id_latest, ped_id) VALUES (%s, %s, %s)", 
                       (new_base_id, new_std_id, current_ped_id))
    else:
        cursor.execute("UPDATE std_pedigree SET ped_id=%s, std_id_latest=%s WHERE base_id=%s", 
                       (current_ped_id, new_std_id, new_base_id))
                       
    for rid in replaced_base_ids:
        cursor.execute("SELECT id FROM std_pedigree WHERE base_id = %s", (rid,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO std_pedigree (base_id, std_id_latest, ped_id) VALUES (%s, %s, %s)", 
                           (rid, new_std_id, current_ped_id))
        else:
            cursor.execute("UPDATE std_pedigree SET ped_id=%s, std_id_latest=%s WHERE base_id=%s", 
                           (current_ped_id, new_std_id, rid))
                       
    # 统一提权：全量更新该家族所有成员的最新代表为当前的 A
    cursor.execute("UPDATE std_pedigree SET std_id_latest = %s WHERE ped_id = %s", (new_std_id, current_ped_id))
    
    # 4. 图遍历计算 (DFS)：从 A 往下疯狂递归，挖出整个家族树
    nodes_set = set()
    edges_list = []
    visited = set()
    
    def get_std_id(b_id):
        cursor.execute("SELECT std_id FROM std_base WHERE id = %s", (b_id,))
        r = cursor.fetchone()
        return r[0] if r else str(b_id)
        
    def dfs(current_b_id):
        if current_b_id in visited: return
        visited.add(current_b_id)
        curr_name = get_std_id(current_b_id)
        nodes_set.add(curr_name)
        
        # 查它的所有儿子 (被它替代的标准)
        cursor.execute("SELECT replace_id, replace_std_name FROM std_replace WHERE base_id = %s", (current_b_id,))
        for row in cursor.fetchall():
            rep_id, rep_name = row[0], row[1]
            if rep_id:
                target_name = get_std_id(rep_id)
                edges_list.append({"source": curr_name, "target": target_name})
                dfs(rep_id) # 继续递归往下挖
            else:
                # 哪怕老标准不在库里，也画一个纯文本节点作为叶子，保证图不断
                nodes_set.add(rep_name)
                edges_list.append({"source": curr_name, "target": rep_name})
                
    dfs(new_base_id)
    
    # 5. 组装 JSON 邻接表并入库
    nodes_list = list(nodes_set)
    if new_std_id in nodes_list:
        nodes_list.remove(new_std_id)
        nodes_list.insert(0, new_std_id)
    chain_json = json.dumps({"nodes": nodes_list, "edges": edges_list}, ensure_ascii=False)
    
    cursor.execute("SELECT id FROM std_ped_chain WHERE ped_id = %s", (current_ped_id,))
    if cursor.fetchone():
        cursor.execute("UPDATE std_ped_chain SET ped_chain = %s WHERE ped_id = %s", (chain_json, current_ped_id))
    else:
        cursor.execute("INSERT INTO std_ped_chain (ped_id, ped_chain) VALUES (%s, %s)", (current_ped_id, chain_json))


def _fetch_std_record(cursor, std_id):
    """按标准号查主表，兼容空格差异。"""
    cursor.execute("SELECT * FROM std_base WHERE std_id = %s", (std_id,))
    row = cursor.fetchone()
    if row:
        return row
    compact = std_id.replace(" ", "")
    cursor.execute(
        "SELECT * FROM std_base WHERE REPLACE(std_id, ' ', '') = %s", (compact,)
    )
    return cursor.fetchone()


def lookup_standard_in_db(std_id_raw):
    """
    检索标准是否在 mydate 库内（MySQL / SQL 备份 / 目录内 Excel），并尽量拉取详情。
    返回 (found: bool, query_id: str, payload: dict | None)
    """
    query_id = clean_id(std_id_raw)
    if not query_id:
        return False, "", None

    conn = pymysql.connect(**DB_CONFIG, cursorclass=pymysql.cursors.DictCursor)
    try:
        with conn.cursor() as cur:
            base = _fetch_std_record(cur, query_id)
            if not base:
                in_cat, qid, cat_rec = lookup_in_catalog(std_id_raw)
                if not in_cat:
                    return False, query_id, None
                base = dict(cat_rec)
                base_id = base.get("id")
                if not base_id:
                    return True, qid, {
                        "base": base,
                        "detail": {},
                        "draft_text": None,
                        "units": [],
                        "replaces": [],
                        "pdfs": [],
                        "_catalog_only": True,
                    }

            base_id = base["id"]
            type_no = base.get("std_type_no") or ""

            detail = {}
            detail_table = {
                "00": ("std_gb_detail", "国标详情"),
                "01": ("std_hb_detail", "行标详情"),
                "02": ("std_db_detail", "地标详情"),
                "03": ("std_tb_detail", "团标详情"),
                "04": ("std_iso_detail", "国际详情"),
                "05": ("std_iec_detail", "IEC详情"),
            }
            if type_no in detail_table:
                tbl, label = detail_table[type_no]
                cur.execute(f"SELECT * FROM {tbl} WHERE base_id = %s", (base_id,))
                detail = cur.fetchone() or {}
                detail["_label"] = label

            cur.execute(
                "SELECT draft_unit FROM std_extend_h WHERE base_id = %s LIMIT 1",
                (base_id,),
            )
            ext = cur.fetchone()
            draft_text = ext["draft_unit"] if ext else None

            cur.execute(
                """
                SELECT u.unit_name, r.role_type, r.rank_order
                FROM std_unit_relation r
                JOIN unit_dict u ON u.unit_id = r.unit_id
                WHERE r.base_id = %s
                ORDER BY r.rank_order
                """,
                (base_id,),
            )
            units = cur.fetchall()

            cur.execute(
                """
                SELECT replace_std_name, replace_type,
                       (SELECT std_id FROM std_base WHERE id = replace_id) AS linked_std_id
                FROM std_replace WHERE base_id = %s
                """,
                (base_id,),
            )
            replaces = cur.fetchall()
            pdfs = fetch_pdfs_for_base(cur, base_id)

            payload = {
                "base": base,
                "detail": detail,
                "draft_text": draft_text,
                "units": units,
                "replaces": replaces,
                "pdfs": pdfs,
            }
            if base.get("_catalog_source") and base.get("_catalog_source") != "mysql":
                payload["_catalog_only"] = False
            return True, query_id, payload
    finally:
        conn.close()


def _dataframe_with_left_ids(df):
    """id / base_id 等字段左对齐显示（避免数字列默认右对齐）。"""
    df = df.copy()
    cfg = {}
    for col in ("id", "base_id"):
        if col in df.columns:
            df[col] = df[col].map(lambda x: "" if x is None else str(x))
            cfg[col] = st.column_config.TextColumn(col, alignment="left")
    return df, cfg


def _parse_std_id_list(text):
    ids = []
    for line in str(text).splitlines():
        for part in re.split(r"[,，;；\t]", line):
            sid = clean_id(part)
            if sid and sid not in ids:
                ids.append(sid)
    return ids


def _render_pdf_panel(pdfs, key_prefix: str):
    """检索结果区：展示并打开关联 PDF。"""
    st.markdown("##### 标准 PDF")
    if not pdfs:
        st.info(
            "库中暂无该标准的 PDF 路径记录。请先将 PDF 放入网盘对应目录，再运行 "
            "`python scan_and_import_filepath.py` 建立映射。"
        )
        st.caption(f"当前检索根目录：`{PDF_ROOT}` / `{PDF_SUBDIR}`")
        return

    for i, p in enumerate(pdfs):
        rel = p.get("file_path") or ""
        fname = p.get("file_name") or os.path.basename(rel) or f"附件{i + 1}"
        abs_path = p.get("abs_path") or ""
        exists = p.get("exists")
        size_mb = ""
        if p.get("file_size"):
            size_mb = f" · {p['file_size'] / 1024 / 1024:.2f} MB"

        c1, c2, c3 = st.columns([4, 1, 1])
        with c1:
            if exists:
                st.markdown(f"**{fname}**{size_mb}")
                st.caption(abs_path)
            else:
                st.markdown(f"**{fname}**（磁盘上未找到）")
                tried = resolve_pdf_abs_path(rel)
                hint = str(tried) if tried else f"{PDF_ROOT / PDF_SUBDIR / rel}"
                st.caption(f"库内路径：{rel}\n尝试：{hint}")

        with c2:
            if exists and abs_path:
                uri = Path(abs_path).as_uri()
                st.link_button("浏览器打开", uri, help="部分浏览器可能拦截 file:// 链接")
        with c3:
            if exists and abs_path:
                if st.button("本机打开", key=f"{key_prefix}_open_{p.get('id', i)}", type="primary"):
                    ok, err = open_pdf_local(abs_path)
                    if ok:
                        st.toast("已调用系统默认程序打开 PDF")
                    else:
                        st.error(err)


def _render_lookup_result(payload, query_id, key_prefix="lookup"):
    base = payload["base"]
    detail = payload["detail"]
    type_no = base.get("std_type_no") or "?"
    type_name = base.get("std_type") or ""

    label = STD_TYPE_LABELS.get(str(type_no), type_name or "其它")
    src = source_label(base)
    st.markdown(
        f'<span class="status-badge status-ok">已在库 · {base["std_id"]} · {label} · {src}</span>',
        unsafe_allow_html=True,
    )
    if payload.get("_catalog_only") or base.get("_catalog_source") in ("sql_dump", "excel"):
        st.info(
            f"该标准号已在 **{src}** 中登记。"
            " 若需查看详情表、起草单位、PDF，请执行 `python setup_mydate_db.py` 将 mydate 目录 SQL 完整导入 MySQL。"
        )

    _render_pdf_panel(payload.get("pdfs") or [], key_prefix)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("标准号", base.get("std_id") or query_id)
    c2.metric("类型", f"{type_name} ({type_no})")
    c3.metric("状态", base.get("std_status") or "-")
    c4.metric("库内 ID", base.get("id"))

    bf, bt = _render_field_table("主表 std_base", BASE_DISPLAY_FIELDS, base)
    detail_defs = {
        "00": GB_DETAIL_DISPLAY,
        "01": HB_DETAIL_DISPLAY,
        "02": DB_DETAIL_DISPLAY,
        "03": TB_DETAIL_DISPLAY,
    }.get(str(type_no), [])

    df, dt = 0, 0
    if detail_defs and detail:
        label = detail.get("_label", "详情")
        df, dt = _render_field_table(f"详情 {label}", detail_defs, detail)
    elif detail and not detail_defs:
        extra = {k: v for k, v in detail.items() if k != "_label" and _field_filled(v)}
        if extra:
            rows = [{"字段": k, "内容": _format_field_value(k, v)} for k, v in extra.items()]
            st.markdown("##### 详情")
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    total_f, total_t = bf + df, bt + df
    if total_t:
        pct = total_f / total_t
        st.markdown("**字段完整度**")
        st.progress(pct)
        if total_f == total_t:
            st.caption(f"{total_f}/{total_t} 项已录入（100%）")
        else:
            st.caption(
                f"{total_f}/{total_t} 项已录入（{int(pct * 100)}%）· 「—」表示该字段库中为空"
            )

    if payload.get("draft_text"):
        st.markdown("##### 起草单位（原文）")
        st.write(payload["draft_text"])

    if payload.get("units"):
        st.markdown("##### 起草单位（结构化）")
        st.dataframe(pd.DataFrame(payload["units"]), use_container_width=True, hide_index=True)

    if payload.get("replaces"):
        st.markdown("##### 替代关系")
        st.dataframe(pd.DataFrame(payload["replaces"]), use_container_width=True, hide_index=True)


def render_verify_panel():
    run_verify = False
    std_ids = []
    with st.container(border=True):
        st.markdown('<p class="card-title">入库核验</p>', unsafe_allow_html=True)
        st.caption(
            "在库判定范围：**mydate 全量数据**（MySQL + `mydate` 目录下 SQL 备份 + 该目录内所有 Excel），"
            "不限于本页新导入的记录。「查询条数」= 您提交了几个标准号。"
        )

        mode = st.radio(
            "检测方式",
            ["单个标准号", "批量粘贴", "上传 Excel 批量检测"],
            horizontal=True,
            label_visibility="collapsed",
        )

        if mode == "单个标准号":
            one = st.text_input("标准编号", placeholder="例如 DB 3307/T 061-2018 或 T/NXAAS 059-2023")
            if one:
                std_ids = [clean_id(one)]
        elif mode == "批量粘贴":
            bulk = st.text_area(
                "每行一个标准号（也支持逗号分隔）",
                height=120,
                placeholder="DB 3307/T 061-2018\nDB 3307/T 102-2019",
            )
            std_ids = _parse_std_id_list(bulk)
        else:
            vf = st.file_uploader("上传 Excel / CSV", type=["xlsx", "xls", "csv"], key="verify_file")
            if vf is not None:
                if vf.name.endswith(".csv"):
                    vdf = pd.read_csv(vf)
                else:
                    vdf = pd.read_excel(vf)
                vdf.columns = [str(c).strip() for c in vdf.columns]
                col = next(
                    (c for c in ("标准号", "标准编号", "编号") if c in vdf.columns),
                    vdf.columns[0],
                )
                std_ids = [clean_id(x) for x in vdf[col] if clean_id(x)]

        run_verify = st.button("开始检测", type="primary", use_container_width=True, key="verify_run")

    if run_verify:
        if not std_ids:
            st.warning("请先输入或上传至少一个标准号。")
            return

        rows = []
        for sid in std_ids:
            found, qid, payload = lookup_standard_in_db(sid)
            if not found:
                rows.append(
                    {
                        "查询标准号": qid or sid,
                        "是否在库": "❌ 不在 mydate 目录",
                        "数据来源": "",
                        "库中标准号": "",
                        "类型": "",
                        "状态": "",
                        "中文名称": "",
                        "PDF": "",
                    }
                )
            else:
                b = payload["base"]
                pdfs = payload.get("pdfs") or []
                rows.append(
                    {
                        "查询标准号": qid,
                        "是否在库": format_in_db_row(b, payload),
                        "数据来源": source_label(b),
                        "库中标准号": b.get("std_id"),
                        "类型": f"{b.get('std_type')} ({b.get('std_type_no')})",
                        "状态": b.get("std_status") or "—",
                        "中文名称": (b.get("std_chinesename") or "")[:40],
                        "PDF": pdf_status_label(pdfs) if pdfs else "—",
                    }
                )

        rdf = pd.DataFrame(rows)
        found_n = sum(1 for r in rows if r["是否在库"].startswith("✅"))
        miss_n = sum(1 for r in rows if r["是否在库"].startswith("❌"))
        st.markdown("#### 检测结果")
        if found_n == len(rows):
            st.success(f"共查询 {len(rows)} 条，均在 mydate 目录范围内。")
        elif found_n == 0:
            st.warning(
                f"共查询 {len(rows)} 条，均不在 mydate（SQL 备份 / Excel / MySQL）中。"
                " 请核对标准号写法，或将 Excel 放入 mydate 目录后刷新页面。"
            )
        else:
            st.info(f"共查询 {len(rows)} 条：{found_n} 条在库，{miss_n} 条不在 mydate 目录。")
        c1, c2, c3 = st.columns(3)
        c1.metric("查询条数", len(rows), help="本次提交检测的标准号数量")
        c2.metric("在库", found_n, help="在 mydate SQL / Excel / MySQL 任一来源中存在")
        c3.metric("不在目录", miss_n, help="mydate 全部来源中均无此标准号")

        with st.container(border=True):
            st.dataframe(rdf, use_container_width=True, hide_index=True)

        if len(std_ids) == 1:
            found, qid, payload = lookup_standard_in_db(std_ids[0])
            if found:
                st.markdown("#### 完整记录")
                _render_lookup_result(payload, qid, key_prefix=f"single_{qid}")
            else:
                st.error(
                    f"标准号 **{qid}** 不在 mydate 目录（SQL 备份、Excel、MySQL）中。"
                    " 请核对写法，或将含该号的 Excel 放入 mydate 文件夹。"
                )
        else:
            st.markdown("#### 逐条详情")
            for sid in std_ids:
                found, qid, payload = lookup_standard_in_db(sid)
                label = f"{qid} — {'已入库' if found else '未找到'}"
                with st.expander(label, expanded=False):
                    if found:
                        _render_lookup_result(payload, qid, key_prefix=f"bulk_{qid}")
                    else:
                        st.error("未在 std_base 中找到该标准号。")


# --- UI 页面配置 ---
st.set_page_config(
    page_title="标准数据极速入库平台",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_custom_css()
render_page_header()

# --- 侧边栏 ---
with st.sidebar:
    st.markdown("### 控制台")
    render_sidebar_section("自动化")
auto_translate = st.sidebar.checkbox(
    "自动翻译缺失的英文名",
    value=True,
    help="未提供英文名时调用百度翻译（末尾补点）",
)

st.sidebar.markdown("---")
render_sidebar_section("数据库")
try:
    _test_conn = pymysql.connect(**DB_CONFIG)
    _test_conn.close()
    st.sidebar.success(f"已连接 `{DB_CONFIG['database']}`")
    try:
        _meta = catalog_meta()
        st.sidebar.caption(
            f"核验目录：SQL 约 {_meta.get('sql_tuples', 0):,} 条 · "
            f"MySQL {_meta.get('mysql_rows', 0):,} 条 · "
            f"Excel {_meta.get('excel_files', 0)} 个文件"
        )
    except Exception:
        pass
except Exception as _db_err:
    st.sidebar.error("未连接数据库")
    st.sidebar.caption(str(_db_err)[:120])
    st.sidebar.info(
        f"请先在命令行执行一次：\n`python setup_mydate_db.py`\n\n"
        f"将 `{SQL_DUMP_DIR}` 下的 SQL 导入 MySQL。"
    )

st.sidebar.markdown("---")
render_sidebar_section("安全模式")
dry_run = st.sidebar.checkbox(
    "模拟导入 (Dry Run)",
    value=False,
    help="仅校验不写库，适合试跑",
)

st.sidebar.markdown("---")
render_sidebar_section("类型指定")
type_override = st.sidebar.selectbox(
    "强制指定标准类型",
    ["自动检测", "国标 (00)", "行标 (01)", "地标 (02)", "团标 (03)", "ISO (04)", "IEC (05)"],
    index=0,
    help="默认自动按行内标准号识别类型；无法识别时可手动指定。",
)

st.sidebar.markdown("---")
render_sidebar_section("PDF 目录")
st.sidebar.caption(f"根目录: `{PDF_ROOT}`")
st.sidebar.caption(f"子目录: `{PDF_SUBDIR or '（无）'}`")
st.sidebar.markdown("---")
render_sidebar_section("快速检测")
sidebar_std = st.sidebar.text_input(
    "输入标准号",
    placeholder="DB 3307/T 061-2018",
    key="sidebar_verify_std",
)
if st.sidebar.button("检测是否已入库", use_container_width=True, key="sidebar_verify_btn"):
    if not sidebar_std or not clean_id(sidebar_std):
        st.sidebar.warning("请输入有效标准号")
    else:
        found, qid, payload = lookup_standard_in_db(sidebar_std)
        if not found:
            st.sidebar.error(f"未找到\n{qid}")
        else:
            b = payload["base"]
            st.sidebar.success(format_in_db_label(b.get("std_type_no"), b.get("std_type")))
            st.sidebar.caption(f"{b.get('std_chinesename', '')[:20]}…")
            st.sidebar.caption(f"状态: {b.get('std_status')}")
            pdfs = [p for p in (payload.get("pdfs") or []) if p.get("exists")]
            if pdfs:
                p0 = pdfs[0]
                if st.sidebar.button("打开 PDF", use_container_width=True, key="sidebar_open_pdf"):
                    ok, err = open_pdf_local(p0["abs_path"])
                    if ok:
                        st.sidebar.toast("已打开 PDF")
                    else:
                        st.sidebar.error(err[:80])
            else:
                st.sidebar.caption(f"PDF: {pdf_status_label(payload.get('pdfs') or [])}")

tab_import, tab_verify = st.tabs(["数据导入", "入库核验"])

with tab_verify:
    render_verify_panel()

with tab_import:
    with st.container(border=True):
        st.markdown('<p class="card-title">上传数据文件</p>', unsafe_allow_html=True)
        st.caption("支持 Excel (.xlsx / .xls) 与 CSV")
        uploaded_file = st.file_uploader(
            "选择或拖入文件",
            type=["xlsx", "xls", "csv"],
            label_visibility="collapsed",
        )

    if uploaded_file is not None:
        try:
            with st.spinner("正在解析数据文件..."):
                if uploaded_file.name.endswith('.csv'):
                    df = pd.read_csv(uploaded_file)
                else:
                    df = pd.read_excel(uploaded_file)

            # 清洗表头
            df.columns = [str(c).strip() for c in df.columns]

            c1, c2 = st.columns([1, 3])
            c1.metric("数据行数", len(df))
            c2.success(f"已读取：**{uploaded_file.name}**")

            with st.expander("预览前 5 行", expanded=False):
                st.dataframe(df.head(), use_container_width=True, hide_index=True)
            
            # --- 智能字段映射逻辑 (别名纠错) ---
            column_mapping = {
                '标准号': ['标准号', '标准编号', '编号', 'NO', '标准', 'A 标准号'],
                '标准类别': ['标准类别', '类型', '标准类型', 'G 标准类别'],
                '状态': ['状态', '标准状态', '执行状态', '状态标识', 'D 标准状态'],
                '中文名称': ['中文名称', '标准名称', '名称', '中文名', 'B 标准中文名称', '中文标题'],
                '英文名称': ['英文名称', '标准英文名称', '英文名', 'C 标准英文名称', '英文标题'],
                '发布日期': ['发布日期', '发布时间', '日期', 'E 发布日期'],
                '实施日期': ['实施日期', '实施时间', 'F 实施日期'],
                '起草单位': ['起草单位', '起草机构', '单位', 'R 起草单位'],
                '替代标准': ['替代标准', '代替标准', '被替代标准', 'J 替代标准号', '替代标准号'],
                'CCS分类': ['CCS分类', '中国标准分类号', 'CCS', 'H 中国标准分类号', '中国标准分类'],
                'ICS分类': ['ICS分类', '国际标准分类号', 'ICS', 'I 国际标准分类号', '标准分类号'],
                '国民经济分类': ['国民经济分类', 'GBC', '经济分类', '国民经济行业分类', '国民经济行业'],
                '归口单位': ['归口单位/部门', '归口单位', '归口部门', 'L 归口单位/部门'],
                '执行单位': ['执行单位', 'M 执行单位'],
                '副归口单位': ['副归口单位', 'N 副归口单位'],
                '技术委员会': ['技术委员会', 'O 技术委员会'],
                '主管部门': ['主管部门', 'P 主管部门'],
                '采标情况': ['采标情况', 'Q 采标情况'],
                '起草人': ['起草人', 'S 起草人'],
                '产品类别': ['产品类别', 'T 产品类别'],
                '代替类型': ['代替类型', 'K 代替类型'],
                '范围': ['范围'],
                '主要技术内容': ['主要技术内容', '主要技术'],
                '是否包含专利信息': ['是否包含专利信息', '专利信息'],
                '标准文本': ['标准文本'],
                '团体名称': ['团体名称', '团体'],
                '登记证号': ['登记证号'],
                '发证机关': ['发证机关'],
                '业务范围': ['业务范围'],
                '法定代表人': ['法定代表人/负责人', '法定代表人', '负责人'],
                '依托单位名称': ['依托单位名称', '依托单位'],
                '通讯地址': ['通讯地址'],
                # --- 以下为行标、地标、团标及国际标准特有字段映射 ---
                '行业分类': ['行业分类', '行业', '所属行业', '行业类别'],
                '备案号': ['备案号', '备案编号', '备案'],
                '提出单位': ['提出单位', '提出机构', '提出部门'],
                '批准单位': ['批准单位', '批准机构', '批准部门'],
                '版本': ['版本', 'Edition', 'Version'],
                '发布组织': ['发布组织', '组织', 'Publisher', 'Organization', '发布机构']
            }
        
            # 自动校正 DataFrame 列名
            for target, aliases in column_mapping.items():
                for alias in aliases:
                    # 如果 DataFrame 里有别名，且目标名还没被占领，就改名
                    if alias in df.columns and target not in df.columns:
                        df.rename(columns={alias: target}, inplace=True)
        
            # 再次清洗：去掉重名可能产生的 (1) 后缀或空格
            df.columns = [str(c).split('.')[0].strip() for c in df.columns]

            # 字段校验（标准类别可无：团标等按 T/、DB、GB 等标准号前缀自动识别）
            required_cols = ['标准号', '状态']
            missing_cols = [col for col in required_cols if col not in df.columns]

            if missing_cols:
                st.error(f"❌ 校验失败！缺失必填列：{', '.join(missing_cols)}。请检查表头名。")
                st.info(f"💡 系统当前检测到的列有：{', '.join(df.columns.tolist())}")
                st.stop()

            if '标准类别' not in df.columns:
                df['标准类别'] = ''
            
            # --- 执行导入按钮 ---
            if st.button("确认入库", type="primary", use_container_width=True):
                progress_bar = st.progress(0)
                status_text = st.empty()
            
                try:
                    conn = pymysql.connect(**DB_CONFIG)
                    cursor = conn.cursor()
                
                    status_text.info("正在加载系统级防重防漏索引，请稍候...")
                
                    # 预加载现有字典
                    cursor.execute("SELECT std_id, id FROM std_base")
                    id_map = {clean_id(row[0]): row[1] for row in cursor.fetchall()}
                
                    cursor.execute("SELECT unit_name, unit_id FROM unit_dict")
                    unit_map = {row[0]: row[1] for row in cursor.fetchall()}
                
                    success_count = 0
                    update_count = 0
                    error_count = 0
                    total_rows = len(df)
                
                    # 字典映射
                    state_dict = {'废止': 0, '现行': 1, '即将实施': 2, '规行': 1}
                    status_text_map = {0: '废止', 1: '现行', 2: '即将实施'}
                
                    # 开始循环写入
                    for index, row in df.iterrows():
                        # 更新进度 UI
                        if index % 20 == 0 or index == total_rows - 1:
                            progress_bar.progress(min(1.0, (index + 1) / total_rows))
                            status_text.text(f"正在全速入库：处理第 {index+1}/{total_rows} 条...")
                    
                        try:
                            std_id = extract_std_id_from_cell(row['标准号'])
                            if not std_id:
                                error_count += 1
                                continue
                            
                            # 提取业务字段
                            raw_type_name = str(row['标准类别']).strip() if '标准类别' in df.columns and pd.notna(row['标准类别']) else "未知"
                        
                            # 类型决策：行内标记(GB/DB/T/ISO…) > 侧边栏 >「标准类别」列
                            std_type_no, std_type_name = resolve_std_type(
                                std_id, raw_type_name, type_override, row=row
                            )
                            # 国标专用表头兜底（有归口单位列且未能识别时）
                            if (
                                type_override == "自动检测"
                                and std_type_no in ("01", "99")
                                and "归口单位" in df.columns
                                and not get_std_type_from_text(std_id)
                                and not get_std_type_from_row(row)
                            ):
                                std_type_no, std_type_name = "00", "国标"
                            
                            ex_state = state_dict.get(str(row['状态']).strip())
                            std_status_text = status_text_map.get(ex_state)
                        
                            ch_name = str(row['中文名称']).strip() if '中文名称' in df.columns and pd.notna(row['中文名称']) else None
                            en_name = str(row['英文名称']).strip() if '英文名称' in df.columns and pd.notna(row['英文名称']) else None
                        
                            # 如果开启了自动翻译且英文名为空 (国际标准屏蔽机器翻译)
                            if auto_translate and ch_name and (not en_name or en_name == 'nan') and std_type_no not in ['04', '05']:
                                en_name = translate_text(ch_name)
                                # 遵循频率限制 (百度标准版 1s/次)
                                time.sleep(1.0)
                            elif en_name and not en_name.endswith('.'):
                                # 手动填写的英文名如果不带点，也补上（可选逻辑，根据手册决定）
                                # en_name += "." 
                                pass
                            
                            r_date = parse_date(row.get('发布日期'))
                            i_date = parse_date(row.get('实施日期'))
                        
                            # 覆盖更新逻辑 vs 新增逻辑
                            if std_id in id_map:
                                base_id = id_map[std_id]
                                # 1. 更新主表
                                try:
                                    cursor.execute("""
                                        UPDATE std_base 
                                        SET std_id=%s, std_type=%s, std_type_no=%s, std_chinesename=%s, std_englishname=%s, release_date=%s, implement_date=%s, ex_state=%s, std_status=%s
                                        WHERE id=%s
                                    """, (std_id, std_type_name, std_type_no, ch_name, en_name, r_date, i_date, ex_state, std_status_text, base_id))
                                except pymysql.err.IntegrityError as e:
                                    if e.args[0] == 1062:
                                        # 幽灵数据冲突：数据库中同时存在带空格和不带空格的记录
                                        cursor.execute("SELECT id FROM std_base WHERE std_id = %s", (std_id,))
                                        real_base_id = cursor.fetchone()[0]
                                        # 删除旧的幽灵数据
                                        cursor.execute("DELETE FROM std_base WHERE id=%s", (base_id,))
                                        # 切换到真正的 base_id
                                        base_id = real_base_id
                                        # 重新更新正确的数据
                                        cursor.execute("""
                                            UPDATE std_base 
                                            SET std_type=%s, std_type_no=%s, std_chinesename=%s, std_englishname=%s, release_date=%s, implement_date=%s, ex_state=%s, std_status=%s
                                            WHERE id=%s
                                        """, (std_type_name, std_type_no, ch_name, en_name, r_date, i_date, ex_state, std_status_text, base_id))
                                    else:
                                        raise
                            
                                # 2. 清理旧的子表数据（为重新插入做准备）
                                cursor.execute("DELETE FROM std_gb_detail WHERE base_id=%s", (base_id,))
                                cursor.execute("DELETE FROM std_hb_detail WHERE base_id=%s", (base_id,))
                                cursor.execute("DELETE FROM std_db_detail WHERE base_id=%s", (base_id,))
                                cursor.execute("DELETE FROM std_tb_detail WHERE base_id=%s", (base_id,))
                                cursor.execute("DELETE FROM std_iso_detail WHERE base_id=%s", (base_id,))
                                cursor.execute("DELETE FROM std_unit_relation WHERE base_id=%s", (base_id,))
                                cursor.execute("DELETE FROM std_extend_h WHERE base_id=%s", (base_id,))
                                cursor.execute("DELETE FROM std_replace WHERE base_id=%s", (base_id,))
                                update_count += 1
                            else:
                                # 1. 写入主表
                                cursor.execute("""
                                    INSERT IGNORE INTO std_base 
                                    (std_id, std_type, std_type_no, std_chinesename, std_englishname, release_date, implement_date, ex_state, std_status)
                                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                                """, (std_id, std_type_name, std_type_no, ch_name, en_name, r_date, i_date, ex_state, std_status_text))
                            
                                if cursor.rowcount == 0:
                                    error_count += 1
                                    continue
                                
                                base_id = cursor.lastrowid
                                id_map[std_id] = base_id # 更新内存索引
                                success_count += 1
                        
                            # ============ 共有逻辑：向详情表插入数据 ============
                            # 提取通用详情字段
                            ccs_val = str(row['CCS分类']).strip() if 'CCS分类' in df.columns and pd.notna(row['CCS分类']) else None
                            ics_val = str(row['ICS分类']).strip() if 'ICS分类' in df.columns and pd.notna(row['ICS分类']) else None
                        
                            # 2. 详情分表路由 (补齐全部表和字段)
                            if std_type_no == '00': # 国标
                                report_unit = str(row['归口单位']).strip() if '归口单位' in df.columns and pd.notna(row['归口单位']) else None
                                sub_report_unit = str(row['副归口单位']).strip() if '副归口单位' in df.columns and pd.notna(row['副归口单位']) else None
                                implementing_unit = str(row['执行单位']).strip() if '执行单位' in df.columns and pd.notna(row['执行单位']) else None
                                tech_comm = str(row['技术委员会']).strip() if '技术委员会' in df.columns and pd.notna(row['技术委员会']) else None
                                dept_charge = str(row['主管部门']).strip() if '主管部门' in df.columns and pd.notna(row['主管部门']) else None
                                adopt_status = str(row['采标情况']).strip() if '采标情况' in df.columns and pd.notna(row['采标情况']) else None
                                product_type = str(row['产品类别']).strip() if '产品类别' in df.columns and pd.notna(row['产品类别']) else None
                                drafter = str(row['起草人']).strip() if '起草人' in df.columns and pd.notna(row['起草人']) else None
                            
                                cursor.execute("""
                                    INSERT IGNORE INTO std_gb_detail 
                                    (base_id, ccs, ics, report_unit, sub_report_unit, implementing_unit, technical_committee, department_in_charge, adopt_status, product_type, drafter) 
                                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                                """, (base_id, ccs_val, ics_val, report_unit, sub_report_unit, implementing_unit, tech_comm, dept_charge, adopt_status, product_type, drafter))
                            elif std_type_no == '01': # 行标
                                industry = str(row['行业分类']).strip() if '行业分类' in df.columns and pd.notna(row['行业分类']) else None
                                record = str(row['备案号']).strip() if '备案号' in df.columns and pd.notna(row['备案号']) else None
                                cursor.execute("INSERT IGNORE INTO std_hb_detail (base_id, ccs, ics, industry_type, record_no) VALUES (%s, %s, %s, %s, %s)", (base_id, ccs_val, ics_val, industry, record))
                            elif std_type_no == '02': # 地标
                                suggest = str(row['提出单位']).strip() if '提出单位' in df.columns and pd.notna(row['提出单位']) else None
                                approve = str(row['批准单位']).strip() if '批准单位' in df.columns and pd.notna(row['批准单位']) else None
                                cursor.execute("INSERT IGNORE INTO std_db_detail (base_id, ccs, ics, suggest_dept, approve_dept) VALUES (%s, %s, %s, %s, %s)", (base_id, ccs_val, ics_val, suggest, approve))
                            elif std_type_no == '03': # 团标（完整字段）
                                cursor.execute(
                                    """
                                    INSERT IGNORE INTO std_tb_detail (
                                        base_id, ccs, ics, gbc, drafter, scope, main_tech_cont,
                                        is_patent, std_text, tb_asso, regi_no, Issu_auth,
                                        buss_scope, charge_person, unit_name, address
                                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                                    """,
                                    (
                                        base_id, ccs_val, ics_val,
                                        cell_str(row, "国民经济分类"),
                                        cell_str(row, "起草人"),
                                        cell_str(row, "范围"),
                                        cell_str(row, "主要技术内容"),
                                        yes_no_flag(row, "是否包含专利信息", "patent"),
                                        yes_no_flag(row, "标准文本", "text"),
                                        cell_str(row, "团体名称"),
                                        cell_str(row, "登记证号"),
                                        cell_str(row, "发证机关"),
                                        cell_str(row, "业务范围"),
                                        cell_str(row, "法定代表人"),
                                        cell_str(row, "依托单位名称"),
                                        cell_str(row, "通讯地址"),
                                    ),
                                )
                            elif std_type_no == '04': # 国际 (ISO等)
                                version = str(row['版本']).strip() if '版本' in df.columns and pd.notna(row['版本']) else None
                                org = str(row['发布组织']).strip() if '发布组织' in df.columns and pd.notna(row['发布组织']) else None
                                cursor.execute("INSERT IGNORE INTO std_iso_detail (base_id, std_varsion, std_rele_issue) VALUES (%s, %s, %s)", (base_id, version, org))
                        
                            # 3. 剥离并写入单位关系
                            units_str = str(row['起草单位']) if '起草单位' in df.columns and pd.notna(row['起草单位']) else None
                            if units_str:
                                # 疑问1解答：写入历史冗余表 std_extend_h 以兼容老前端
                                cursor.execute("INSERT IGNORE INTO std_extend_h (base_id, std_type, draft_unit) VALUES (%s, %s, %s)", (base_id, std_type_name, units_str))
                            
                                # 继续拆分进入现代字典库 (仅标点分割，保留空格)
                                units = re.split(r'[，,；;、]', units_str)
                                for rank, u in enumerate(units):
                                    uname = clean_unit_name(u)
                                    if uname:
                                        uid = unit_map.get(uname)
                                        if not uid:
                                            # 新单位落地
                                            cursor.execute("INSERT IGNORE INTO unit_dict (unit_name) VALUES (%s)", (uname,))
                                            cursor.execute("SELECT unit_id FROM unit_dict WHERE unit_name = %s", (uname,))
                                            res = cursor.fetchone()
                                            if res:
                                                uid = res[0]
                                                unit_map[uname] = uid
                                        if uid:
                                            # 写入关系
                                            cursor.execute("INSERT IGNORE INTO std_unit_relation (base_id, unit_id, role_type, rank_order) VALUES (%s, %s, %s, %s)", 
                                                           (base_id, uid, 1 if rank==0 else 2, rank+1))
                        
                            # 4. 追踪替代关系并构建谱系树 (方案一核心)
                            replace_str = str(row['替代标准']).strip() if '替代标准' in df.columns and pd.notna(row['替代标准']) else None
                            replace_type = str(row['代替类型']).strip() if '代替类型' in df.columns and pd.notna(row['代替类型']) else None
                            if replace_str:
                                # 仅用标点分割，防止带空格标准号被切断
                                reps = re.split(r'[，,；;、]', replace_str)
                                replaced_ids = []
                                for rep in reps:
                                    rep = str(rep).strip()
                                    if not rep: continue
                                    clean_rep = clean_id(rep)
                                    rep_id = id_map.get(clean_rep)
                                    cursor.execute("INSERT IGNORE INTO std_replace (base_id, replace_id, replace_std_name, replace_type) VALUES (%s, %s, %s, %s)", 
                                                   (base_id, rep_id, rep, replace_type))
                                    if rep_id:
                                        replaced_ids.append(rep_id)
                                    
                                # 调用 DFS 算法当场计算并生成 JSON 拓扑图
                                if replaced_ids:
                                    update_pedigree(cursor, base_id, std_id, replaced_ids)
                                
                                    # 即时状态级联：新标准现行时，被替代的旧标准作废
                                    if ex_state == 1:
                                        format_strings = ','.join(['%s'] * len(replaced_ids))
                                        cursor.execute(f"UPDATE std_base SET ex_state = 0 WHERE id IN ({format_strings})", tuple(replaced_ids))

                            
                            # 由于 success_count 等计数已经在前面更新了，此处不再需要 +1
                            # 批量提交保护 (非模拟导入模式下)
                            if not dry_run and success_count % 500 == 0:
                                conn.commit()
                            
                        except Exception as row_e:
                            error_count += 1
                            st.error(f"❌ 第 {index+2} 行处理失败 (标准号: {row.get('标准号')}): {str(row_e)}")
                
                    # 最终事务提交
                    if not dry_run:
                        conn.commit()
                        st.balloons()
                        st.success(f"🎉 任务圆满结束！数据已正式入库。")
                    else:
                        conn.rollback() # 模拟模式下必须回滚
                        st.warning(f"🧪 模拟导入完成！已解析 {success_count + update_count} 条数据，数据库未做任何更改。")
                
                    col1, col2, col3 = st.columns(3)
                    col1.metric("✨ 成功新增 (条数)", success_count)
                    col2.metric("🔄 查重覆盖 (更新老数据)", update_count)
                    col3.metric("⚠️ 异常丢弃 (数据损坏)", error_count)
                
                    if update_count > 0:
                        st.info("💡 覆盖机制生效：系统检测到库中已有相同的标准号，已使用 Excel 中的最新数据全面覆盖更新！")
                
                except Exception as e:
                    if 'conn' in locals(): conn.rollback()
                    st.error(f"💣 严重错误：数据库连接异常或系统故障 ({str(e)})")
                finally:
                    if 'cursor' in locals(): cursor.close()
                    if 'conn' in locals(): conn.close()
                
        except Exception as e:
            st.error(f"❌ 无法解析该文件，请确保它是一个合法的 Excel 或 CSV 文件。报错详情：{str(e)}")
