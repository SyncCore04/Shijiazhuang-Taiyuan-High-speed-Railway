@echo off
setlocal
rem ============================================================
rem  一键启动：本地 HTTP 服务 + 自动打开浏览器
rem  用法:
rem    start.bat              打开主页 index.html（端口 8000）
rem    start.bat record       打开录制页 record.html
rem    start.bat index 8010   指定页面与端口
rem  关闭服务: 关闭本窗口, 或在窗口内按 Ctrl+C 后按 Y
rem  注意: 本文件必须以 ANSI/GBK 编码保存, 否则中文提示会乱码
rem ============================================================

cd /d "%~dp0"

set "PAGE=index.html"
if /i "%~1"=="record" set "PAGE=record.html"
if /i "%~1"=="index" set "PAGE=index.html"
set "PORT=%~2"
if "%PORT%"=="" set "PORT=8000"

rem --- 端口已被监听 = 服务已在跑, 直接开浏览器即可 ---
netstat -ano | findstr /r /c:":%PORT% .*LISTENING" >nul 2>nul
if not errorlevel 1 (
  echo [OK] 端口 %PORT% 已有服务在运行, 直接打开浏览器.
  start "" "http://localhost:%PORT%/%PAGE%"
  exit /b 0
)

rem --- 找一个可用的 Python (绕开 Microsoft Store 的 python 占位程序) ---
set "PY="
python -c "import http.server" >nul 2>nul && set "PY=python"
if not defined PY (
  py -3 -c "import http.server" >nul 2>nul && set "PY=py -3"
)
if not defined PY (
  echo [错误] 没有找到可用的 Python 3, 请先安装后重试.
  pause
  exit /b 1
)

echo [启动] http://localhost:%PORT%/%PAGE%
echo [提示] 关闭本窗口或按 Ctrl+C 即可停止服务.
start "" cmd /c "timeout /t 1 /nobreak >nul & start "" http://localhost:%PORT%/%PAGE%"
%PY% -m http.server %PORT% --bind 127.0.0.1
