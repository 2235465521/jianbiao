# 📑 标准管理系统 数据库设计文档 V3 (Data Dictionary)

本文件详尽记录了 V3 版架构（国标/行标/地标详情表物理分离、字段聚合、ID 精准重置）的数据库表结构。

---

## 1. 核心层 (Core)

### 1.1 `std_base` (标准基础核心主表)
存储标准的最基本物理标识及其全生命周期核心元数据。

| 字段名 | 类型 | 必填 | 默认值 | 注释 |
| :--- | :--- | :--- | :--- | :--- |
| `id` | BIGINT UNSIGNED | 是 | (自增) | 主键ID |
| `std_id` | VARCHAR(50) | 是 | - | 标准号 (UNIQ) |
| `std_type` | VARCHAR(20) | 是 | - | 标准类型 (GB, HB, DB 等) |
| `std_type_no` | VARCHAR(2) | 否 | NULL | 00国标, 01行标, 02地标, 06企标... |
| `std_chinesename` | VARCHAR(255) | 否 | NULL | 中文标准名称 |
| `std_englishname` | VARCHAR(255) | 否 | NULL | 英文标准名称 |
| `release_date` | DATE | 否 | NULL | 发布日期 |
| `implement_date`| DATE | 否 | NULL | 实施日期 |
| `ex_state` | TINYINT | 否 | NULL | 0废止, 1现行, 2即将实施 |
| `create_time` | DATETIME | 是 | CURRENT_TIMESTAMP | 系统录入时间 |

---

## 2. 详情层 (Details - 物理分类)

### 2.1 `std_gb_detail` (国标详情信息表)
专属于 **国家标准** 的详细属性。

| 字段名 | 类型 | 必填 | 注释 |
| :--- | :--- | :--- | :--- |
| `id` | BIGINT UNSIGNED | 是 | 详情表自增ID |
| `base_id` | BIGINT UNSIGNED | 是 | 关联主表 ID |
| `ccs` | VARCHAR(50) | 否 | 中国标准文献分类号 |
| `ics` | VARCHAR(50) | 否 | 国际标准分类号 |
| `drafter` | LONGTEXT | 否 | 主要起草人 |
| `report_unit` | VARCHAR(100) | 否 | 归口单位 |
| `sub_report_unit`| VARCHAR(100) | 否 | 执行单位 |

### 2.2 `std_hb_detail` (行标详情信息表)
专属于 **行业标准** 的详细属性。

| 字段名 | 类型 | 必填 | 注释 |
| :--- | :--- | :--- | :--- |
| `id` | BIGINT UNSIGNED | 是 | 详情表自增ID |
| `base_id` | BIGINT UNSIGNED | 是 | 关联主表 ID |
| `industry_type` | VARCHAR(50) | 否 | 行业分类 |
| `std_indu_type` | VARCHAR(50) | 否 | 标准类别 |
| `record_no` | VARCHAR(50) | 否 | 备案号 |
| `record_date` | DATE | 否 | 备案日期 |
| `rev_type` | VARCHAR(20) | 否 | 制修订 |
| `tech_committee`| VARCHAR(100) | 否 | 技术归口 |
| `approve_dept` | VARCHAR(100) | 否 | 批准发布部门 |
| `ccs`, `ics`, `drafter`, `report_unit` | - | 否 | (同国标对应字段) |

### 2.3 `std_db_detail` (地标详情信息表)
专属于 **地方标准** 的详细属性。

| 字段名 | 类型 | 必填 | 注释 |
| :--- | :--- | :--- | :--- |
| `id` | BIGINT UNSIGNED | 是 | 详情表自增ID |
| `base_id` | BIGINT UNSIGNED | 是 | 关联主表 ID |
| `industry_type` | VARCHAR(50) | 否 | 行业分类 |
| `std_indu_type` | VARCHAR(50) | 否 | 标准类别 |
| `record_no` | VARCHAR(50) | 否 | 备案号 |
| `record_date` | DATE | 否 | 备案日期 |
| `rev_type` | VARCHAR(20) | 否 | 制修订 |
| `tech_committee`| VARCHAR(100) | 否 | 技术归口 |
| `approve_dept` | VARCHAR(100) | 否 | 批准发布部门 |
| `ccs`, `ics` | - | 否 | (同国标对应字段) |

### 2.4 `std_iso_detail` (ISO国际标准详情表)
专属于 **ISO 国际标准** 的详细属性。

| 字段名 | 类型 | 必填 | 注释 |
| :--- | :--- | :--- | :--- |
| `id` | BIGINT UNSIGNED | 是 | 详情表自增ID |
| `base_id` | BIGINT UNSIGNED | 是 | 关联主表 ID |
| `std_varsion` | TINYINT | 否 | 版本 |
| `std_EN` | VARCHAR(8) | 否 | 标准语言 (如 EN) |
| `std_rele_issue` | VARCHAR(50) | 否 | 标准发布组织 (如 ISO) |

### 2.5 `std_iec_detail` (IEC国际标准详情表)
专属于 **IEC 国际标准** 的详细属性。

