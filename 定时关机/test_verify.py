# -*- coding: utf-8 -*-
"""
功能检验脚本：不真正执行 shutdown，mock 掉 subprocess；
messagebox 弹窗改为记录后跳过，保证可无人值守运行。
"""
import subprocess
import datetime
import winreg
from unittest import mock

import main

APP = main.ShutdownTimerApp
REG_PATH = APP.REG_PATH
REG_VALUE = APP.REG_VALUE

results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(("PASS" if ok else "FAIL"), "-", name, ("| " + detail) if detail else "")


# ---------- 备份注册表中的已有任务（避免破坏真实数据） ----------
def read_reg():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH)
        v = winreg.QueryValueEx(key, REG_VALUE)[0]
        winreg.CloseKey(key)
        return v
    except OSError:
        return None

def write_reg(text):
    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_PATH)
    winreg.SetValueEx(key, REG_VALUE, 0, winreg.REG_SZ, text)
    winreg.CloseKey(key)

def del_reg():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, REG_VALUE)
        winreg.CloseKey(key)
    except OSError:
        pass
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REG_PATH)
    except OSError:
        pass

saved_reg = read_reg()

# ---------- mock：shutdown 命令与弹窗 ----------
shutdown_calls = []

def fake_run(cmd, **kwargs):
    shutdown_calls.append(cmd)
    class R:
        returncode = 0
    return R()

class FakeMsg:
    @staticmethod
    def showwarning(title, msg, **kw):
        print(f"  [弹窗-警告] {title}: {msg.replace(chr(10), ' / ')}")
    @staticmethod
    def showerror(title, msg, **kw):
        print(f"  [弹窗-错误] {title}: {msg.replace(chr(10), ' / ')}")

