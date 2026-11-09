import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import datetime
import json
import os
import sys
import ctypes


# ======================================================
# 高分屏适配：按真实 DPI 渲染，避免文字发虚
# 必须在创建 Tk 窗口之前调用
#
# 注意只能用"系统 DPI 感知"(1)，不能用 per-monitor (2)：
# per-monitor 模式下 Windows 会自行移动/缩放跨屏窗口，
# 而 Tk 不处理对应的 WM_DPICHANGED 消息，两边争抢窗口矩形，
# 窗口位置就会乱跳乱闪。系统 DPI 感知由系统统一缩放，
# 位置稳定，主显示器上文字依然是清晰的。
# ======================================================
def enable_windows_dpi_awareness():

    if sys.platform != "win32":
        return

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


# ======================================================
# 单实例保护：
# 两个实例同时倒计时时，先开的那个到点会补发立即关机，
# 会把后开实例设置的更长任务提前打断，所以只允许运行一个
# ======================================================
def another_instance_running():

    if sys.platform != "win32":
        return False

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    kernel32.CreateMutexW(
        None,
        False,
        "Local\\ScheduledShutdownTool"
    )

    return ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS


# ======================================================
# 任务持久化路径：
# %APPDATA%\ScheduledShutdown\shutdown_task.json
# 只写当前用户自己的目录，不需要管理员权限，也不写注册表
# ======================================================
def get_save_file():

    base = os.environ.get("APPDATA")

    if not base:
        base = os.path.join(
            os.path.expanduser("~"),
            "AppData",
            "Roaming"
        )

    return os.path.join(
        base,
        "ScheduledShutdown",
        "shutdown_task.json"
    )


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
    DISABLED = "#CBD5E1"      # 置灰按钮
    OK_GREEN = "#16A34A"      # 安全状态
    OK_RED = "#DC2626"        # 倒计时中状态

    # 下拉框专用
    FIELD_BORDER = "#CBD5E1"  # 常态描边
    FIELD_HOVER = "#93C5FD"   # 悬停描边
    FIELD_FOCUS_BG = "#F7FBFF"  # 聚焦底色
    FIELD_DISABLED_BG = "#F8FAFC"
    ARROW = "#94A3B8"         # 箭头
    ARROW_ACTIVE = "#3B82F6"  # 悬停/聚焦箭头
    SELECT_BG = "#DBEAFE"     # 文本选中底色

    # =========================
    # 任务持久化：AppData 下的 json 文件
    # 不在 exe 所在目录生成任何文件，也不写注册表
    # 用类属性是为了方便检验脚本替换成临时路径
    # =========================
    SAVE_FILE = get_save_file()

    # shutdown /t 的上限（秒）：文档写的是 10 年（315360000），
    # 但实测部分 Win11 版本对该值返回错误 87，
    # 这里按实测可用的 30 天（2592000）限制，对关机定时足够了
    SHUTDOWN_MAX_SECONDS = 2592000

    # shutdown.exe 的退出码 ERROR_SHUTDOWN_IS_SCHEDULED：
    # 系统里已经挂着一条计划关机时，再下发 /s /t 会返回 1190。
    # 恢复任务时据此判断"旧命令仍在"，从而不必执行会弹系统通知的 /a
    SHUTDOWN_ALREADY_SCHEDULED = 1190

    # 启动 shutdown.exe 时不创建控制台窗口：
    # exe 是无控制台打包的，不加这个每次执行命令都会闪一下黑窗
    NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

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
    # 小工具：按实际 DPI 缩放设计像素（96 DPI 为基准）
    # ==================================================
    def px(self, value):

        return int(value * self.ui_scale)

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
        ).pack(anchor="w", padx=self.px(10), pady=(self.px(5), 0))

        body = tk.Frame(card, bg=self.CARD)
        body.pack(fill="x", padx=self.px(10), pady=(self.px(1), self.px(7)))

        card.pack(fill="x", padx=self.px(14), pady=(self.px(3), self.px(3)))

        return body

    # ==================================================
    # 小工具：扁平彩色按钮（带悬停变色，置灰时不响应悬停）
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
            padx=self.px(padx),
            pady=self.px(2),
            cursor="hand2",
            highlightthickness=0
        )

        def on_enter(_event):

            if str(btn["state"]) == "normal":
                btn.config(bg=hover)

        def on_leave(_event):

            if str(btn["state"]) == "normal":
                btn.config(bg=bg)

        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)

        return btn

    # ==================================================
    # 小工具：窗口在屏幕上居中
    # 窗口处于 withdraw 隐藏状态时 winfo_width 可能返回 1，
    # 此时退回用请求尺寸计算
    # ==================================================
    def center_window(self):

        self.root.update_idletasks()

        width = self.root.winfo_width()
        height = self.root.winfo_height()

        if width <= 1:
            width = self.root.winfo_reqwidth()

        if height <= 1:
            height = self.root.winfo_reqheight()

        x = (self.root.winfo_screenwidth() - width) // 2
        # 稍微偏上一点，视觉上更正
        y = (self.root.winfo_screenheight() - height) // 2 - self.px(20)

        if x < 0:
            x = 0
        if y < 0:
            y = 0

        self.root.geometry(f"+{x}+{y}")

    # ==================================================
    # 小工具：目标时间转状态栏文案
    # 跨天的任务带上日期，避免"明天关机"只显示 HH:MM 造成误解
    # ==================================================
    def describe_target(self, target):

        today = datetime.date.today()

        if target.date() == today:
            return f"{target.strftime('%H:%M')} 关机"

        if target.date() == today + datetime.timedelta(days=1):
            return f"明天 {target.strftime('%H:%M')} 关机"

        return f"{target.strftime('%m-%d %H:%M')} 关机"

    # ==================================================
    # 小工具：取消按钮的可用/置灰状态
    # ==================================================
    def set_cancel_enabled(self, enabled):

        if enabled:
            self.cancel_btn.config(
                state="normal",
                bg=self.DANGER
            )
        else:
            self.cancel_btn.config(
                state="disabled",
                bg=self.DISABLED
            )

    def __init__(self, root):

        self.root = root

        # 先隐藏窗口，等位置摆好再显示，
        # 避免启动时窗口先出现在默认位置、再跳到居中位置的闪跳
        root.withdraw()

        self.root.title("Windows 定时关机工具")
        self.root.configure(bg=self.BG)
        self.root.resizable(False, False)

        # 96 DPI 设计尺寸，按实际 DPI 等比放大
        self.ui_scale = max(1.0, root.winfo_fpixels("1i") / 96.0)
        self.root.geometry(f"{self.px(370)}x{self.px(330)}")

        self.shutdown_timer = None
        self.running = False
        self.target_time = None

        # =========================
        # ttk 风格：下拉框配色与扁平卡片统一
        # clam 主题允许自由配色，原生 vista 主题改不了外观
        # =========================
        style = ttk.Style()
        style.theme_use("clam")

        style.configure(
            "Card.TCombobox",
            fieldbackground=self.CARD,
            background=self.CARD,
            foreground=self.TEXT,
            bordercolor=self.FIELD_BORDER,
            lightcolor=self.CARD,
            darkcolor=self.CARD,
            borderwidth=1,
            relief="solid",
            padding=(self.px(9), self.px(5)),
            insertcolor=self.PRIMARY,
            selectbackground=self.SELECT_BG,
            selectforeground=self.TEXT,
            arrowcolor=self.ARROW,
            arrowsize=self.px(10),
            postoffset=(0, self.px(3), 0, 0)
        )

        # 状态按顺序匹配（先命中先生效），所以 disabled 放最前
        style.map(
            "Card.TCombobox",
            fieldbackground=[
                ("disabled", self.FIELD_DISABLED_BG),
                ("focus", self.FIELD_FOCUS_BG)
            ],
            bordercolor=[
                ("disabled", self.BORDER),
                ("focus", self.PRIMARY),
                ("active", self.FIELD_HOVER)
            ],
            arrowcolor=[
                ("disabled", self.DISABLED),
                ("focus", self.ARROW_ACTIVE),
                ("active", self.ARROW_ACTIVE)
            ],
            foreground=[
                ("disabled", self.SUBTEXT)
            ]
        )

        # 保留 clam 自带的箭头元素与布局：它画的是完整的四边框 +
        # 独立箭头按钮，比自绘图片贴进去更干净（自绘会吃掉右边框）
        # 只通过 arrowcolor / arrowsize 调整颜色和大小

        # 下拉展开的列表：白底、无凸起边框、蓝色选中、去掉虚线焦点框
        root.option_add("*TCombobox*Listbox.background", self.CARD)
        root.option_add("*TCombobox*Listbox.foreground", self.TEXT)
        root.option_add("*TCombobox*Listbox.selectBackground", self.PRIMARY)
        root.option_add("*TCombobox*Listbox.selectForeground", "#FFFFFF")
        root.option_add("*TCombobox*Listbox.selectBorderWidth", 0)
        root.option_add("*TCombobox*Listbox.font", ("Microsoft YaHei", 10))
        root.option_add("*TCombobox*Listbox.relief", "flat")
        root.option_add("*TCombobox*Listbox.borderWidth", 0)
        root.option_add("*TCombobox*Listbox.highlightThickness", 0)
        root.option_add("*TCombobox*Listbox.activestyle", "none")

        # =========================
        # 标题
        # =========================
        tk.Label(
            root,
            text="定时关机",
            font=("Microsoft YaHei", 13, "bold"),
            bg=self.BG,
            fg=self.TEXT
        ).pack(pady=(self.px(12), self.px(4)))

        # =========================
        # ① 多少分钟后关机
        # =========================
        frame1 = self.make_card(root, "① 多少分钟后关机")

        self.minutes_var = tk.StringVar(value="30")

        minute_box = ttk.Combobox(
            frame1,
            style="Card.TCombobox",
            textvariable=self.minutes_var,
            values=[
                "5",
                "10",
                "15",
                "20",
                "30",
                "45",
                "60",
                "90",
                "120"
            ],
            width=5,
            state="normal",
            font=("Microsoft YaHei", 10)
        )
        minute_box.pack(side="left", padx=(0, self.px(4)))

        tk.Label(
            frame1,
            text="分钟后关机",
            font=("Microsoft YaHei", 9),
            bg=self.CARD,
            fg=self.TEXT
        ).pack(side="left")

        self.flat_button(
            frame1,
            "开启定时",
            self.start_minutes,
            self.PRIMARY,
            self.PRIMARY_HOVER,
            padx=12
        ).pack(side="right")

        # 输入完直接回车就能开始
        minute_box.bind("<Return>", lambda _e: self.start_minutes())

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
        # 小时（点击下拉选择，也可直接输入）
        # =========================
        self.hour_var = tk.StringVar(
            value=default_time.strftime("%H")
        )

        hour_box = ttk.Combobox(
            frame2,
            style="Card.TCombobox",
            textvariable=self.hour_var,
            values=[f"{h:02d}" for h in range(24)],
            width=3,
            state="normal",
            height=10,
            font=("Microsoft YaHei", 10)
        )
        hour_box.pack(side="left", padx=(0, self.px(2)))

        tk.Label(
            frame2,
            text="时",
            font=("Microsoft YaHei", 9),
            bg=self.CARD,
            fg=self.TEXT
        ).pack(
            side="left",
            padx=(0, self.px(6))
        )

        # =========================
        # 分钟（点击下拉选择，也可直接输入）
        # =========================
        self.minute_var = tk.StringVar(
            value=default_time.strftime("%M")
        )

        minute_box = ttk.Combobox(
            frame2,
            style="Card.TCombobox",
            textvariable=self.minute_var,
            values=[f"{m:02d}" for m in range(60)],
            width=3,
            state="normal",
            height=10,
            font=("Microsoft YaHei", 10)
        )
        minute_box.pack(side="left", padx=(0, self.px(2)))

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
            "开启定时",
            self.start_specific_time,
            self.PRIMARY,
            self.PRIMARY_HOVER,
            padx=12
        ).pack(
            side="right"
        )

        # 输入完直接回车就能开始
        hour_box.bind("<Return>", lambda _e: self.start_specific_time())
        minute_box.bind("<Return>", lambda _e: self.start_specific_time())

        # =========================
        # 当前状态
        # =========================
        status_frame = tk.Frame(root, bg=self.BG)
        status_frame.pack(pady=(self.px(6), 0))

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
            fg=self.SUBTEXT
        )
        self.countdown_label.pack()

        # =========================
        # 操作按钮
        # =========================
        button_frame = tk.Frame(root, bg=self.BG)
        button_frame.pack(pady=(self.px(6), self.px(4)))

        self.cancel_btn = self.flat_button(
            button_frame,
            "取消关机",
            self.cancel_shutdown,
            self.DANGER,
            self.DANGER_HOVER,
            wide=True
        )
        self.cancel_btn.pack(side="left", padx=self.px(5))

        self.flat_button(
            button_frame,
            "退出程序",
            self.close_program,
            self.NEUTRAL,
            self.NEUTRAL_HOVER,
            wide=True
        ).pack(
            side="left",
            padx=self.px(5)
        )

        # 没有任务时取消按钮置灰，避免误点后误显示"已取消关机"
        self.set_cancel_enabled(False)

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
            pady=(0, self.px(6))
        )

        # =========================
        # 点右上角 X 也走"退出程序"：
        # 只退出界面，不取消已设置的系统关机
        # =========================
        self.root.protocol("WM_DELETE_WINDOW", self.close_program)

        # =========================
        # 启动时恢复之前的任务
        # =========================
        self.load_saved_task()

        # =========================
        # 打开时窗口居中
        # =========================
        self.center_window()

        # 位置已就位，显示窗口
        root.deiconify()

    # ==================================================
    # 保存任务到 AppData
    # 先写临时文件再原子替换，避免写到一半断电/退出留下坏文件
    # ==================================================
    def save_task(self):

        if self.target_time is None:
            return

        try:

            path = self.SAVE_FILE

            os.makedirs(
                os.path.dirname(path),
                exist_ok=True
            )

            tmp = path + ".tmp"

            with open(
                tmp,
                "w",
                encoding="utf-8"
            ) as f:

                json.dump(
                    {
                        "target_time": self.target_time.strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                    },
                    f,
                    ensure_ascii=False
                )

            os.replace(tmp, path)

        except Exception:
            pass

    # ==================================================
    # 删除保存的任务
    # ==================================================
    def delete_saved_task(self):

        for path in (self.SAVE_FILE, self.SAVE_FILE + ".tmp"):

            try:

                if os.path.exists(path):
                    os.remove(path)

            except Exception:
                pass

        # 顺手清掉旧版本遗留的 json 文件
        try:

            if os.path.exists(self.OLD_SAVE_FILE):
                os.remove(self.OLD_SAVE_FILE)

        except Exception:
            pass

    # ==================================================
    # 读取旧版本 exe 目录下的 shutdown_task.json
    # （一次性迁移到 AppData 用，无论成败都会把旧文件删掉）
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

        # ---------- AppData 中的任务文件 ----------
        try:

            with open(
                self.SAVE_FILE,
                "r",
                encoding="utf-8"
            ) as f:

                data = json.load(f)

            target_text = (
                data.get("target_time")
                if isinstance(data, dict)
                else None
            )

            if not target_text:
                raise ValueError("无效的任务文件")

        except Exception:

            target_text = None

            # 文件不存在不用管；文件存在但内容损坏就直接删掉，
            # 避免每次启动都读到坏数据
            # 这里不能用 delete_saved_task，它会把待迁移的旧 json 一起删掉
            try:

                if os.path.exists(self.SAVE_FILE):
                    os.remove(self.SAVE_FILE)

            except Exception:
                pass

        # ---------- 旧版 exe 目录 json 文件迁移 ----------
        legacy = False

        if target_text:

            # AppData 里已有任务，旧文件已无用途，顺手清理
            self.read_legacy_task()

        else:

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

            # 旧版 json 里的任务迁移到 AppData
            if legacy:

                self.save_task()

            # 系统级关机命令不跨重启保留：
            # 这里按剩余秒数重新下发，保证电脑到点真的会关机
            remaining = int(
                (target - now).total_seconds()
            )

            # 恢复时不再无条件调用 shutdown /a：
            # Windows 每取消一次计划关机都会弹「注销被取消 / 计划的关闭已取消」通知，
            # 而退出程序时系统关机命令是保留的，于是每次打开软件都会弹一次。
            # 改为直接按剩余秒数下发，按退出码分两种结果：
            #   0    -> 系统里本来没有命令（例如刚重启过），已重新设好；
            #   1190 -> 系统里还挂着上次留下的计划关机，直接沿用，不取消。
            # 两条路径的关机时刻一致：/t 秒数都由同一个绝对目标时间算出，
            # 旧命令在 T1 下发 /t (target-T1)、本次在 T2 下发 /t (target-T2)，
            # 落点都是 target，最多 1 秒取整误差。
            code = self.execute_shutdown(
                remaining
            )

            if code != 0 and code != self.SHUTDOWN_ALREADY_SCHEDULED:

                self.running = False
                self.target_time = None
                self.delete_saved_task()

                messagebox.showerror(
                    "错误",
                    "设置关机失败，之前保存的任务已丢弃。\n\n"
                    "如果系统策略（组策略）禁止通过命令行关机，"
                    "则本功能无法使用。",
                    parent=self.root
                )

                return

            self.set_cancel_enabled(True)

            self.status_label.config(
                text=self.describe_target(target),
                fg=self.OK_RED
            )

            self.countdown_label.config(fg=self.OK_RED)

            # 恢复倒计时
            self.update_countdown()

        except Exception:

            # 保存的数据损坏
            self.delete_saved_task()

    # ==================================================
    # 执行 Windows 关机
    # ==================================================
    def execute_shutdown(self, seconds):
        """
        执行 Windows 关机命令。
        成功返回 0；失败返回 shutdown.exe 的退出码（异常时返回 -1）。
        调用方必须检查返回值，失败时不能假倒计时。
        返回退出码而不是布尔值，是为了让恢复流程能识别 1190
        （系统里已有一条计划关机），避免误判成失败后去执行 /a 弹通知。
        """

        try:

            result = subprocess.run(
                [
                    "shutdown",
                    "/s",
                    "/f",
                    "/t",
                    str(seconds)
                ],
                shell=False,
                creationflags=self.NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            return result.returncode

        except Exception:

            return -1

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
                shell=False,
                creationflags=self.NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

        except Exception:
            pass

    # ==================================================
    # 设置 / 改期关机任务（两个"开始"按钮共用）
    #
    # 已有任务时是"改期"，不是"删掉再重设"：
    #   - 新命令确认成功之前，不动 target_time / running / 任务文件；
    #   - 成功后一次性提交，直接覆盖保存，全程不调用 delete_saved_task；
    #   - 失败则原任务原样保留，并尽量把旧的系统命令补回去。
    # ==================================================
    def set_shutdown_target(self, target, seconds):

        old_target = self.target_time
        old_running = self.running

        # 连点/重复点同一个时间：目标几乎没变，直接忽略，
        # 避免为此去取消系统里的关机命令（会弹"注销被取消"通知）
        if (old_running and old_target is not None
                and abs((target - old_target).total_seconds()) < 2):
            return True

        # 先直接下发，不预先取消任何东西。
        # 系统里没有挂着的关机命令时（重启后第一次设置）一次就成功，
        # 完全不会触发 shutdown /a
        code = self.execute_shutdown(seconds)

        # 1190：Windows 只允许存在一个计划关机，改时间必须先清掉旧的。
        # 这是系统层面的限制，但任务数据始终没被删除
        if code == self.SHUTDOWN_ALREADY_SCHEDULED:

            self.cancel_system_shutdown()
            code = self.execute_shutdown(seconds)

        if code != 0:

            # 失败时保住原任务：不清空状态、不删文件，只提示
            if (old_running and old_target is not None
                    and old_target > datetime.datetime.now()):

                # 若上一步 /a 已把旧命令清掉，按原目标时间补回去；
                # 若旧命令还在，这次调用返回 1190，同样说明原任务仍有效
                self.execute_shutdown(
                    int(
                        (
                            old_target - datetime.datetime.now()
                        ).total_seconds()
                    )
                )

                messagebox.showerror(
                    "错误",
                    "修改关机时间失败，已保留原来的关机任务。\n\n"
                    "如果系统策略（组策略）禁止通过命令行关机，"
                    "则本功能无法使用。",
                    parent=self.root
                )

            else:

                self.running = False
                self.target_time = None
                self.delete_saved_task()

                messagebox.showerror(
                    "错误",
                    "设置关机失败。\n\n"
                    "如果系统策略（组策略）禁止通过命令行关机，"
                    "则本功能无法使用。",
                    parent=self.root
                )

            return False

        # 到这里新命令已确认生效，才提交状态并覆盖任务文件
        self.target_time = target
        self.running = True
        self.save_task()

        self.set_cancel_enabled(True)

        self.status_label.config(
            text=self.describe_target(target),
            fg=self.OK_RED
        )

        self.countdown_label.config(fg=self.OK_RED)

        self.update_countdown()

        return True

    # ==================================================
    # ① 多少分钟后关机
    # ==================================================
    def start_minutes(self):

        text = self.minutes_var.get().strip()

        try:
            minutes = int(text)
        except ValueError:
            minutes = 0

        # 上限与系统 shutdown /t 实测可用的 30 天对齐，超出时命令会失败
        if minutes <= 0 or minutes * 60 > self.SHUTDOWN_MAX_SECONDS:

            messagebox.showwarning(
                "输入错误",
                "请输入正确的分钟数（1 - 43200，即 30 天以内），\n例如：10、30、60、120",
                parent=self.root
            )

            return

        target = (
            datetime.datetime.now()
            + datetime.timedelta(
                minutes=minutes
            )
        )

        self.set_shutdown_target(target, minutes * 60)

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
                "分钟：0 - 59",
                parent=self.root
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

        self.set_shutdown_target(target, seconds)

    # ==================================================
    # 小工具：停止内部 1 秒倒计时定时器
    # ==================================================
    def stop_timer(self):

        if self.shutdown_timer is not None:

            try:

                self.root.after_cancel(
                    self.shutdown_timer
                )

            except Exception:
                pass

            self.shutdown_timer = None

    # ==================================================
    # 更新倒计时
    # ==================================================
    def update_countdown(self):

        if not self.running:
            return

        if self.target_time is None:
            return

        # 先停掉可能残留的旧回调（例如上一个任务遗留的），
        # 防止多条 1 秒刷新链并行运行
        self.stop_timer()

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
            self.stop_timer()

            # 删除保存的任务
            self.delete_saved_task()

            self.set_cancel_enabled(False)

            # 兜底关机：正常路径在开始时已下发过系统命令，
            # 但如果重启后系统里已没有该命令，就必须在这里
            # 直接补发立即关机，保证电脑到点真的会关
            self.execute_shutdown(0)

            # 同步状态栏，避免红色"XX:XX 关机"停留误导
            self.status_label.config(
                text="正在关机",
                fg=self.OK_RED
            )

            return

        # 超过 24 小时先显示天数，避免出现 100:00:00 这种时长
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        if days > 0:
            text = f"{days}天 {hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            text = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        # 显示倒计时
        self.countdown_label.config(text=text)

        # 每秒刷新
        self.shutdown_timer = self.root.after(
            1000,
            self.update_countdown
        )

    # ==================================================
    # 取消关机
    # ==================================================
    def cancel_shutdown(self):

        was_running = self.running

        # 取消 Windows 关机
        self.cancel_system_shutdown()

        # 停止内部计时
        self.running = False
        self.target_time = None
        self.stop_timer()

        # 删除保存任务
        self.delete_saved_task()

        # 更新界面
        self.set_cancel_enabled(False)

        self.status_label.config(
            text="已取消关机" if was_running else "未设置关机",
            fg=self.OK_GREEN
        )

        self.countdown_label.config(
            text="--:--:--",
            fg=self.SUBTEXT
        )

    # ==================================================
    # 退出程序
    # ==================================================
    def close_program(self):

        # 注意：
        # 这里只退出程序
        # 不取消 Windows 的关机任务

        self.running = False
        self.stop_timer()

        self.root.destroy()


# ======================================================
# 程序入口
# ======================================================

if __name__ == "__main__":

    enable_windows_dpi_awareness()

    # 已有实例在运行就不再开第二个窗口，
    # 避免两个倒计时互相覆盖、旧实例到点重复触发关机
    if another_instance_running():

        ctypes.windll.user32.MessageBoxW(
            None,
            "定时关机工具已经在运行了，请使用已打开的窗口。",
            "提示",
            0x00000040  # MB_ICONINFORMATION
        )

        sys.exit(0)

    root = tk.Tk()

    app = ShutdownTimerApp(root)

    root.mainloop()
