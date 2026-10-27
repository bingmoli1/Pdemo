@echo off
cd /d %~dp0
title 闲鱼自动发货 - 商品管理页面
echo 正在打开商品管理页面（浏览器会自动弹出），关闭本窗口即退出。
echo.
python admin_server.py
pause
