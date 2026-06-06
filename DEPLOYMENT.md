# 标准数据极速入库平台 - 服务器部署与启动文档

本文档用于指导在 Linux 本地服务器（如 `192.168.10.225`）上的项目部署、日常启动与常见排错。

---

## 📋 基础环境准备
在启动服务前，请确保以下环境已就绪：
1. **网络挂载**：确认 NAS 共享路径已挂载到服务器的 `/mnt/std_bk` 目录。
2. **数据库**：MySQL 数据库正常运行，账号为 `root`，密码为 `zkbz2025`。
3. **Python 环境**：已激活 `(jianbiao)` 虚拟环境。

---

## 🚀 日常启动方式

进入项目根目录：
```bash
cd ~/jianbiao
```

### 方式 A：后台常驻运行（推荐）
服务会在后台一直运行，即使关闭 SSH 终端窗口也不会中断。
```bash
# 1. 确保 logs 目录存在
mkdir -p logs

# 2. 启动服务（输出重定向到 logs/streamlit.log）
nohup python -m streamlit run app/web_import_tool.py --server.port 8501 --server.headless true > logs/streamlit.log 2>&1 &
```

### 方式 B：前台运行（用于开发测试）
方便查看实时输出，关闭终端后服务即停止。
```bash
python -m streamlit run app/web_import_tool.py --server.port 8501 --server.headless true
```

---

## 🛠️ 服务管理与排错

### 1. 为什么页面展示的是“旧项目”？（端口占用问题）
如果您访问 `http://192.168.10.225:8501` 发现打开的是旧项目，或者页面没有更新，通常是因为：
**8501 端口被服务器上之前启动的旧 Streamlit 进程占用了。** 当您尝试启动新服务时，Streamlit 检测到 8501 被占用，会自动跳到 **8502** 端口运行。

#### 诊断步骤：
* **查看新服务的实际运行端口**：
  ```bash
  cat logs/streamlit.log
  ```
  如果日志中包含 `Port 8501 is already in use, using port 8502 instead.`，说明新服务正运行在 8502 端口，您可以通过 `http://192.168.10.225:8502` 访问。

* **释放 8501 端口（关闭旧进程并重新启动新服务）**：
  1. 查询占用 8501 端口的进程 PID：
     ```bash
     lsof -i :8501
     # 或者使用：
     netstat -nlp | grep 8501
     ```
  2. 杀死旧的进程（假定 PID 为 12345）：
     ```bash
     kill -9 12345
     # 或者一步到位杀死所有占用 8501 的进程：
     kill -9 $(lsof -t -i:8501)
     ```
  3. 重新运行**方式 A** 的启动命令。

### 2. 常用监控命令
* **查看实时运行日志**：
  ```bash
  tail -f logs/streamlit.log
  ```
* **查看 Streamlit 进程**：
  ```bash
  ps -ef | grep streamlit
  ```
* **一键关闭服务**：
  ```bash
  kill $(pgrep -f "streamlit run")
  ```

---

## ⚙️ 关机后自动启动设置 (Systemd)

如果您希望服务器关机或重启后，项目能够自动启动，请配置系统守护进程：

1. **获取 Python 绝对路径**：
   在激活了虚拟环境的终端中运行：
   ```bash
   which python
   ```
   记录输出的路径（例如 `/home/zkbz01/jianbiao/venv/bin/python`）。

2. **创建服务配置文件**：
   ```bash
   sudo nano /etc/systemd/system/jianbiao.service
   ```
   写入以下配置（替换其中的 `ExecStart` 路径为第一步获取的 Python 路径）：
   ```ini
   [Unit]
   Description=Streamlit Standard Data Import Platform
   After=network.target mysql.service

   [Service]
   Type=simple
   User=zkbz01
   WorkingDirectory=/home/zkbz01/jianbiao
   ExecStart=/home/zkbz01/jianbiao/venv/bin/python -m streamlit run app/web_import_tool.py --server.port 8501 --server.headless true
   Restart=always
   RestartSec=5

   [Install]
   WantedBy=multi-user.target
   ```

3. **启用自启服务**：
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable jianbiao.service
   sudo systemctl start jianbiao.service
   ```
