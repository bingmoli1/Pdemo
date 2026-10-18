import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import datetime
import json
import os
import sys
import winreg


class ShutdownTimerApp:

    # =========================
    # 界面配色 / 常量（仅影响外观）
    # =========================
    BG = "#F4F6FA"            # 窗口背景
    CARD = "#FFFFFF"          # 卡片背景
    BORDER = "#E2E8F0"        # 卡片描边
    TEXT = "#1E293B"          # 主文字
    SUBTEXT = "#94A3B8"       # 次要文字
    PRIMARY = "#3B82F6"       # 主按钮蓝
    PRIMARY_HOVER = "#2563EB"
    DANGER = "#F43F5E"        # 取消按钮红
    DANGER_HOVER = "#E11D48"
    NEUTRAL = "#94A3B8"       # 退出按钮灰
    NEUTRAL_HOVER = "#64748B"
    OK_GREEN = "#16A34A"      # 安全状态
    OK_RED = "#DC2626"        # 倒计时中状态

    # =========================
    # 任务持久化：Windows 注册表（不在目录里生成任何文件）
    # =========================
    REG_PATH = "Software\\ScheduledShutdown"
    REG_VALUE = "target_time"

    # 旧版本遗留的 shutdown_task.json（仅用于一次性迁移，读到后即删除）
    if getattr(sys, "frozen", False):
        OLD_SAVE_FILE = os.path.join(
            os.path.dirname(os.path.abspath(sys.executable)),
            "shutdown_task.json"
        )
    else:
        OLD_SAVE_FILE = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "shutdown_task.json"
        )

    # ==================================================
    # 小工具：卡片容器（标题 + 内容区）
    # ==================================================
    def make_card(self, parent, heading):

        card = tk.Frame(
            parent,
            bg=self.CARD,
            highlightbackground=self.BORDER,
            highlightcolor=self.BORDER,
            highlightthickness=1
        )

        tk.Label(
            card,
            text=heading,
            bg=self.CARD,
            fg=self.SUBTEXT,
            font=("Microsoft YaHei", 8)
        ).pack(anchor="w", padx=10, pady=(5, 0))

        body = tk.Frame(card, bg=self.CARD)
        body.pack(fill="x", padx=10, pady=(1, 7))

        card.pack(fill="x", padx=14, pady=(3, 3))

        return body

    # ==================================================
    # 小工具：扁平彩色按钮（带悬停变色）
    # ==================================================
    def flat_button(self, parent, text, command, bg, hover, wide=False, padx=0):

        btn = tk.Button(
            parent,
            text=text,
            command=command,
            font=("Microsoft YaHei", 9, "bold" if wide else "normal"),
            bg=bg,
            fg="white",
            activebackground=hover,
            activeforeground="white",
            relief="flat",
            bd=0,
            width=10 if wide else 9,
            padx=padx,
            pady=2,
            cursor="hand2",
            highlightthickness=0
        )

        btn.bind("<Enter>", lambda _e: btn.config(bg=hover))
        btn.bind("<Leave>", lambda _e: btn.config(bg=bg))

        return btn

    # ==================================================
    # 小工具：窗口在屏幕上居中
    # ==================================================
    def center_window(self):

        self.root.update_idletasks()

        width = self.root.winfo_width()
        height = self.root.winfo_height()

        x = (self.root.winfo_screenwidth() - width) // 2
        # 稍微偏上一点，视觉上更正
        y = (self.root.winfo_screenheight() - height) // 2 - 20

        if x < 0:
            x = 0
        if y < 0:
            y = 0

        self.root.geometry(f"+{x}+{y}")

    def __init__(self, root):

        self.root = root
        self.root.title("Windows 定时关机工具")
        self.root.geometry("370x330")
        self.root.resizable(False, False)
        self.root.configure(bg=self.BG)

        self.shutdown_timer = None
        self.running = False
        self.target_time = None

        # =========================
        # 标题
        # =========================
        tk.Label(
            root,
            text="定时关机",
            font=("Microsoft YaHei", 13, "bold"),
            bg=self.BG,
            fg=self.TEXT
        ).pack(pady=(12, 4))

        # =========================
        # ① 多少分钟后关机
        # =========================
        frame1 = self.make_card(root, "① 多少分钟后关机")

        self.minutes_var = tk.StringVar(value="30")

        minute_box = ttk.Combobox(
            frame1,
            textvariable=self.minutes_var,
            values=[
                "10",
                "20",
                "30",
                "40",
                "50",
                "60",
                "120"
            ],
            width=5,
            state="normal",
            font=("Microsoft YaHei", 10)
        )
        minute_box.pack(side="left", padx=(0, 4))

        tk.Label(
            frame1,
            text="分钟后关机",
            font=("Microsoft YaHei", 9),
            bg=self.CARD,
            fg=self.TEXT
        ).pack(side="left")

        self.flat_button(
            frame1,
            "开始倒计时",
            self.start_minutes,
            self.PRIMARY,
            self.PRIMARY_HOVER,
            padx=12
        ).pack(side="right")

        # =========================
        # ② 指定时间关机
        # =========================
        frame2 = self.make_card(root, "② 指定时间关机")

        # 默认时间 = 当前时间 + 1小时
        default_time = (
            datetime.datetime.now()
            + datetime.timedelta(hours=1)
        )

        # =========================
        # 小时
        # =========================
        self.hour_var = tk.StringVar(
            value=default_time.strftime("%H")
        )

        tk.Entry(
            frame2,
            textvariable=self.hour_var,
            width=4,
            font=("Microsoft YaHei", 10),
            justify="center",
            relief="solid",
            bd=1
        ).pack(
            side="left",
            padx=(0, 2)
        )

        tk.Label(
            frame2,
            text="时",
            font=("Microsoft YaHei", 9),
            bg=self.CARD,
            fg=self.TEXT
        ).pack(
            side="left",
            padx=(0, 6)
        )

        # =========================
        # 分钟
        # =========================
        self.minute_var = tk.StringVar(
            value=default_time.strftime("%M")
        )

        tk.Entry(
            frame2,
            textvariable=self.minute_var,
            width=4,
            font=("Microsoft YaHei", 10),
            justify="center",
            relief="solid",
            bd=1
        ).pack(
            side="left",
            padx=(0, 2)
        )

        tk.Label(
            frame2,
            text="分",
            font=("Microsoft YaHei", 9),
            bg=self.CARD,
            fg=self.TEXT
        ).pack(
            side="left"
        )

        # 指定时间关机按钮
        self.flat_button(
            frame2,
            "指定时间关机",
            self.start_specific_time,
            self.PRIMARY,
            self.PRIMARY_HOVER,
            padx=12
        ).pack(
            side="right"
        )

        # =========================
        # 当前状态
        # =========================
        status_frame = tk.Frame(root, bg=self.BG)
        status_frame.pack(pady=(6, 0))

        tk.Label(
            status_frame,
            text="当前状态：",
            font=("Microsoft YaHei", 10, "bold"),
            bg=self.BG,
            fg=self.TEXT
        ).pack(side="left")

        self.status_label = tk.Label(
            status_frame,
            text="未设置关机",
            font=("Microsoft YaHei", 10),
            bg=self.BG,
            fg=self.OK_GREEN
        )
        self.status_label.pack(side="left")

        # =========================
        # 倒计时
        # =========================
        self.countdown_label = tk.Label(
            root,
            text="--:--:--",
            font=("Consolas", 22, "bold"),
            bg=self.BG,
            fg=self.TEXT
        )
        self.countdown_label.pack()

        # =========================
        # 操作按钮
        # =========================
        button_frame = tk.Frame(root, bg=self.BG)
        button_frame.pack(pady=(6, 4))

        self.flat_button(
            button_frame,
            "取消关机",
            self.cancel_shutdown,
            self.DANGER,
            self.DANGER_HOVER,
            wide=True
        ).pack(
            side="left",
            padx=5
        )

        self.flat_button(
            button_frame,
            "退出程序",
            self.close_program,
            self.NEUTRAL,
            self.NEUTRAL_HOVER,
            wide=True
        ).pack(
            side="left",
            padx=5
        )

        # =========================
        # 底部提示
        # =========================
        tk.Label(
            root,
            text="指定时间默认设置为当前时间 + 1小时",
            font=("Microsoft YaHei", 8),
            bg=self.BG,
            fg=self.SUBTEXT
        ).pack(
            side="bottom",
            pady=(0, 6)
        )

        # =========================
        # 启动时恢复之前的任务
        # =========================
        self.load_saved_task()

        # =========================
        # 打开时窗口居中
        # =========================
        self.center_window()

    # ==================================================
    # 保存任务
    # ==================================================
    def save_task(self):

        if self.target_time is None:
            return

        try:

            key = winreg.CreateKey(
                winreg.HKEY_CURRENT_USER,
                self.REG_PATH
            )

            winreg.SetValueEx(
                key,
                self.REG_VALUE,
                0,
                winreg.REG_SZ,
                self.target_time.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )

            winreg.CloseKey(key)

        except Exception:
            pass

    # ==================================================
    # 删除保存的任务
    # ==================================================
    def delete_saved_task(self):

        try:

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.REG_PATH,
                0,
                winreg.KEY_SET_VALUE
            )

            winreg.DeleteValue(key, self.REG_VALUE)
            winreg.CloseKey(key)

        except Exception:
            pass

        # 顺手清掉旧版本遗留的 json 文件
        try:

            if os.path.exists(self.OLD_SAVE_FILE):
                os.remove(self.OLD_SAVE_FILE)

        except Exception:
            pass

    # ==================================================
    # 读取旧版本 shutdown_task.json（一次性迁移用）
    # 无论成败都会把旧文件删掉，不留残留
    # ==================================================
    def read_legacy_task(self):

        if not os.path.exists(self.OLD_SAVE_FILE):
            return None

        try:

            with open(
                self.OLD_SAVE_FILE,
                "r",
                encoding="utf-8"
            ) as f:

                data = json.load(f)

            text = data.get("target_time")

        except Exception:

            text = None

        try:

            os.remove(self.OLD_SAVE_FILE)

        except Exception:
            pass

        return text

    # ==================================================
    # 程序启动时恢复任务
    # ==================================================
    def load_saved_task(self):

        target_text = None

        # ---------- 注册表 ----------
        try:

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.REG_PATH
            )

            target_text = winreg.QueryValueEx(
                key,
                self.REG_VALUE
            )[0]

            winreg.CloseKey(key)

        except Exception:

            target_text = None

        # ---------- 旧版 json 文件迁移 ----------
        legacy = False

        if not target_text:

            target_text = self.read_legacy_task()
            legacy = True

        if not target_text:
            return

        try:

            target = datetime.datetime.strptime(
                target_text,
                "%Y-%m-%d %H:%M:%S"
            )

            now = datetime.datetime.now()

            # 如果时间已经过去
            if target <= now:

                self.delete_saved_task()

                return

            # 恢复任务
            self.target_time = target
            self.running = True

            # 旧任务迁移到注册表
            if legacy:

                self.save_task()

            # =========================
            # 这里只显示时间，不显示日期
            # =========================
            self.status_label.config(
                text=f"{target.strftime('%H:%M')} 关机",
                fg=self.OK_RED
            )

            # 恢复倒计时
            self.update_countdown()

        except Exception:

            # 保存的数据损坏
            self.delete_saved_task()

    # ==================================================
    # 执行 Windows 关机
    # ==================================================
    def execute_shutdown(self, seconds):

        try:

            subprocess.run(
                [
                    "shutdown",
                    "/s",
                    "/f",
                    "/t",
                    str(seconds)
                ],
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

        except Exception as e:

            messagebox.showerror(
                "错误",
                f"设置关机失败：\n{e}"
            )

    # ==================================================
    # 取消 Windows 系统关机
    # ==================================================
    def cancel_system_shutdown(self):

        try:

            subprocess.run(
                [
                    "shutdown",
                    "/a"
                ],
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

        except:
            pass

    # ==================================================
    # ① 多少分钟后关机
    # ==================================================
    def start_minutes(self):

        try:

            minutes = int(
                self.minutes_var.get()
            )

            if minutes <= 0:
                raise ValueError

        except ValueError:

            messagebox.showwarning(
                "输入错误",
                "请输入正确的分钟数，例如：10、30、60、120"
            )

            return

        # 取消之前的 Windows 关机
        self.cancel_system_shutdown()

        # 计算目标时间
        self.target_time = (
            datetime.datetime.now()
            + datetime.timedelta(
                minutes=minutes
            )
        )

        self.running = True

        # 设置 Windows 关机
        self.execute_shutdown(
            minutes * 60
        )

        # 保存任务
        self.save_task()

        # 更新状态
        self.status_label.config(
            text=f"{minutes} 分钟后关机",
            fg=self.OK_RED
        )

        # 开始倒计时
        self.update_countdown()

    # ==================================================
    # ② 指定时间关机
    # ==================================================
    def start_specific_time(self):

        hour_text = self.hour_var.get().strip()
        minute_text = self.minute_var.get().strip()

        # 验证时间
        try:

            hour = int(hour_text)
            minute = int(minute_text)

            if not (0 <= hour <= 23):
                raise ValueError

            if not (0 <= minute <= 59):
                raise ValueError

        except ValueError:

            messagebox.showwarning(
                "时间格式错误",
                "请输入正确的时间：\n\n"
                "小时：0 - 23\n"
                "分钟：0 - 59"
            )

            return

        now = datetime.datetime.now()

        # 创建今天的目标时间
        target = now.replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0
        )

        # 如果今天的时间已经过去
        # 自动安排到明天
        if target <= now:

            target += datetime.timedelta(
                days=1
            )

        # 计算剩余秒数
        seconds = int(
            (target - now).total_seconds()
        )

        # 取消之前的 Windows 关机
        self.cancel_system_shutdown()

        # 保存目标时间
        self.target_time = target
        self.running = True

        # 设置 Windows 关机
        self.execute_shutdown(
            seconds
        )

        # 保存任务
        self.save_task()

        # =========================
        # 这里只显示时间，不显示日期
        # =========================
        self.status_label.config(
            text=f"{target.strftime('%H:%M')} 关机",
            fg=self.OK_RED
        )

        # 开始倒计时
        self.update_countdown()

    # ==================================================
    # 更新倒计时
    # ==================================================
    def update_countdown(self):

        if not self.running:
            return

        if self.target_time is None:
            return

        now = datetime.datetime.now()

        remaining = (
            self.target_time - now
        )

        total_seconds = int(
            remaining.total_seconds()
        )

        # 时间到了
        if total_seconds <= 0:

            self.countdown_label.config(
                text="00:00:00"
            )

            self.running = False

            # 删除保存的任务
            self.delete_saved_task()

            return

        # 计算小时
        hours = total_seconds // 3600

        # 计算分钟
        minutes = (
            total_seconds % 3600
        ) // 60

        # 计算秒
        seconds = (
            total_seconds % 60
        )

        # 显示倒计时
        self.countdown_label.config(
            text=f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        )

        # 每秒刷新
        self.shutdown_timer = self.root.after(
            1000,
            self.update_countdown
        )

    # ==================================================
    # 取消关机
    # ==================================================
    def cancel_shutdown(self):

        # 取消 Windows 关机
        self.cancel_system_shutdown()

        # 停止内部计时
        self.running = False
        self.target_time = None

        # 取消 after 定时器
        if self.shutdown_timer is not None:

            try:

                self.root.after_cancel(
                    self.shutdown_timer
                )

            except:
                pass

            self.shutdown_timer = None

        # 删除保存任务
        self.delete_saved_task()

        # 更新界面
        self.status_label.config(
            text="已取消关机",
            fg=self.OK_GREEN
        )

        self.countdown_label.config(
            text="--:--:--"
        )

    # ==================================================
    # 退出程序
    # ==================================================
    def close_program(self):

        # 注意：
        # 这里只退出程序
        # 不取消 Windows 的关机任务

        self.running = False

        if self.shutdown_timer is not None:

            try:

                self.root.after_cancel(
                    self.shutdown_timer
                )

            except:
                pass

        self.root.destroy()


# ======================================================
# 程序入口
# ======================================================

if __name__ == "__main__":

    root = tk.Tk()

    app = ShutdownTimerApp(root)

    root.mainloop()
