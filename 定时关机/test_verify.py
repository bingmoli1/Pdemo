# -*- coding: utf-8 -*-
"""
功能检验脚本：不真正执行 shutdown，mock 掉 subprocess；
messagebox 弹窗改为记录后跳过，保证可无人值守运行。
任务文件全部指向临时目录，不碰用户真实的 AppData 数据，也不写注册表。
"""
import subprocess
import datetime
import json
import os
import tempfile
from unittest import mock

import main

APP = main.ShutdownTimerApp

# 真实路径只用来校验默认值，测试一律用临时文件
REAL_SAVE_FILE = APP.SAVE_FILE
TMP_DIR = os.path.join(tempfile.gettempdir(), "shutdown_timer_verify")
TEST_SAVE_FILE = os.path.join(TMP_DIR, "shutdown_task.json")
TEST_LEGACY_FILE = os.path.join(TMP_DIR, "legacy_shutdown_task.json")

APP.SAVE_FILE = TEST_SAVE_FILE
APP.OLD_SAVE_FILE = TEST_LEGACY_FILE

results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(("PASS" if ok else "FAIL"), "-", name, ("| " + detail) if detail else "")


def expected_label(target):
    """按目标日期推算状态栏文案，跨天/跨月/跨年时都成立。"""
    today = datetime.date.today()
    if target.date() == today:
        return target.strftime("%H:%M") + " 关机"
    if target.date() == today + datetime.timedelta(days=1):
        return "明天 " + target.strftime("%H:%M") + " 关机"
    return target.strftime("%m-%d %H:%M") + " 关机"


def next_occurrence(now, hour, minute):
    """指定的 HH:MM 在今天已过则顺延到明天。"""
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += datetime.timedelta(days=1)
    return target


