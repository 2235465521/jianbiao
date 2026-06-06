# -*- coding: utf-8 -*-
import pandas as pd
import sys
sys.stdout.reconfigure(encoding='utf-8')

path = r'c:\Users\20711\Desktop\地标.xlsx'
df = pd.read_excel(path, sheet_name=0)
print('行数:', len(df))
print('原始列名:')
for i, c in enumerate(df.columns):
    print(f'  {i}: {c}')

column_mapping = {
    '标准号': ['标准号', '标准编号', '编号', 'NO', '标准', 'A 标准号'],
    '标准类别': ['标准类别', '类型', '标准类型', 'G 标准类别'],
    '状态': ['状态', '标准状态', '执行状态', '状态标识', 'D 标准状态'],
    '中文名称': ['中文名称', '标准名称', '名称', '中文名', 'B 标准中文名称'],
    '英文名称': ['英文名称', '标准英文名称', '英文名', 'C 标准英文名称'],
    '发布日期': ['发布日期', '发布时间', '日期', 'E 发布日期'],
    '实施日期': ['实施日期', '实施时间', 'F 实施日期'],
    '起草单位': ['起草单位', '起草机构', '单位', 'R 起草单位'],
    '替代标准': ['替代标准', '代替标准', '被替代标准', 'J 替代标准号', '替代标准号'],
    'CCS分类': ['CCS分类', '中国标准分类号', 'CCS', 'H 中国标准分类号'],
    'ICS分类': ['ICS分类', '国际标准分类号', 'ICS', 'I 国际标准分类号'],
    '归口单位': ['归口单位/部门', '归口单位', '归口部门', 'L 归口单位/部门'],
    '执行单位': ['执行单位', 'M 执行单位'],
    '副归口单位': ['副归口单位', 'N 副归口单位'],
    '技术委员会': ['技术委员会', 'O 技术委员会'],
    '主管部门': ['主管部门', 'P 主管部门'],
    '采标情况': ['采标情况', 'Q 采标情况'],
    '起草人': ['起草人', 'S 起草人'],
    '产品类别': ['产品类别', 'T 产品类别'],
    '代替类型': ['代替类型', 'K 代替类型'],
    '行业分类': ['行业分类', '行业', '所属行业', '行业类别'],
    '备案号': ['备案号', '备案编号', '备案'],
    '提出单位': ['提出单位', '提出机构', '提出部门'],
    '批准单位': ['批准单位', '批准机构', '批准部门'],
    '国民经济分类': ['国民经济分类', 'GBC', '经济分类', '国民经济行业分类'],
    '版本': ['版本', 'Edition', 'Version'],
    '发布组织': ['发布组织', '组织', 'Publisher', 'Organization', '发布机构'],
}

df2 = df.copy()
df2.columns = [str(c).split('.')[0].strip() for c in df2.columns]
rename_log = []
for target, aliases in column_mapping.items():
    for alias in aliases:
        if alias in df2.columns and target not in df2.columns:
            df2.rename(columns={alias: target}, inplace=True)
            rename_log.append((alias, target))

print('\n列名映射结果:')
for a, t in rename_log:
    print(f'  {a} -> {t}')

print('\n映射后全部列名:', list(df2.columns))
required = ['标准号', '标准类别', '状态']
print('\n必填校验:', {c: c in df2.columns for c in required})
missing = [c for c in required if c not in df2.columns]
if missing:
    print('会拦截无法导入:', missing)

mapped_targets = set(column_mapping.keys())
unmapped = [c for c in df2.columns if c not in mapped_targets]
print('\n无法映射、程序不会读取的列:')
for c in unmapped:
    val = df2[c].iloc[0] if len(df2) else ''
    print(f'  - {c} | 样例: {val}')

# 地标分支会用的列
db_cols = ['CCS分类', 'ICS分类', '提出单位', '批准单位']
print('\n地标详情分支实际会尝试读取:')
for c in db_cols:
    print(f'  {c}:', '有' if c in df2.columns else '无')

# 有映射但地标分支不写的
hb_only = ['行业分类', '备案号']
print('\n表里有映射但地标(02)不会写入详情表的列:')
for c in hb_only:
    if c in df2.columns:
        print(f'  {c}: 有 (仅行标01会写)')

# 类型检测
if '标准类别' in df2.columns:
    samples = df2['标准类别'].dropna().unique()[:5]
    print('\n标准类别样例值:', list(samples))
    for v in samples[:3]:
        name = str(v).upper()
        if '国' in name or 'GB' in name: t = '00 国标'
        elif '地' in name or 'DB' in name: t = '02 地标'
        elif '团' in name or 'TB' in name: t = '03 团标'
        else: t = '01 行标(默认)'
        print(f'  "{v}" -> {t}')

if '状态' in df2.columns:
    print('\n状态列唯一值:', df2['状态'].dropna().unique().tolist())
    state_dict = {'废止': 0, '现行': 1, '即将实施': 2}
    bad = [s for s in df2['状态'].dropna().unique() if str(s).strip() not in state_dict]
    if bad:
        print('无法识别为 ex_state 的状态值:', bad)
