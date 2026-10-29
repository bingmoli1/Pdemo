@echo off
cd /d %~dp0
if "%1"=="" (title 自动发货 - 当前账号（关闭本窗口即停止）) else (title 自动发货 - %1（关闭本窗口即停止）)
echo 正在启动自动发货，随后会弹出一个浏览器窗口。
echo 未登录时会先等你用手机闲鱼/淘宝扫码，登录后自动开始监听。
echo 保持浏览器停留在闲鱼「消息」页；关闭浏览器或本窗口即停止本账号。
echo 提示：也可以到「商品管理」页面里点每个账号的「启动」，多个账号可同时运行。
echo.
set PY=python
where python >nul 2>nul || set PY=py
if "%1"=="" (%PY% auto_delivery.py run) else (%PY% auto_delivery.py run --account %1)
if %errorlevel%==0 exit
echo.
echo 程序异常退出，请把上面的提示截图排查。
pause
