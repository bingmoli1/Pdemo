@echo off
cd /d %~dp0
title 闲鱼自动发货 - 运行中（关闭浏览器或本窗口即停止）
echo 正在启动闲鱼自动发货，稍后会弹出浏览器窗口，请保持它停留在闲鱼"消息"页。
echo 关闭浏览器窗口 = 停止程序并自动关闭本窗口。
echo.
set PY=python
where python >nul 2>nul || set PY=py
%PY% auto_delivery.py run
if %errorlevel%==0 exit
echo.
echo 程序异常退出，请把上面的内容截图反馈。
pause