with mock.patch.object(main.subprocess, "run", fake_run), \
     mock.patch.object(main.messagebox, "showwarning", FakeMsg.showwarning), \
     mock.patch.object(main.messagebox, "showerror", FakeMsg.showerror):

    import tkinter as tk
    root = tk.Tk()
    root.withdraw()

    # 清空注册表，保证从"无任务"状态开始测
    del_reg()
    app = APP(root)

    # 1. 初始状态
    check("初始状态为未设置", app.status_label["text"] == "未设置关机")
    check("初始取消按钮置灰", str(app.cancel_btn["state"]) == "disabled")
    check("初始倒计时显示 --:--:--", app.countdown_label["text"] == "--:--:--")
    check("初始无注册表任务", read_reg() is None)

    # 2. describe_target
    now = datetime.datetime.now()
    check("describe_target-今天", app.describe_target(now.replace(second=0)) == now.strftime("%H:%M") + " 关机")
    check("describe_target-明天", app.describe_target(now + datetime.timedelta(days=1)) == "明天 " + (now + datetime.timedelta(days=1)).strftime("%H:%M") + " 关机")
    d3 = now + datetime.timedelta(days=3)
    check("describe_target-跨天带日期", app.describe_target(d3) == d3.strftime("%m-%d %H:%M") + " 关机")

    # 3. 分钟模式：正常
    app.minutes_var.set("30")
    app.start_minutes()
    ok = (app.running and app.target_time is not None
          and abs((app.target_time - datetime.datetime.now()).total_seconds() - 1800) < 5)
    check("30分钟倒计时设置成功", ok)
    check("30分钟模式已下发系统关机", any(c[:2] == ["shutdown", "/s"] and "/t" in c for c in shutdown_calls))
    check("30分钟模式任务写入注册表", read_reg() is not None)
    check("30分钟模式取消按钮可用", str(app.cancel_btn["state"]) == "normal")
    check("30分钟模式状态栏红色倒计时", app.status_label["fg"] == APP.OK_RED)

    # 4. 分钟模式：非法输入（先取消，确保从"无任务"状态开始）
    app.cancel_shutdown()
    n_calls = len(shutdown_calls)
    for bad in ["abc", "0", "-5", "50000"]:
        app.minutes_var.set(bad)
        app.start_minutes()
    check("非法分钟输入全部被拒绝", not app.running and app.target_time is None)
    check("非法输入未下发任何系统命令", len(shutdown_calls) == n_calls)
    check("上限对齐 43200 分钟(30天)", APP.SHUTDOWN_MAX_SECONDS == 2592000)

    # 5. 分钟模式边界值 43200 应该成功
    app.minutes_var.set("43200")
    app.start_minutes()
    check("43200分钟(30天)边界值可用", app.running)
    app.cancel_shutdown()
    check("取消后状态复位", (not app.running and app.target_time is None
                          and app.status_label["text"] == "已取消关机"
                          and read_reg() is None
                          and str(app.cancel_btn["state"]) == "disabled"))

    # 6. 指定时间模式：正常（设为 1 小时后）
    t = (datetime.datetime.now() + datetime.timedelta(hours=1))
    app.hour_var.set(t.strftime("%H"))
    app.minute_var.set(t.strftime("%M"))
    app.start_specific_time()
    check("指定时间(1小时后)设置成功", app.running and app.status_label["text"] == t.strftime("%H:%M") + " 关机")

    # 7. 指定时间模式：过去时间自动排到明天
    past = (datetime.datetime.now() - datetime.timedelta(hours=1))
    app.hour_var.set(past.strftime("%H"))
    app.minute_var.set(past.strftime("%M"))
    app.start_specific_time()
    expect = (datetime.datetime.now().replace(hour=past.hour, minute=past.minute, second=0, microsecond=0)
              + datetime.timedelta(days=1))
    check("过去时间自动排到明天", app.target_time is not None and app.target_time.date() == expect.date()
          and app.status_label["text"] == "明天 " + expect.strftime("%H:%M") + " 关机")

    # 8. 指定时间模式：非法输入（先取消，确保从"无任务"状态开始）
    app.cancel_shutdown()
    n_calls = len(shutdown_calls)
    app.hour_var.set("25"); app.minute_var.set("99")
    app.start_specific_time()
    check("非法时间(25:99)被拒绝", not app.running)
    app.hour_var.set("aa"); app.minute_var.set("bb")
    app.start_specific_time()
    check("非数字时间被拒绝", not app.running)
    check("非法时间未下发任何系统命令", len(shutdown_calls) == n_calls)

    # 9. 倒计时到点逻辑（把 target 改成过去，验证到点分支）
    app.hour_var.set((datetime.datetime.now() + datetime.timedelta(hours=1)).strftime("%H"))
    app.minute_var.set((datetime.datetime.now() + datetime.timedelta(hours=1)).strftime("%M"))
    app.start_specific_time()
    app.target_time = datetime.datetime.now() - datetime.timedelta(seconds=1)
    n_before = len(shutdown_calls)
    app.update_countdown()
    immediate = shutdown_calls[n_before:]
    check("到点后补发立即关机(兜底)", any(c[:2] == ["shutdown", "/s"] and "/t" in c and c[-1] == "0" for c in immediate))
    check("到点后任务删除、状态复位", (not app.running and read_reg() is None
                                  and app.status_label["text"] == "正在关机"))

    # 10. 重新下发恢复逻辑（模拟重启后恢复任务）
    target = datetime.datetime.now() + datetime.timedelta(minutes=25)
    write_reg(target.strftime("%Y-%m-%d %H:%M:%S"))
    n_before = len(shutdown_calls)
    app.load_saved_task()
    check("注册表任务恢复成功", app.running and app.target_time is not None
          and abs((app.target_time - target).total_seconds()) < 2)
    # 恢复时应先 shutdown /a 取消旧命令，再按剩余秒数重新下发
    tail = shutdown_calls[n_before:]
    check("恢复时先取消旧系统关机(/a)", any(c == ["shutdown", "/a"] for c in tail))
    check("恢复时按剩余秒数重新下发", any(c[:2] == ["shutdown", "/s"] for c in tail))
    app.cancel_shutdown()

    # 11. 过期任务：注册表里的时间已过去，应清理且不恢复
    write_reg((datetime.datetime.now() - datetime.timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S"))
    app.load_saved_task()
    check("过期任务被自动清理", not app.running and read_reg() is None)

    # 12. 损坏数据：注册表内容非法，应清理且不崩溃
    write_reg("not-a-date")
    app.load_saved_task()
    check("损坏数据被自动清理", not app.running and read_reg() is None)

    # 13. 退出程序：只退出界面，不取消系统关机
    app.minutes_var.set("60")
    app.start_minutes()
    n_before = len(shutdown_calls)
    app.close_program()
    check("退出程序不发任何 shutdown 命令", len(shutdown_calls) == n_before)

    try:
        root.destroy()
    except tk.TclError:
        pass  # close_program 已销毁窗口，属预期

# ---------- 还原用户原本的注册表任务 ----------
if saved_reg is not None:
    write_reg(saved_reg)
    print("\n(已还原测试前注册表中的原任务:", saved_reg, ")")
else:
    del_reg()

fails = [r for r in results if not r[1]]
print("\n========== 结果汇总: %d 项, 通过 %d, 失败 %d ==========" % (len(results), len(results) - len(fails), len(fails)))
if fails:
    for name, _, _ in fails:
        print("  FAILED:", name)
    raise SystemExit(1)
