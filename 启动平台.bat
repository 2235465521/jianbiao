@echo off
chcp 65001 >nul
title 标准数据极速入库平台
cd /d "%~dp0"

echo.
echo  ========================================
echo    标准数据极速入库平台
echo  ========================================
echo.

set PYTHONPATH=%CD%

python -c "import streamlit" >nul 2>&1
if errorlevel 1 (
    echo [提示] 未检测到 streamlit，正在安装依赖...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [错误] 依赖安装失败，请手动执行: pip install -r requirements.txt
        pause
        exit /b 1
    )
)

echo [启动] 正在打开浏览器...
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://localhost:8501"

echo [运行] http://localhost:8501  （关闭本窗口即停止服务）
echo.
python -m streamlit run app\web_import_tool.py --server.headless true

pause
