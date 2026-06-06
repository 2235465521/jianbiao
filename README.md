标准数据入库与核验平台。

## 快速启动

1. 复制 `.env.example` 为 `.env`，填写数据库与路径（**换机器主要改 `.env` 和根目录 `db_config.py` 默认值**）
2. 双击 **`启动平台.bat`**，浏览器打开 http://localhost:8501

或命令行：

```bash
pip install -r requirements.txt
streamlit run app/web_import_tool.py
```

首次使用若 MySQL 为空，可导入 mydate 备份：

```bash
python scripts/setup_mydate_db.py
```

## 目录结构

```
建表/
├── 启动平台.bat      ← 一键启动 Web 工具
├── .env              ← 数据库、PDF、mydate 目录等路径（需按本机修改）
├── db_config.py      ← 读取 .env 的统一配置
├── requirements.txt
├── README.md
├── app/              ← Web 主程序
│   ├── web_import_tool.py
│   ├── mydate_catalog.py
│   └── pdf_resolver.py
├── scripts/          ← 导入、迁移、核验等脚本
├── sql/              ← 建表 SQL
├── docs/             ← 说明文档
├── data/             ← 静态数据（如 pcas-code.json）
├── logs/             ← 运行日志
├── config/           ← Redis Worker 等配置
├── workers/          ← 批量入库消费者
└── scratch/          ← 临时调试脚本
```

## 批量入库（Redis + Worker，可选）

```bash
python workers/async_importer.py
python scripts/producer_api.py
```

## 说明

- **入库核验**：扫描 mydate 目录 SQL 备份 + Excel + MySQL，不限于本页新导入的数据
- 路径类配置集中在根目录 `.env`，业务代码在 `app/`、`scripts/` 子目录
