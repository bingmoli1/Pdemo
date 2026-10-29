# -*- coding: utf-8 -*-
"""停止所有正在运行的自动发货实例（含它们各自打开的浏览器窗口）。

也可在商品管理页点「全部停止」；或直接运行 python stop_all.py。
"""
import os
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from stores import clear_run_pid, pid_alive, running_accounts  # noqa: E402


def kill(pid) -> None:
    """连进程树一起结束：浏览器是它的子进程，要一起关掉。"""
    try:
        pid = int(pid)
    except Exception:
        return
    if pid <= 0:
        return
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           capture_output=True, timeout=20)
        except Exception:
            pass
        return
    try:
        os.kill(pid, 15)
    except Exception:
        pass


def main():
    jobs = running_accounts()
    if not jobs:
        print("现在没有账号在运行。")
    for name, info in sorted(jobs.items()):
        pid = int(info.get("pid") or 0)
        print(f"停止「{name}」（PID {pid}）…")
        kill(pid)
        clear_run_pid(name, pid)
        for _ in range(10):
            if not pid_alive(pid):
                break
    # 兜底：命令行里带 auto_delivery.py run 的 python 进程（手动双击 bat、pid 文件丢失的情况）
    if os.name == "nt":
        ps = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' "
              "-and $_.CommandLine -like '*auto_delivery.py*run*' } | ForEach-Object "
              "{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
        try:
            subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, timeout=60)
        except Exception:
            pass
    print("已停止。")


if __name__ == "__main__":
    main()
