@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem 平时双击「小梦的词书.exe」就行；它找不到依赖时会自动打开本文件来安装。
python -c "import PySide6, fsrs, openpyxl" 2>nul
if errorlevel 1 (
  echo 第一次运行小梦的词书，正在安装依赖，请稍等...
  python -m pip install -r requirements.txt
  if errorlevel 1 (
    echo.
    echo 安装失败。请确认已安装 Python 3.10 或更新版本，并且安装时勾选了 "Add python.exe to PATH"。
    pause
    exit /b 1
  )
)
start "" pythonw run.py
