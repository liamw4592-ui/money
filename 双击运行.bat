@echo off
chcp 65001 >nul
title 赚钱雷达
cd /d "%~dp0"
where python >nul 2>nul || (echo 未找到 Python，请先安装: https://www.python.org/downloads/ ^(安装时勾选 Add to PATH^) & pause & exit /b)
python scripts\monitor.py --open
echo.
echo 已用浏览器打开结果页，可关闭此窗口。
pause
