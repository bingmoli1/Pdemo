@echo off
cd /d %~dp0
title 自动发货 - 停止
echo 正在停止所有正在运行的自动发货实例（含它们打开的浏览器窗口）…
set PY=python
where python >nul 2>nul || set PY=py
%PY% stop_all.py
echo 已停止。
pause