# ---------- 临时任务文件读写（不碰真实数据） ----------
def read_task():
    try:
        with open(TEST_SAVE_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("target_time")
    except Exception:
        return None


def write_task(text):
    os.makedirs(TMP_DIR, exist_ok=True)
    with open(TEST_SAVE_FILE, "w", encoding="utf-8") as f:
        json.dump({"target_time": text}, f)


def del_task():
    for path in (TEST_SAVE_FILE, TEST_SAVE_FILE + ".tmp"):
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass


def snapshot_real():
    try:
        with open(REAL_SAVE_FILE, "rb") as f:
            return f.read()
    except OSError:
        return None


real_before = snapshot_real()
del_task()

# ---------- 源码层面确认注册表已彻底移除 ----------
with open(main.__file__, "r", encoding="utf-8") as f:
    source = f.read()

check("main.py 不再包含注册表操作", "winreg" not in source and "HKEY_" not in source)
check("默认保存路径在 AppData 下",
      REAL_SAVE_FILE.lower().startswith((os.environ.get("APPDATA") or "").lower())
      and REAL_SAVE_FILE.endswith("shutdown_task.json"),
      REAL_SAVE_FILE)

# ---------- mock：shutdown 命令与弹窗 ----------
shutdown_calls = []
# 可动态改成 1190（系统里已有计划关机）或其它错误码，模拟不同系统状态
next_returncode = {"value": 0}
# 只对 /s 命令按顺序消费一次性的返回码，用于模拟"先 1190 再成功"这类序列
return_code_queue = []


def fake_run(cmd, **kwargs):
    shutdown_calls.append(cmd)

    class R:
        pass

    result = R()
    if cmd[:2] == ["shutdown", "/s"] and return_code_queue:
        result.returncode = return_code_queue.pop(0)
    else:
        result.returncode = next_returncode["value"]
    return result


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
    from tkinter import ttk
    root = tk.Tk()
    root.withdraw()

    # 清空任务文件，保证从"无任务"状态开始测
    del_task()
    app = APP(root)

    # 1b. 两个"开始"按钮文案
    def button_texts(widget):
        out = []
        for child in widget.winfo_children():
            if isinstance(child, tk.Button):
                out.append(str(child["text"]))
            out.extend(button_texts(child))
        return out

    texts = button_texts(root)
    check("两个开始按钮都显示「开启定时」", texts.count("开启定时") == 2, str(texts))
    check("旧按钮文案已移除", "开始倒计时" not in texts and "指定时间关机" not in texts)

    # 1c. 自定义样式必须真的被三个下拉框引用（曾出现"定义了却没用上"的 bug）
    def combobox_styles(widget):
        out = []
        for child in widget.winfo_children():
            if isinstance(child, ttk.Combobox):
                out.append(str(child["style"]))
            out.extend(combobox_styles(child))
        return out

    styles = combobox_styles(root)
    check("三个下拉框都应用 Card.TCombobox",
          styles == ["Card.TCombobox"] * 3, str(styles))
    ui_style = ttk.Style()
    check("下拉框描边/立体边框配置已生效",
          ui_style.lookup("Card.TCombobox", "bordercolor") == APP.FIELD_BORDER
          # relief 查出来是 Tcl index 对象，需要转字符串再比
          and str(ui_style.lookup("Card.TCombobox", "relief")) == "solid")
    check("下拉框聚焦/悬停状态已配置",
          "bordercolor" in ui_style.map("Card.TCombobox")
          and "arrowcolor" in ui_style.map("Card.TCombobox"))

    # 1. 初始状态
    check("初始状态为未设置", app.status_label["text"] == "未设置关机")
    check("初始取消按钮置灰", str(app.cancel_btn["state"]) == "disabled")
    check("初始倒计时显示 --:--:--", app.countdown_label["text"] == "--:--:--")
    check("初始无任务文件", read_task() is None)

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
    check("30分钟模式任务写入 AppData 文件", read_task() is not None)
    check("原子写入后不残留 .tmp 文件", not os.path.exists(TEST_SAVE_FILE + ".tmp"))
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
                          and read_task() is None
                          and str(app.cancel_btn["state"]) == "disabled"))

    # 6. 指定时间模式：正常（设为 1 小时后，跨天时状态栏会带"明天"）
    t = (datetime.datetime.now() + datetime.timedelta(hours=1))
    app.hour_var.set(t.strftime("%H"))
    app.minute_var.set(t.strftime("%M"))
    app.start_specific_time()
    expect6 = next_occurrence(datetime.datetime.now(), t.hour, t.minute)
    check("指定时间(1小时后)设置成功",
          app.running
          and app.target_time is not None
          and abs((app.target_time - expect6).total_seconds()) < 60
          and app.status_label["text"] == expected_label(expect6),
          app.status_label["text"])

    # 7. 指定时间模式：时间点已过则自动排到下一次出现（通常是明天）
    past = (datetime.datetime.now() - datetime.timedelta(hours=1))
    app.hour_var.set(past.strftime("%H"))
    app.minute_var.set(past.strftime("%M"))
    app.start_specific_time()
    expect7 = next_occurrence(datetime.datetime.now(), past.hour, past.minute)
    check("已过时间自动排到下一次出现",
          app.target_time is not None
          and abs((app.target_time - expect7).total_seconds()) < 60
          and app.status_label["text"] == expected_label(expect7),
          app.status_label["text"])

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
    check("到点后任务文件删除、状态复位", (not app.running and read_task() is None
                                    and app.status_label["text"] == "正在关机"))

    # 10. 重新下发恢复逻辑（模拟重启后恢复任务，系统里没有旧命令）
    target = datetime.datetime.now() + datetime.timedelta(minutes=25)
    write_task(target.strftime("%Y-%m-%d %H:%M:%S"))
    n_before = len(shutdown_calls)
    app.load_saved_task()
    check("AppData 任务恢复成功", app.running and app.target_time is not None
          and abs((app.target_time - target).total_seconds()) < 2)
    tail = shutdown_calls[n_before:]
    # 关键回归：恢复时不能调用 /a，否则 Windows 每次启动都弹「注销被取消」
    check("恢复时不执行 shutdown /a（不弹系统通知）",
          not any(c == ["shutdown", "/a"] for c in tail))
    check("恢复时按剩余秒数重新下发", any(c[:2] == ["shutdown", "/s"] for c in tail))
    app.cancel_shutdown()

    # 10b. 系统里还挂着上次留下的计划关机（下发返回 1190）
    target2 = datetime.datetime.now() + datetime.timedelta(minutes=25)
    write_task(target2.strftime("%Y-%m-%d %H:%M:%S"))
    next_returncode["value"] = 1190
    n_before = len(shutdown_calls)
    app.load_saved_task()
    tail = shutdown_calls[n_before:]
    check("已有计划关机(1190)时仍能恢复任务",
          app.running and app.target_time is not None
          and abs((app.target_time - target2).total_seconds()) < 2)
    check("已有计划关机时不执行 /a（不弹系统通知）",
          not any(c == ["shutdown", "/a"] for c in tail))
    check("已有计划关机时仍按剩余秒数尝试下发",
          any(c[:2] == ["shutdown", "/s"] for c in tail))
    next_returncode["value"] = 0
    app.cancel_shutdown()

    # 10c. 真正的关机失败（如组策略禁止）仍必须回滚，不能假倒计时
    write_task((datetime.datetime.now() + datetime.timedelta(minutes=25)).strftime("%Y-%m-%d %H:%M:%S"))
    next_returncode["value"] = 5
    app.load_saved_task()
    check("恢复时真实失败会丢弃任务、不假倒计时",
          not app.running and app.target_time is None and read_task() is None)
    next_returncode["value"] = 0

    # 10d. 新建任务时系统拒绝关机，同样要回滚
    app.minutes_var.set("30")
    next_returncode["value"] = 5
    app.start_minutes()
    check("新建任务失败时回滚状态",
          not app.running and app.target_time is None and read_task() is None)
    next_returncode["value"] = 0
    return_code_queue.clear()

    # 10e. 已有任务时点新时间 = 直接改期，不删除任务再重建
    app.minutes_var.set("30")
    app.start_minutes()
    old_target = app.target_time
    check("改期前已有一个任务", app.running and read_task() is not None)

    # 模拟系统里已挂着一条计划关机：首次下发返回 1190，/a 之后重发成功
    return_code_queue.extend([1190, 0])
    n_before = len(shutdown_calls)
    with mock.patch.object(app, "delete_saved_task", wraps=app.delete_saved_task) as spy:
        app.minutes_var.set("60")
        app.start_minutes()
        check("改期全程不调用 delete_saved_task", spy.call_count == 0)
    tail = shutdown_calls[n_before:]
    check("改期时先直接下发新时间", bool(tail) and tail[0][:2] == ["shutdown", "/s"])
    check("仅在遇到 1190 时才取消旧系统命令", any(c == ["shutdown", "/a"] for c in tail))
    check("改期后目标时间已更新",
          app.running and app.target_time is not None
          and (app.target_time - old_target).total_seconds() > 1700)
    check("改期后任务文件直接覆盖为新时间",
          read_task() == app.target_time.strftime("%Y-%m-%d %H:%M:%S"))

    # 10f. 改期失败时原任务必须原样保留
    old_target = app.target_time
    return_code_queue.extend([1190, 5, 0])  # 首次被拒 -> /a 后重发失败 -> 补回旧命令
    n_before = len(shutdown_calls)
    with mock.patch.object(app, "delete_saved_task", wraps=app.delete_saved_task) as spy:
        app.minutes_var.set("90")
        app.start_minutes()
        check("改期失败也不删除任务", spy.call_count == 0)
    check("改期失败后保留原目标时间", app.running and app.target_time == old_target)
    check("改期失败后任务文件仍是原时间",
          read_task() == old_target.strftime("%Y-%m-%d %H:%M:%S"))
    check("改期失败后补回旧系统命令",
          sum(1 for c in shutdown_calls[n_before:] if c[:2] == ["shutdown", "/s"]) == 3)

    # 10g. 无任务时直接设置，不执行 /a
    app.cancel_shutdown()
    return_code_queue.clear()
    n_before = len(shutdown_calls)
    app.minutes_var.set("10")
    app.start_minutes()
    tail = shutdown_calls[n_before:]
    check("无任务时直接设置、不执行 /a",
          not any(c == ["shutdown", "/a"] for c in tail) and app.running)

    # 10h. 连点同一时间不应产生任何系统命令
    app.cancel_shutdown()
    app.minutes_var.set("30")
    app.start_minutes()
    n_before = len(shutdown_calls)
    app.minutes_var.set("30")
    app.start_minutes()
    check("重复点同一时间不触发取消/重设", len(shutdown_calls) == n_before)
    app.cancel_shutdown()
    return_code_queue.clear()

    # 11. 过期任务：文件里的时间已过去，应清理且不恢复
    write_task((datetime.datetime.now() - datetime.timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S"))
    app.load_saved_task()
    check("过期任务被自动清理", not app.running and read_task() is None)

    # 12. 损坏数据：内容非法，应清理且不崩溃
    write_task("not-a-date")
    app.load_saved_task()
    check("非法日期数据被自动清理", not app.running and read_task() is None)

    os.makedirs(TMP_DIR, exist_ok=True)
    with open(TEST_SAVE_FILE, "w", encoding="utf-8") as f:
        f.write("{broken json")
    app.load_saved_task()
    check("非法 JSON 文件被自动清理", not app.running and read_task() is None)

    # 13. 旧版 exe 目录 json 迁移到 AppData
    with open(TEST_LEGACY_FILE, "w", encoding="utf-8") as f:
        json.dump({"target_time": (datetime.datetime.now()
                                   + datetime.timedelta(minutes=20)).strftime("%Y-%m-%d %H:%M:%S")}, f)
    app.load_saved_task()
    check("旧版 json 迁移到 AppData", app.running and read_task() is not None
          and not os.path.exists(TEST_LEGACY_FILE))
    app.cancel_shutdown()

    # 14. 退出程序：只退出界面，不取消系统关机
    app.minutes_var.set("60")
    app.start_minutes()
    n_before = len(shutdown_calls)
    app.close_program()
    check("退出程序不发任何 shutdown 命令", len(shutdown_calls) == n_before)

    try:
        root.destroy()
    except tk.TclError:
        pass  # close_program 已销毁窗口，属预期

# ---------- 收尾：真实任务数据必须原封不动 ----------
check("未触碰用户真实的 AppData 任务文件", snapshot_real() == real_before)
del_task()
if os.path.exists(TEST_LEGACY_FILE):
    os.remove(TEST_LEGACY_FILE)

fails = [r for r in results if not r[1]]
print("\n========== 结果汇总: %d 项, 通过 %d, 失败 %d ==========" % (len(results), len(results) - len(fails), len(fails)))
if fails:
    for name, _, _ in fails:
        print("  FAILED:", name)
    raise SystemExit(1)
