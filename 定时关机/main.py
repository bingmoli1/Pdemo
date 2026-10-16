
import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import datetime
import json
import os


class ShutdownTimerApp:

    # 保存任务的文件
    SAVE_FILE = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "shutdown_task.json"
    )

    def __init__(self, root):

        self.root = root
        self.root.geometry("500x450")
        self.root.resizable(False, False)

        self.shutdown_timer = None
        self.running = False
        self.target_time = None

        # =========================
        # 标题
        # =========================
        title = tk.Label(
            root,
            text="Windows 定时关机工具",
            font=("Microsoft YaHei", 18, "bold")
        )
        title.pack(pady=15)

        # =========================
        # ① 多少分钟后关机
        # =========================
        frame1 = tk.LabelFrame(
            root,
            text="① 多少分钟后关机",
            font=("Microsoft YaHei", 11, "bold"),
            padx=15,
            pady=12
        )
        frame1.pack(fill="x", padx=20, pady=5)

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
            width=10,
            state="normal",
            font=("Microsoft YaHei", 11)
        )
        minute_box.pack(side="left", padx=5)

        tk.Label(
            frame1,
            text="分钟后关机",
            font=("Microsoft YaHei", 10)
        ).pack(side="left", padx=5)

        tk.Button(
            frame1,
            text="开始倒计时",
            command=self.start_minutes,
            width=13,
            font=("Microsoft YaHei", 10)
        ).pack(side="right", padx=5)

        # =========================
        # ② 指定时间关机
        # =========================
        frame2 = tk.LabelFrame(
            root,
            text="② 指定时间关机",
            font=("Microsoft YaHei", 11, "bold"),
            padx=15,
            pady=12
        )
        frame2.pack(fill="x", padx=20, pady=10)

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
            width=5,
            font=("Microsoft YaHei", 12),
            justify="center"
        ).pack(
            side="left",
            padx=(5, 2)
        )

        tk.Label(
            frame2,
            text="时",
            font=("Microsoft YaHei", 10)
        ).pack(
            side="left",
            padx=(0, 8)
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
            width=5,
            font=("Microsoft YaHei", 12),
            justify="center"
        ).pack(
            side="left",
            padx=(2, 2)
        )

        tk.Label(
            frame2,
            text="分",
            font=("Microsoft YaHei", 10)
        ).pack(
            side="left",
            padx=(0, 5)
        )

        # 指定时间关机按钮
        tk.Button(
            frame2,
            text="指定时间关机",
            command=self.start_specific_time,
            width=13,
            font=("Microsoft YaHei", 10)
        ).pack(
            side="right",
            padx=5
        )

        # =========================
        # 当前状态
        # =========================
        status_frame = tk.Frame(root)
        status_frame.pack(pady=12)

        tk.Label(
            status_frame,
            text="当前状态：",
            font=("Microsoft YaHei", 11, "bold")
        ).pack(side="left")

        self.status_label = tk.Label(
            status_frame,
            text="未设置关机",
            font=("Microsoft YaHei", 11),
            fg="green"
        )
        self.status_label.pack(side="left")

        # =========================
        # 倒计时
        # =========================
        self.countdown_label = tk.Label(
            root,
            text="--:--:--",
            font=("Consolas", 32, "bold")
        )
        self.countdown_label.pack(pady=5)

        # =========================
        # 操作按钮
        # =========================
        button_frame = tk.Frame(root)
        button_frame.pack(pady=12)

        tk.Button(
            button_frame,
            text="取消关机",
            command=self.cancel_shutdown,
            width=15,
            height=2,
            font=("Microsoft YaHei", 11, "bold")
        ).pack(
            side="left",
            padx=8
        )

        tk.Button(
            button_frame,
            text="退出程序",
            command=self.close_program,
            width=15,
            height=2,
            font=("Microsoft YaHei", 11, "bold")
        ).pack(
            side="left",
            padx=8
        )

        # =========================
        # 底部提示
        # =========================
        tk.Label(
            root,
            text="指定时间默认设置为当前时间 + 1小时",
            font=("Microsoft YaHei", 9),
            fg="gray"
        ).pack(
            side="bottom",
            pady=10
        )

        # =========================
        # 启动时恢复之前的任务
        # =========================
        self.load_saved_task()

    # ==================================================
    # 保存任务
    # ==================================================
    def save_task(self):

        if self.target_time is None:
            return

        data = {
            "target_time": self.target_time.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        }

        try:

            with open(
                self.SAVE_FILE,
                "w",
                encoding="utf-8"
            ) as f:

                json.dump(
                    data,
                    f,
                    ensure_ascii=False,
                    indent=4
                )

        except Exception:
            pass

    # ==================================================
    # 删除保存的任务
    # ==================================================
    def delete_saved_task(self):

        try:

            if os.path.exists(self.SAVE_FILE):
                os.remove(self.SAVE_FILE)

        except Exception:
            pass

    # ==================================================
    # 程序启动时恢复任务
    # ==================================================
    def load_saved_task(self):

        if not os.path.exists(self.SAVE_FILE):
            return

        try:

            with open(
                self.SAVE_FILE,
                "r",
                encoding="utf-8"
            ) as f:

                data = json.load(f)

            target_text = data.get("target_time")

            if not target_text:
                return

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

            # =========================
            # 这里只显示时间，不显示日期
            # =========================
            self.status_label.config(
                text=f"{target.strftime('%H:%M')} 关机",
                fg="red"
            )

            # 恢复倒计时
            self.update_countdown()

        except Exception:

            # 保存文件损坏
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
            fg="red"
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
            fg="red"
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
            fg="green"
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
