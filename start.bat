@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title 小梦的词书 · 准备运行环境
rem 平时双击「小梦的词书.exe」就行；它发现缺 Python 或缺组件时会自动打开本文件。
rem 本文件做的事：找 Python 3.10+ → 没有就下载官方 Python 安装包并安装（只装给当前用户）→ 安装依赖 → 打开程序。

set "PYVER=3.12.10"
set "PYSHA=67b5635e80ea51072b87941312d00ec8927c4db9ba18938f7ad2d27b328b95fb"
set "INST=%TEMP%\python-%PYVER%-amd64.exe"

call :findpy
if defined PY goto deps

echo.
echo  ==================================================================
echo    这台电脑上还没有 Python 3.10 或更新版本。
echo    小梦的词书是用 Python 写的，需要它才能运行。
echo.
echo    接下来会自动下载官方的 Python %PYVER% 安装包，约 26 MB。
echo    只安装给当前用户，不需要管理员权限，不会影响别的程序。
echo    以后不想要了，可以在「设置 - 应用」里像普通软件一样卸载。
echo  ==================================================================
echo.
choice /c YN /t 20 /d Y /m "现在开始下载安装吗？按 Y 开始，按 N 改为自己安装（20 秒后自动开始）"
if errorlevel 2 goto manual

:download
call :fetch "https://www.python.org/ftp/python/%PYVER%/python-%PYVER%-amd64.exe"
if not errorlevel 1 goto install
echo 官网下载不顺利，换国内镜像（npmmirror）重试……
call :fetch "https://registry.npmmirror.com/-/binary/python/%PYVER%/python-%PYVER%-amd64.exe"
if not errorlevel 1 goto install
echo 再换一个镜像（华为云）重试……
call :fetch "https://mirrors.huaweicloud.com/python/%PYVER%/python-%PYVER%-amd64.exe"
if not errorlevel 1 goto install
echo.
echo 下载失败，请检查网络连接后再双击「小梦的词书.exe」重试。
goto manual

:install
echo.
echo 正在安装 Python %PYVER%，会弹出一个安装进度窗口，请稍等一两分钟……
"%INST%" /passive InstallAllUsers=0 PrependPath=1 Include_launcher=0 Include_test=0 Include_doc=0 Include_tcltk=0 Shortcuts=0 AssociateFiles=0
set "RC=%errorlevel%"
del "%INST%" >nul 2>&1
if "%RC%"=="1602" (
  echo 安装被取消了。
  goto manual
)
call :findpy
if defined PY goto deps
echo.
echo Python 安装没有成功，返回代码 %RC%。
goto manual

:deps
"%PY%" -c "import PySide6, fsrs, openpyxl" >nul 2>&1
if not errorlevel 1 goto launch
echo.
echo 第一次运行，正在安装小梦的词书需要的组件（PySide6 等，约 150 MB），请稍等几分钟……
"%PY%" -m pip install --disable-pip-version-check --timeout 30 -r requirements.txt
if not errorlevel 1 goto launch
echo.
echo 从官方源下载不顺利，换用国内镜像（清华大学）重试……
"%PY%" -m pip install --disable-pip-version-check --timeout 30 -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
if not errorlevel 1 goto launch
echo.
echo 组件安装失败。请检查网络连接，然后再双击「小梦的词书.exe」重试。
echo 如果一直失败，可以把这个窗口截图发到 GitHub 的 Issues 或者 B 站私信千醉_LDream。
pause
exit /b 1

:launch
echo 准备好了，正在打开小梦的词书……
set "PYW=%PY:python.exe=pythonw.exe%"
if not exist "%PYW%" set "PYW=%PY%"
start "" "%PYW%" run.py
exit /b 0

:manual
echo.
echo 也可以自己安装 Python：在打开的网页里下载 Python 3.12，
echo 安装界面第一页记得勾选 "Add python.exe to PATH"，装好后再双击「小梦的词书.exe」。
start "" https://www.python.org/downloads/
pause
exit /b 1

rem ---------------------------------------------------------------- 子程序
rem 找一个能用的 Python 3.10+，结果（python.exe 的完整路径）放在 PY 里
:findpy
set "PY="
set "PYOUT=%TEMP%\shici-python-path.txt"
call :trypy "python" ""
if defined PY exit /b 0
call :trypy "py" "-3"
if defined PY exit /b 0
for /d %%d in ("%LOCALAPPDATA%\Programs\Python\Python3*" "%ProgramFiles%\Python3*") do (
  if exist "%%~d\python.exe" call :trypy "%%~d\python.exe" ""
)
exit /b 0

:trypy
del "%PYOUT%" >nul 2>&1
"%~1" %~2 -c "import sys; sys.version_info >= (3, 10) or sys.exit(1); open(sys.argv[1], 'w', encoding='utf-8').write(sys.executable)" "%PYOUT%" >nul 2>&1
if errorlevel 1 exit /b 1
if not exist "%PYOUT%" exit /b 1
set /p PY=<"%PYOUT%"
del "%PYOUT%" >nul 2>&1
exit /b 0

rem 下载 Python 安装包到 INST，并核对 SHA-256（和 python.org 官方文件一致才用）
:fetch
echo.
echo 正在下载 Python 安装包：%~1
del "%INST%" >nul 2>&1
where curl >nul 2>&1
if errorlevel 1 goto fetch_ps
curl -L --fail --connect-timeout 15 --speed-limit 20000 --speed-time 25 --progress-bar -o "%INST%" "%~1"
goto fetch_check
:fetch_ps
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol='Tls12'; try { Invoke-WebRequest -UseBasicParsing -Uri '%~1' -OutFile '%INST%' } catch { exit 1 }"
:fetch_check
if not exist "%INST%" exit /b 1
certutil -hashfile "%INST%" SHA256 | findstr /i /c:"%PYSHA%" >nul
if errorlevel 1 (
  echo 下载的文件不完整或校验不通过，丢弃。
  del "%INST%" >nul 2>&1
  exit /b 1
)
exit /b 0
