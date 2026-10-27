@echo off
cd /d %~dp0
title 闲鱼自动发货 - 停止
echo 正在停止自动发货程序和它打开的浏览器...
powershell -Command "Get-CimInstance Win32_Process | Where-Object { \D:\Pdemo\闲鱼.Name -eq 'python.exe' -and \D:\Pdemo\闲鱼.CommandLine -like '*auto_delivery.py run*' } | ForEach-Object { Stop-Process -Id \D:\Pdemo\闲鱼.ProcessId -Force -ErrorAction SilentlyContinue }; Get-CimInstance Win32_Process | Where-Object { \D:\Pdemo\闲鱼.Name -eq 'chrome.exe' -and \D:\Pdemo\闲鱼.CommandLine -like '*browser_data*' } | ForEach-Object { Stop-Process -Id \D:\Pdemo\闲鱼.ProcessId -Force -ErrorAction SilentlyContinue }"
echo 已停止。
pause