| 字段名 | 类型 | 必填 | 注释 |
| :--- | :--- | :--- | :--- |
| `id` | BIGINT UNSIGNED | 是 | 详情表自增ID |
| `base_id` | BIGINT UNSIGNED | 是 | 关联主表 ID |
| `nat_issue` | VARCHAR(30) | 否 | 国际组织机构 (如 TC 76) |
| `std_varsion` | FLOAT | 否 | 版本 (如 4.1) |
| `std_EN` | VARCHAR(8) | 否 | 标准语言 (如 EN-FR) |
| `std_rele_issue` | VARCHAR(20) | 否 | 标准发布组织 (如 IEC) |

---

## 3. 全局联合视图 (View)

### 3.1 `view_std_full`
**核心逻辑**：使用 `COALESCE` 自动合并同名业务字段（如 ccs/ics/drafter/industry_type 等），并左连接 `std_iso_detail` 与 `std_iec_detail` 补充国际标准信息。

---

## 4. 维度层 (Dimensions - 字典与画像)

### 4.1 `area_dict` (全国行政区划字典表)
存储国家标准的 6 位行政区划代码及地理坐标，支持地图可视化与区域统计。

| 字段名 | 类型 | 必填 | 默认值 | 注释 |
| :--- | :--- | :--- | :--- | :--- |
| `area_code` | VARCHAR(10) | 是 | - | 主键，6位区划代码 (如: 110105) |
| `province_name` | VARCHAR(50) | 是 | - | 省份名称 (如: 北京市) |
| `city_name` | VARCHAR(50) | 否 | NULL | 城市名称 |
| `county_name` | VARCHAR(50) | 否 | NULL | 区县名称 |
| `level` | TINYINT | 是 | - | 层级: 1-省, 2-市, 3-区县 |
| `longitude` | DECIMAL(10,7) | 否 | NULL | 经度 (通过民政部接口自动采集) |
| `latitude` | DECIMAL(10,7) | 否 | NULL | 纬度 (通过民政部接口自动采集) |

### 4.2 `unit_dict` (起草单位实体表)
存储经过清洗去重后的单位（机构/企业/高校）实体画像。

| 字段名 | 类型 | 必填 | 默认值 | 注释 |
| :--- | :--- | :--- | :--- | :--- |
| `unit_id` | INT | 是 | (自增) | 单位主键 ID |
| `unit_name` | VARCHAR(255) | 是 | - | 单位清洗后的标准全称 (UNIQUE) |
| `area_code` | VARCHAR(10) | 否 | NULL | 关联的 6 位行政区划代码 (已做本地匹配+API补充) |
| `credit_code` | VARCHAR(18) | 否 | NULL | 统一社会信用代码 (预留) |
| `created_at` | TIMESTAMP | 否 | CURRENT_TIMESTAMP | 录入时间 |
| `updated_at` | TIMESTAMP | 否 | - | 更新时间 |

---

## 5. 关联与谱系层 (Relationship & Pedigree)

### 5.1 `std_unit_relation` (标准-单位映射表)
实现标准与起草单位之间的多对多关联。

| 字段名 | 类型 | 必填 | 默认值 | 注释 |
| :--- | :--- | :--- | :--- | :--- |
| `id` | INT | 是 | (自增) | 关系主键 ID |
| `base_id` | BIGINT UNSIGNED | 是 | - | 关联 `std_base.id` |
| `unit_id` | INT | 是 | - | 关联 `unit_dict.unit_id` |
| `role_type` | TINYINT | 否 | 2 | 角色: 1=主起草单位, 2=参与起草单位 |
| `rank_order` | INT | 否 | 0 | 在原始文本中的排名顺序 (从1开始) |

### 5.2 `std_pedigree` (标准家族谱系表)
存储标准与其所属“谱系家族”的映射关系。

| 字段名 | 类型 | 必填 | 默认值 | 注释 |
| :--- | :--- | :--- | :--- | :--- |
| `id` | BIGINT UNSIGNED | 是 | (自增) | 主键 ID |
| `base_id` | BIGINT UNSIGNED | 是 | - | 关联 `std_base.id` |
| `std_id_latest` | VARCHAR(1023) | 否 | NULL | 该谱系下目前最新的标准号 |
| `ped_id` | VARCHAR(512) | 是 | - | 谱系族 ID (支持多 ID 拼接) |

### 5.3 `std_ped_chain` (标准谱系链条表)
存储完整的一条“由新到旧”的演变序列字符串。

| 字段名 | 类型 | 必填 | 默认值 | 注释 |
| :--- | :--- | :--- | :--- | :--- |
| `id` | BIGINT UNSIGNED | 是 | (自增) | 主键 ID |
| `ped_id` | VARCHAR(512) | 是 | - | 谱系族 ID (与 std_pedigree 关联) |
| `ped_chain` | LONGTEXT | 否 | NULL | 格式化的谱系演化链条字符串 |

---

## 6. 其他历史遗留表

*   `std_extend_h` / `std_extend_s`: 早期起草单位冗余存储表（现已迁移至 `unit_dict`）。
*   `std_replace`: 传统的标准替代关系表。
