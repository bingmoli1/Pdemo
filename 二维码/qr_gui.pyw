# -*- coding: utf-8 -*-

"""
二维码批量转码工具

启动即进入批量转码主界面（唯一窗口），两个页签：
1. 文本 → 二维码（批量生成）：TXT/CSV/TSV 清单批量生成 PNG
2. 二维码 → 文本（批量识别）：多张图片/文件夹批量识别并导出
"""

import csv
import os
import re
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import qrcode
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageTk

try:
    from pyzbar.pyzbar import decode as zbar_decode
except ImportError:
    zbar_decode = None

# 尝试安装 tkinterdnd2 以支持拖拽
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    TkinterDnD = None

# ----------------------------------------------------------------------
# 视觉规范（浅色 + 圆角卡片 + 柔和阴影）
# ----------------------------------------------------------------------
BG = "#F3F5FA"           # 窗口背景
CARD = "#FFFFFF"         # 卡片背景
FIELD = "#F8FAFD"        # 预览区底色
BORDER = "#E9EDF5"       # 卡片描边
FIELD_BORDER = "#E7ECF4" # 预览区描边
DIVIDER = "#EFF2F8"      # 分隔线
TEXT = "#1D2534"         # 主文字
MUTED = "#8A93A8"        # 次要文字
STATUS_FG = "#6B7488"    # 状态栏文字
PLACEHOLDER = "#C7D0E0"  # 占位图形颜色
ACCENT = "#3B82F6"       # 主题色
ACCENT_HOVER = "#2E6FE4"
ACCENT_ACTIVE = "#2A62D0"
OK = "#16A34A"
WARN = "#D97706"
ERR = "#EF4444"

FONT = "Microsoft YaHei UI"
CONTENT_W = 244          # 卡片内容/预览区宽度（96 DPI 逻辑像素）
CARD_R = 12              # 卡片圆角
PREV_R = 10              # 预览区圆角
BTN_R = 7                # 按钮圆角
SHADOW_M = 8             # 卡片阴影留白

# ----------------------------------------------------------------------
# 批量转码共用定义（单张与批量走同一套编解码实现，结果完全一致）
# ----------------------------------------------------------------------
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff")
TEXT_EXTS = (".txt", ".csv", ".tsv")
IMG_FILETYPES = [("图像文件", "*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tif *.tiff"),
                 ("所有文件", "*.*")]
TEXT_FILETYPES = [("文本 / CSV 清单", "*.txt *.csv *.tsv"), ("所有文件", "*.*")]
DEFAULT_OUT_NAME = "二维码批量输出"
TABLE_HEADERS = {"内容", "文本", "链接", "网址", "content", "text", "link",
                 "url", "data", "value"}


def _cjk_ratio(s: str) -> float:
    """统计 CJK 汉字占比，用于挑选最像正常文本的候选。"""
    if not s:
        return 0.0
    total = 0
    cjk = 0
    for c in s:
        if c.isspace():
            continue
        total += 1
        o = ord(c)
        # 基本汉字 + 扩展A + 兼容汉字
        if (0x4E00 <= o <= 0x9FFF) or (0x3400 <= o <= 0x4DBF) or (0xF900 <= o <= 0xFAFF):
            cjk += 1
    return cjk / total if total else 0.0

def _is_mojibake(s: str) -> bool:
    """粗略判断 s 是否像 mojibake（含大量拉丁扩展/生僻符号但不像正常文本）。"""
    if not s:
        return False
    # 含替换符 → 一定坏
    if "\ufffd" in s:
        return True
    # 含大量 Latin-1 扩展区字符（如 ä½ å¥½）→ 典型 latin-1 mojibake
    latin_like = sum(1 for c in s if 0x80 <= ord(c) <= 0x024F)
    if latin_like and latin_like / max(1, len(s)) > 0.3:
        return True
    # 含大量 CJK 兼容/生僻区字符（如 蝸ｯ蟇ｹ蝠頑弍）→ 典型 gbk mojibake
    rare_cjk = sum(1 for c in s if 0x3400 <= ord(c) <= 0x4DBF
                   or 0xF900 <= ord(c) <= 0xFAFF
                   or 0x20000 <= ord(c) <= 0x2FFFF)
    if rare_cjk and rare_cjk / max(1, len(s)) > 0.3:
        return True
    return False

def smart_decode(data: bytes) -> str:
    """
    兼容多种情况：
    1. data 是原始 UTF-8 字节 → 直接 UTF-8 解
    2. data 是 "UTF-8 字节被 Latin-1 显示后再 encode" 的产物 → latin-1 mojibake 修复
    3. data 是 "UTF-8 字节被 GBK 解后再 encode" 的产物 → gbk mojibake 修复
    4. data 是 GBK/Big5 等中文编码原始字节 → 按顺序尝试
    """
    # 先拿 UTF-8 候选
    utf8_str = None
    try:
        utf8_str = data.decode("utf-8")
    except UnicodeDecodeError:
        pass

    if utf8_str is not None:
        # bugfix: zbar 有时把 UTF-8 字节按 Shift_JIS 解释后重新编码返回,
        # 中文识别成生僻汉字+半角假名(如 "二维码工具" -> "莠檎ｻｴ遐∝…"),
        # 且表面汉字占比正常, 不触发 _is_mojibake。
        # 反向修复: 按 cp932 重新编码, 若能严格读回 UTF-8 且中文占比更高则采用
        try:
            sjis_fixed = utf8_str.encode("cp932").decode("utf-8")
            # 半角假名(U+FF61-FF9F)是 SJIS 误读的强特征, 用于修复
            # 纯字母/数字内容(如 é -> ﾃｩ)这类汉字占比不变的乱码
            has_hankana = any("\uff61" <= ch <= "\uff9f" for ch in utf8_str)
            if (sjis_fixed != utf8_str
                    and (_cjk_ratio(sjis_fixed) > _cjk_ratio(utf8_str)
                         or (has_hankana and "\ufffd" not in sjis_fixed))):
                return sjis_fixed
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
        # 若 UTF-8 解出来像乱码，尝试 mojibake 修复
        if _is_mojibake(utf8_str):
            # latin/cp1252 双层编码方向：能重新读回 UTF-8 基本即可信
            # (纯 ASCII 不会进这里；正常带重音符号的文本读不回 UTF-8)
            for codec in ("cp1252", "latin-1"):
                try:
                    latin_fixed = utf8_str.encode(codec, "ignore").decode("utf-8")
                    if latin_fixed:
                        return latin_fixed
                except (UnicodeEncodeError, UnicodeDecodeError):
                    continue
            # gbk 方向：修复结果汉字占比明显更高才采用
            try:
                gbk_fixed = utf8_str.encode("gbk", "ignore").decode("utf-8", "ignore")
                if (gbk_fixed and "\ufffd" not in gbk_fixed
                        and _cjk_ratio(gbk_fixed)
                        > _cjk_ratio(utf8_str) + 0.1):
                    return gbk_fixed
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass

        if "\ufffd" not in utf8_str:
            return utf8_str

    # 原始字节本身就是 GBK/Big5 等编码的情况
    for enc in ("gb18030", "gbk", "big5", "shift_jis"):
        try:
            s = data.decode(enc)
            if "\ufffd" not in s and not _is_mojibake(s):
                return s
        except (UnicodeDecodeError, UnicodeError):
            continue

    return data.decode("utf-8", errors="replace")


def make_qr_image(link: str) -> "Image.Image":
    """按工具统一参数生成二维码（UTF-8 字节写入、H 级纠错、白底黑块）。"""
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10, border=4)
    qr.add_data(link.encode("utf-8"))
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


def decode_qr_image(img: "Image.Image") -> list:
    """识别图片中所有二维码，返回文本列表；未识别到返回空列表。"""
    if zbar_decode is None:
        raise RuntimeError("缺少 pyzbar 库，请安装：pip install pyzbar")
    results = zbar_decode(img)
    if not results:
        # 放大重试：用 NEAREST 避免插值灰边导致误识别
        big = img.resize((img.width * 2, img.height * 2), Image.NEAREST)
        results = zbar_decode(big)
    return [smart_decode(r.data) for r in results]


def safe_filename(name: str, maxlen: int = 48) -> str:
    """把内容清洗成 Windows 合法文件名（含设备保留名兜底）。"""
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")[:maxlen].strip(" .")
    name = name or "qr"
    if name.split(".")[0].upper() in {
            "CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10))}:
        name = "_" + name
    return name


def parse_input_file(path: str) -> list:
    """读取清单：TXT 每行一条；CSV/TSV 取每行首个非空单元格并跳过表头。"""
    ext = os.path.splitext(path)[1].lower()
    with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as f:
        if ext in (".csv", ".tsv"):
            items, first = [], True
            for row in csv.reader(f, delimiter="\t" if ext == ".tsv" else ","):
                cell = next((c.strip() for c in row if c.strip()), "")
                if not cell:
                    continue
                if first and cell.lower() in TABLE_HEADERS:
                    first = False
                    continue
                first = False
                items.append(cell)
            return items
        return [ln.strip() for ln in f if ln.strip()]


def parse_drop_paths(widget, data: str) -> list:
    """解析拖拽数据（Tcl list，可能含多个带花括号的路径）。

    不能用 tk.splitlist：它会把 Windows 路径里的反斜杠当 Tcl 转义符吃掉
    （C:\\Temp\\a.png -> C:Tempa.png）。这里只按花括号/空白分词，原样保留路径。
    """
    data = (data or "").strip()
    if not data:
        return []
    parts, buf, in_brace = [], [], False
    for ch in data:
        if ch == "{" and not in_brace:
            in_brace, buf = True, []
        elif ch == "}" and in_brace:
            parts.append("".join(buf))
            buf, in_brace = [], False
        elif in_brace:
            buf.append(ch)
        elif ch.isspace():
            if buf:
                parts.append("".join(buf))
                buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))
    parts = [p for p in parts if p]
    # 兼容未加花括号但含空格的单个路径
    if len(parts) > 1 and os.path.isfile(" ".join(parts)):
        parts = [" ".join(parts)]
    return parts


def default_out_dir() -> str:
    return os.path.join(os.path.expanduser("~"), "Desktop", DEFAULT_OUT_NAME)


def _rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def _load_ttf(px, bold):
    """加载微软雅黑（UI 字面），失败时逐级回退。"""
    candidates = [
        ("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc", 1),
        ("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc", 0),
        ("C:/Windows/Fonts/simhei.ttf" if bold else "C:/Windows/Fonts/simsun.ttc", 0),
        ("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf", 0),
    ]
    for path, idx in candidates:
        try:
            return ImageFont.truetype(path, px, index=idx)
        except Exception:
            continue
    return ImageFont.load_default()


def setup_style(root, S):
    """tkk 只保留输入框样式；按钮/卡片均为自绘圆角控件。"""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure(".", background=BG, foreground=TEXT, font=(FONT, 10),
                    selectbackground=ACCENT, selectforeground="#FFFFFF")
    style.configure("TEntry", fieldbackground="#FFFFFF", foreground=TEXT,
                    insertcolor=TEXT, bordercolor=BORDER,
                    lightcolor=BORDER, darkcolor=BORDER,
                    padding=round(4 * S), selectbackground=ACCENT,
                    selectforeground="#FFFFFF")
    style.map("TEntry",
              bordercolor=[("focus", ACCENT)],
              lightcolor=[("focus", ACCENT)],
              darkcolor=[("focus", ACCENT)],
              fieldbackground=[("readonly", "#FFFFFF")],
              foreground=[("readonly", TEXT)])


def set_app_icon(root):
    """运行时生成一枚二维码风格的应用图标，无需外部文件。"""
    try:
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, size - 1, size - 1], radius=14, fill=ACCENT)
        d.rounded_rectangle([7, 7, size - 8, size - 8], radius=7, fill="#FFFFFF")
        dark = "#1E3A8A"
        for x, y in ((13, 13), (37, 13), (13, 37)):
            d.rectangle([x, y, x + 13, y + 13], fill=dark)
            d.rectangle([x + 3, y + 3, x + 10, y + 10], fill="#FFFFFF")
            d.rectangle([x + 5, y + 5, x + 8, y + 8], fill=dark)
        for x, y in ((37, 37), (45, 37), (37, 45), (45, 45), (29, 45), (45, 29)):
            d.rectangle([x, y, x + 4, y + 4], fill=dark)
        root.iconphoto(True, ImageTk.PhotoImage(img))
    except Exception:
        pass


class UI:
    """用 PIL 渲染圆角/阴影/文字位图资源（超采样抗锯齿）。"""

    BTN_STYLES = {
        "primary": {
            "normal":  (ACCENT, ACCENT, "#FFFFFF", 0),
            "hover":   (ACCENT_HOVER, ACCENT_HOVER, "#FFFFFF", 0),
            "pressed": (ACCENT_ACTIVE, ACCENT_ACTIVE, "#FFFFFF", 1),
        },
        "secondary": {
            "normal":  ("#FCFDFF", "#E2E7F0", "#3D4759", 0),
            "hover":   ("#F3F6FB", "#D5DEEB", "#2A3242", 0),
            "pressed": ("#ECF1F8", "#CFD9E8", "#2A3242", 1),
        },
    }

    def __init__(self, root, S):
        self.root = root
        self.S = S
        self.dpi = root.winfo_fpixels("1i")
        self.SS = 4  # 超采样倍率
        self._fonts = {}
        self._dots = {}
        self._chips = {}
        self._placeholder = None

    def P(self, n):
        return round(n * self.S)

    def font(self, pt, bold=False):
        key = (pt, bold)
        if key not in self._fonts:
            px = max(8, round(pt * self.dpi / 72))
            self._fonts[key] = _load_ttf(px, bold)
        return self._fonts[key]

    # --- 底层渲染 ---
    def _base(self, w, h, color):
        img = Image.new("RGBA", (w * self.SS, h * self.SS), _rgb(color) + (255,))
        return img, ImageDraw.Draw(img)

    def _down(self, img, w, h):
        return img.resize((w, h), Image.LANCZOS)

    # --- 卡片背景：白色圆角 + 柔和投影 ---
    def card_bg(self, w, h, radius, margin):
        W, H = w + 2 * margin, h + 2 * margin
        SS = self.SS
        alpha = Image.new("L", (W * SS, H * SS), 0)
        d = ImageDraw.Draw(alpha)
        d.rounded_rectangle(
            [margin * SS, (margin + self.P(2)) * SS,
             (margin + w) * SS, (margin + self.P(2) + h) * SS],
            radius=radius * SS, fill=255)
        alpha = alpha.filter(ImageFilter.GaussianBlur(self.P(2.5) * SS))
        alpha = alpha.point(lambda v: int(v * 0.10))
        base = Image.new("RGBA", (W * SS, H * SS), _rgb(BG) + (255,))
        shadow = Image.new("RGBA", (W * SS, H * SS), (15, 23, 42, 255))
        shadow.putalpha(alpha)
        base.alpha_composite(shadow)
        d2 = ImageDraw.Draw(base)
        d2.rounded_rectangle(
            [margin * SS, margin * SS, (margin + w) * SS, (margin + h) * SS],
            radius=radius * SS, fill=_rgb(CARD) + (255,),
            outline=_rgb(BORDER) + (255,), width=SS)
        out = base.resize((W, H), Image.LANCZOS).convert("RGB")
        return ImageTk.PhotoImage(out, master=self.root)

    # --- 预览区背景 ---
    def preview_bg(self, size):
        img, d = self._base(size, size, CARD)
        d.rounded_rectangle([0, 0, size * self.SS - 1, size * self.SS - 1],
                            radius=PREV_R * self.SS, fill=_rgb(FIELD) + (255,),
                            outline=_rgb(FIELD_BORDER) + (255,), width=self.SS)
        out = self._down(img, size, size).convert("RGB")
        return ImageTk.PhotoImage(out, master=self.root)

    # --- 按钮：三态圆角位图（文字 1x 绘制保持锐利） ---
    def button_states(self, text, kind, w, pt=10):
        h = self.P(30)
        f = self.font(pt, kind == "primary")
        out = {}
        for state, (fill, border, fg, dy) in self.BTN_STYLES[kind].items():
            img, d = self._base(w, h, CARD)
            d.rounded_rectangle([0, 0, w * self.SS - 1, h * self.SS - 1],
                                radius=BTN_R * self.SS, fill=_rgb(fill) + (255,),
                                outline=_rgb(border) + (255,), width=self.SS)
            small = self._down(img, w, h).convert("RGB")
            ImageDraw.Draw(small).text((w / 2, h / 2 + dy), text, font=f,
                                       fill=fg, anchor="mm")
            out[state] = ImageTk.PhotoImage(small, master=self.root)
        return out

    # --- 标题序号圆角徽标 ---
    def chip(self, num):
        if num not in self._chips:
            s = self.P(22)
            img, d = self._base(s, s, CARD)
            d.rounded_rectangle([0, 0, s * self.SS - 1, s * self.SS - 1],
                                radius=self.P(7) * self.SS,
                                fill=_rgb(ACCENT) + (255,))
            small = self._down(img, s, s).convert("RGB")
            ImageDraw.Draw(small).text((s / 2, s / 2 + self.S / 2), str(num),
                                       font=self.font(10, True),
                                       fill="#FFFFFF", anchor="mm")
            self._chips[num] = ImageTk.PhotoImage(small, master=self.root)
        return self._chips[num]

    # --- 预览区占位图形（二维码风格） ---
    def placeholder(self):
        if self._placeholder is None:
            s = self.P(36)
            SS = self.SS
            img, d = self._base(s, s, FIELD)
            c = _rgb(PLACEHOLDER) + (255,)
            lw = max(2, round(s * 0.09)) * SS
            f = round(s * 0.30)
            m = round(s * 0.10)
            for x, y in ((m, m), (s - m - f, m), (m, s - m - f)):
                d.rounded_rectangle([x * SS, y * SS, (x + f) * SS, (y + f) * SS],
                                    radius=4 * SS, outline=c, width=lw)
                cxy = x + f // 2
                r = f * 0.16
                d.rectangle([(cxy - r) * SS, (cxy - r) * SS,
                             (cxy + r) * SS, (cxy + r) * SS], fill=c)
            for dx, dy in ((0.56, 0.56), (0.70, 0.56), (0.84, 0.56),
                           (0.56, 0.70), (0.70, 0.70), (0.56, 0.84)):
                r = s * 0.055
                d.ellipse([(s * dx - r) * SS, (s * dy - r) * SS,
                           (s * dx + r) * SS, (s * dy + r) * SS], fill=c)
            small = self._down(img, s, s).convert("RGB")
            self._placeholder = ImageTk.PhotoImage(small, master=self.root)
        return self._placeholder

    # --- 状态栏圆点 ---
    def dot(self, color):
        if color not in self._dots:
            s = max(5, self.P(8))
            img, d = self._base(s, s, CARD)
            d.ellipse([0, 0, s * self.SS - 1, s * self.SS - 1],
                      fill=_rgb(color) + (255,))
            self._dots[color] = ImageTk.PhotoImage(
                self._down(img, s, s).convert("RGB"), master=self.root)
        return self._dots[color]


class Btn(tk.Label):
    """自绘圆角按钮：悬停/按下三态 + 按下微沉降。"""

    def __init__(self, master, ui, text, command, kind="secondary",
                 width=None, pt=10):
        self.command = command
        if width is None:
            width = int(ui.font(pt, kind == "primary").getlength(text)) + ui.P(22)
        self.images = ui.button_states(text, kind, width, pt)
        super().__init__(master, image=self.images["normal"], bd=0,
                         bg=CARD, cursor="hand2", highlightthickness=0)
        self._down = False
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self._enabled = True

    def _show(self, state):
        self.configure(image=self.images[state])

    def set_enabled(self, on: bool):
        """批量任务运行时禁用按钮（Label 的 state=disabled 不拦截事件，故自行守卫）。"""
        self._enabled = bool(on)
        self.configure(cursor="hand2" if self._enabled else "arrow")
        if not self._enabled:
            self._down = False
            self._show("normal")

    def _on_enter(self, _e):
        if self._enabled and not self._down:
            self._show("hover")

    def _on_leave(self, _e):
        self._down = False
        self._show("normal")

    def _on_press(self, _e):
        if not self._enabled:
            return
        self._down = True
        self._show("pressed")

    def _on_release(self, e):
        if not self._down or not self._enabled:
            return
        self._down = False
        inside = (0 <= e.x < self.winfo_width()
                  and 0 <= e.y < self.winfo_height())
        self._show("hover" if inside else "normal")
        if inside and self.command:
            self.command()


class BatchWindow:
    """批量转码主窗口（程序的唯一窗口，直接以 Tk 根窗口为界面）。

    页签一 文本 → 二维码：TXT/CSV/TSV 清单或手工多行输入，批量生成 PNG。
    页签二 二维码 → 文本：多选图片 / 文件夹 / 拖拽，批量识别并导出 CSV/TXT。
    任务用 after() 分片执行，界面保持响应，可中途取消。
    """

    CHUNK_GEN = 4      # 每次事件循环处理条数
    CHUNK_DEC = 2      # 解码较慢，每片少一些

    def __init__(self, root):
        self.win = win = root
        win.title("二维码工具 - 批量转码")
        win.configure(bg=BG)
        self.S = max(1.0, win.winfo_fpixels("1i") / 96.0)
        self.ui = UI(win, self.S)
        self.P = self.ui.P
        setup_style(win, self.S)
        set_app_icon(win)
        win.minsize(self.P(780), self.P(540))

        self._job = None
        self._running = False
        self._cancel = False
        self._kind = ""
        self.gen_rows = []
        self.dec_rows = []
        self.dec_paths = []
        self._dec_keys = set()
        self._gen_tasks = []
        self._gen_index = 0
        self._gen_used = set()
        self._gen_dir = ""
        self._gen_start = 1
        self._dec_index = 0

        self._init_style()
        self._build()
        w, h = self.P(900), self.P(630)
        x = max(0, (win.winfo_screenwidth() - w) // 2)
        y = max(0, (win.winfo_screenheight() - h) // 2)
        win.geometry(f"{w}x{h}+{x}+{y}")
        win.protocol("WM_DELETE_WINDOW", self.close)

        if TkinterDnD and hasattr(win, "drop_target_register"):
            try:
                win.drop_target_register(DND_FILES)
                win.dnd_bind("<<Drop>>", self.on_drop)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 样式与布局
    # ------------------------------------------------------------------
    def _init_style(self):
        P = self.P
        st = ttk.Style(self.win)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure("TNotebook", background=BG, borderwidth=0)
        # 当前页签更大更醒目（大字号加粗 + 更多留白 + 主题色），
        # 未选中的页签收敛成小号淡色，避免「反客为主」。
        st.configure("TNotebook.Tab", background="#E9EEF7", foreground=MUTED,
                     padding=(P(12), P(4)), font=(FONT, 9))
        st.map("TNotebook.Tab",
               background=[("selected", CARD), ("active", "#DDE8FA")],
               foreground=[("selected", ACCENT), ("active", TEXT)],
               font=[("selected", (FONT, 10, "bold"))],
               padding=[("selected", (P(16), P(6)))])
        st.configure("Treeview", background="#FFFFFF", fieldbackground="#FFFFFF",
                     foreground=TEXT, bordercolor=BORDER, rowheight=P(24),
                     font=(FONT, 9))
        st.configure("Treeview.Heading", background="#F1F5FB", foreground=MUTED,
                     font=(FONT, 9, "bold"), relief="flat", padding=(P(4), P(4)))
        st.map("Treeview", background=[("selected", "#DBEAFE")],
               foreground=[("selected", TEXT)])
        st.configure("TProgressbar", troughcolor="#EEF2F9", background=ACCENT,
                     bordercolor=BG, lightcolor=ACCENT, darkcolor=ACCENT,
                     thickness=P(8))
        st.configure("TCombobox", fieldbackground="#FFFFFF", background="#FFFFFF",
                     foreground=TEXT, arrowcolor=MUTED, bordercolor=BORDER)
        st.configure("TCheckbutton", background=CARD, foreground=TEXT,
                     font=(FONT, 9))
        st.map("TCheckbutton", background=[("active", CARD)])
        self._init_tick_checkbutton(st)

    def _init_tick_checkbutton(self, st):
        """clam 主题复选框选中时画的是叉号，换成蓝底白色对勾。"""
        size = max(14, self.P(16))
        s = size * 2

        def make(fill, outline, tick):
            im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            d.rounded_rectangle([2, 2, s - 3, s - 3], radius=s // 8,
                                fill=fill, outline=outline,
                                width=max(2, s // 16))
            if tick:
                d.line([(s * 0.28, s * 0.50), (s * 0.44, s * 0.66),
                        (s * 0.74, s * 0.28)],
                       fill="#FFFFFF", width=max(3, s // 10), joint="curve")
            return ImageTk.PhotoImage(im.resize((size, size), Image.LANCZOS),
                                     master=self.win)

        off = make(CARD, "#A9B4C8", False)
        hover = make("#F2F6FE", ACCENT, False)
        on = make(ACCENT, ACCENT, True)
        on_hover = make(ACCENT_HOVER, ACCENT_HOVER, True)
        # 必须持有引用，否则 PhotoImage 被 GC 后 Tcl 侧图片失效
        self._tick_images = (off, hover, on, on_hover)

        if "Tick.indicator" not in st.element_names():
            # 状态规则按「更具体」优先：悬停时同时带 selected+active，
            # 若把 ("active", hover) 放前面会先命中空框、把对勾盖掉。
            st.element_create("Tick.indicator", "image", off,
                              ("selected", "active", on_hover),
                              ("selected", on),
                              ("active", hover),
                              width=size, sticky="")
        layout = st.layout("TCheckbutton")

        def replace(node):
            out = []
            for name, opts in node:
                o = dict(opts)
                if "children" in o:
                    o["children"] = replace(o["children"])
                out.append(("Tick.indicator" if name == "Checkbutton.indicator"
                            else name, o))
            return out

        st.layout("Tick.TCheckbutton", replace(layout))
        st.configure("Tick.TCheckbutton", background=CARD, foreground=TEXT,
                     font=(FONT, 9), padding=2)
        st.map("Tick.TCheckbutton", background=[("active", CARD)])

    @staticmethod
    def _panel(parent):
        return tk.Frame(parent, bg=CARD, highlightthickness=1,
                        highlightbackground=BORDER, highlightcolor=BORDER, bd=0)

    @staticmethod
    def _label(parent, text, *, bold=False, muted=False, side=None, **kw):
        lbl = tk.Label(parent, text=text, bg=CARD,
                       fg=MUTED if muted else TEXT,
                       font=(FONT, 10, "bold") if bold else (FONT, 9),
                       highlightthickness=0, **kw)
        if side:
            lbl.pack(side=side)
        return lbl

    def _build(self):
        P = self.P
        outer = tk.Frame(self.win, bg=BG)
        outer.pack(fill="both", expand=True, padx=P(12), pady=P(10))
        nb = ttk.Notebook(outer)
        nb.pack(fill="both", expand=True)
        self.gen_frame = tk.Frame(nb, bg=BG)
        self.dec_frame = tk.Frame(nb, bg=BG)
        nb.add(self.gen_frame, text="  文本 → 二维码（批量生成）  ")
        nb.add(self.dec_frame, text="  二维码 → 文本（批量识别）  ")
        self.nb = nb
        self._build_gen(self.gen_frame)
        self._build_dec(self.dec_frame)
        foot = tk.Frame(outer, bg=BG)
        foot.pack(fill="x", pady=(P(8), 0))
        tk.Label(foot, text="提示：可直接把 TXT/CSV 清单、二维码图片或文件夹拖入本窗口",
                 bg=BG, fg=MUTED, font=(FONT, 9), anchor="w",
                 highlightthickness=0).pack(side="left")

    def _make_tree(self, parent, cols, heads, widths):
        P = self.P
        wrap = tk.Frame(parent, bg=CARD)
        wrap.pack(fill="both", expand=True, padx=P(10), pady=(0, P(2)))
        vy = ttk.Scrollbar(wrap, orient="vertical")
        vy.pack(side="right", fill="y")
        vx = ttk.Scrollbar(wrap, orient="horizontal")
        vx.pack(side="bottom", fill="x")
        tv = ttk.Treeview(wrap, columns=cols, show="headings",
                          selectmode="extended",
                          yscrollcommand=vy.set, xscrollcommand=vx.set)
        tv.pack(side="left", fill="both", expand=True)
        vy.configure(command=tv.yview)
        vx.configure(command=tv.xview)
        for c, h, w in zip(cols, heads, widths):
            tv.heading(c, text=h, anchor="w")
            tv.column(c, width=P(w), minwidth=P(30), anchor="w",
                      stretch=c not in ("idx", "status"))
        tv.tag_configure("ok", foreground=OK)
        tv.tag_configure("err", foreground=ERR)
        tv.tag_configure("wait", foreground=MUTED)
        return tv

    def _build_gen(self, parent):
        P = self.P
        parent.columnconfigure(0, minsize=P(288))
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(0, weight=1)
        left = self._panel(parent)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, P(5)), pady=P(8))
        right = self._panel(parent)
        right.grid(row=0, column=1, sticky="nsew", padx=(P(5), 0), pady=P(8))

        # ===== 左：输入清单 =====
        head = tk.Frame(left, bg=CARD)
        head.pack(fill="x", padx=P(10), pady=(P(10), P(6)))
        self._label(head, "输入内容", bold=True, side="left")
        self.gen_count_var = tk.StringVar(value="共 0 条")
        tk.Label(head, textvariable=self.gen_count_var, bg=CARD, fg=MUTED,
                 font=(FONT, 9), highlightthickness=0).pack(side="right")

        # 固定高度区块先打包到底部，窗口缩小时也不会把设置项挤没
        fixed = tk.Frame(left, bg=CARD)
        fixed.pack(side="bottom", fill="x")
        tk.Label(fixed, text="一行 = 一张二维码，空行自动忽略", bg=CARD,
                 fg=MUTED, font=(FONT, 9), anchor="w",
                 highlightthickness=0).pack(fill="x", padx=P(10), pady=(P(5), 0))
        row = tk.Frame(fixed, bg=CARD)
        row.pack(fill="x", padx=P(10), pady=P(6))
        Btn(row, self.ui, "导入 TXT/CSV", self.import_file, pt=9).pack(side="left")
        Btn(row, self.ui, "粘贴", self.paste_lines, pt=9).pack(side="left", padx=(P(5), 0))
        Btn(row, self.ui, "清空", self.clear_lines, pt=9).pack(side="left", padx=(P(5), 0))

        # ===== 左：输出位置设置 =====
        tk.Frame(fixed, bg=DIVIDER, height=1, highlightthickness=0,
                 bd=0).pack(fill="x", padx=P(10), pady=(0, P(8)))
        self._label(fixed, "输出位置设置", bold=True, anchor="w").pack(fill="x", padx=P(10))
        drow = tk.Frame(fixed, bg=CARD)
        drow.pack(fill="x", padx=P(10), pady=(P(6), 0))
        self.gen_dir_var = tk.StringVar(value=default_out_dir())
        ttk.Entry(drow, textvariable=self.gen_dir_var, font=(FONT, 9)).pack(
            side="left", fill="x", expand=True, padx=(0, P(5)))
        Btn(drow, self.ui, "浏览", self.choose_dir, pt=9).pack(side="left")

        orow = tk.Frame(fixed, bg=CARD)
        orow.pack(fill="x", padx=P(10), pady=(P(8), 0))
        self._label(orow, "命名", muted=True, side="left")
        self.gen_name_var = tk.StringVar(value="序号命名")
        ttk.Combobox(orow, textvariable=self.gen_name_var, state="readonly",
                     values=["序号命名", "内容命名"], width=9,
                     font=(FONT, 9)).pack(side="left", padx=P(5))
        self._label(orow, "前缀", muted=True).pack(side="left", padx=(P(8), 0))
        self.gen_prefix_var = tk.StringVar(value="qr_")
        ttk.Entry(orow, textvariable=self.gen_prefix_var, width=7,
                  font=(FONT, 9)).pack(side="left", padx=(P(4), 0))

        nrow = tk.Frame(fixed, bg=CARD)
        nrow.pack(fill="x", padx=P(10), pady=(P(8), P(12)))
        self._label(nrow, "起始序号", muted=True, side="left")
        self.gen_start_var = tk.StringVar(value="1")
        ttk.Entry(nrow, textvariable=self.gen_start_var, width=6,
                  font=(FONT, 9)).pack(side="left", padx=(P(5), 0))
        tk.Label(nrow, text="PNG · H 级纠错", bg=CARD, fg=MUTED,
                 font=(FONT, 9), highlightthickness=0).pack(side="right")

        # 输入区最后打包，占满剩余空间并可自由伸缩
        tw = tk.Frame(left, bg=CARD)
        tw.pack(side="top", fill="both", expand=True, padx=P(10))
        sb = ttk.Scrollbar(tw, orient="vertical")
        sb.pack(side="right", fill="y")
        self.gen_text = tk.Text(tw, wrap="none", undo=True, width=26, height=8,
                                font=(FONT, 10), bg="#FFFFFF", fg=TEXT,
                                insertbackground=TEXT, relief="flat", bd=0,
                                highlightthickness=1,
                                highlightbackground=BORDER,
                                highlightcolor=ACCENT, yscrollcommand=sb.set)
        self.gen_text.pack(side="left", fill="both", expand=True)
        self.gen_text.bind("<KeyRelease>", lambda _e: self.update_gen_count())
        sb.configure(command=self.gen_text.yview)

        # ===== 右：结果 =====
        rhead = tk.Frame(right, bg=CARD)
        rhead.pack(fill="x", padx=P(10), pady=(P(10), P(6)))
        self._label(rhead, "生成结果", bold=True, side="left")
        self.gen_status_var = tk.StringVar(value="就绪")
        tk.Label(rhead, textvariable=self.gen_status_var, bg=CARD,
                 fg=STATUS_FG, font=(FONT, 9), anchor="e",
                 highlightthickness=0).pack(side="right", fill="x", expand=True)
        self.gen_tree = self._make_tree(
            right, ("idx", "content", "status", "file"),
            ("#", "内容", "状态", "输出文件"), (36, 190, 90, 170))
        self.gen_prog = ttk.Progressbar(right, mode="determinate", maximum=100)
        self.gen_prog.pack(fill="x", padx=P(10), pady=(P(8), 0))
        row = tk.Frame(right, bg=CARD)
        row.pack(fill="x", padx=P(10), pady=P(10))
        self.gen_start_btn = Btn(row, self.ui, "开始生成", self.start_gen,
                                 kind="primary")
        self.gen_start_btn.pack(side="left")
        self.gen_cancel_btn = Btn(row, self.ui, "取消", self.cancel_job)
        self.gen_cancel_btn.pack(side="left", padx=(P(6), 0))
        Btn(row, self.ui, "打开目录", self.open_out_dir).pack(side="left", padx=(P(6), 0))
        Btn(row, self.ui, "导出清单", self.export_gen).pack(side="left", padx=(P(6), 0))
        self.gen_cancel_btn.set_enabled(False)

    def _build_dec(self, parent):
        P = self.P
        panel = self._panel(parent)
        panel.pack(fill="both", expand=True, padx=P(8), pady=P(8))

        bar = tk.Frame(panel, bg=CARD)
        bar.pack(fill="x", padx=P(10), pady=(P(10), P(6)))
        Btn(bar, self.ui, "添加图片", self.add_images, pt=9).pack(side="left")
        Btn(bar, self.ui, "添加文件夹", self.add_folder, pt=9).pack(side="left", padx=(P(5), 0))
        Btn(bar, self.ui, "移除选中", self.remove_selected, pt=9).pack(side="left", padx=(P(5), 0))
        Btn(bar, self.ui, "清空", self.clear_paths, pt=9).pack(side="left", padx=(P(5), 0))
        self.dec_rec_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="包含子文件夹", variable=self.dec_rec_var,
                        style="Tick.TCheckbutton").pack(side="left", padx=(P(12), 0))
        self.dec_count_var = tk.StringVar(value="共 0 张图片")
        tk.Label(bar, textvariable=self.dec_count_var, bg=CARD, fg=MUTED,
                 font=(FONT, 9), highlightthickness=0).pack(side="right")

        head = tk.Frame(panel, bg=CARD)
        head.pack(fill="x", padx=P(10), pady=(0, P(6)))
        self._label(head, "识别结果", bold=True, side="left")
        self.dec_status_var = tk.StringVar(value="就绪")
        tk.Label(head, textvariable=self.dec_status_var, bg=CARD,
                 fg=STATUS_FG, font=(FONT, 9), anchor="e",
                 highlightthickness=0).pack(side="right", fill="x", expand=True)
        self.dec_tree = self._make_tree(
            panel, ("idx", "file", "status", "result"),
            ("#", "文件名", "状态", "识别结果"), (36, 180, 100, 330))
        self.dec_prog = ttk.Progressbar(panel, mode="determinate", maximum=100)
        self.dec_prog.pack(fill="x", padx=P(10), pady=(P(8), 0))
        row = tk.Frame(panel, bg=CARD)
        row.pack(fill="x", padx=P(10), pady=P(10))
        self.dec_start_btn = Btn(row, self.ui, "开始识别", self.start_dec,
                                 kind="primary")
        self.dec_start_btn.pack(side="left")
        self.dec_cancel_btn = Btn(row, self.ui, "取消", self.cancel_job)
        self.dec_cancel_btn.pack(side="left", padx=(P(6), 0))
        Btn(row, self.ui, "复制结果", self.copy_dec_results).pack(side="left", padx=(P(6), 0))
        Btn(row, self.ui, "导出结果", self.export_dec).pack(side="left", padx=(P(6), 0))
        self.dec_cancel_btn.set_enabled(False)

    # ------------------------------------------------------------------
    # 通用状态
    # ------------------------------------------------------------------
    def _status(self, kind, text):
        (self.gen_status_var if kind == "gen" else self.dec_status_var).set(text)

    def _progress(self, kind, done, total):
        bar = self.gen_prog if kind == "gen" else self.dec_prog
        bar["value"] = 100.0 * done / max(1, total)
        self._status(kind, f"处理中 {done}/{total}")

    def _set_running(self, kind, on):
        self._running = on
        self._kind = kind if on else ""
        if on:
            self._cancel = False
        self.gen_start_btn.set_enabled(not on)
        self.dec_start_btn.set_enabled(not on)
        self.gen_cancel_btn.set_enabled(on and kind == "gen")
        self.dec_cancel_btn.set_enabled(on and kind == "dec")

    def _finish(self, kind, cancelled=False):
        if self._job is not None:
            try:
                self.win.after_cancel(self._job)
            except Exception:
                pass
            self._job = None
        rows = self.gen_rows if kind == "gen" else self.dec_rows
        total = len(self._gen_tasks) if kind == "gen" else len(self.dec_paths)
        ok = sum(1 for r in rows if r["tag"] == "ok")
        bad = len(rows) - ok
        if cancelled:
            msg = f"已取消：完成 {len(rows)}/{total} 项"
        else:
            msg = f"完成：成功 {ok} 项，失败 {bad} 项"
            if kind == "gen":
                msg += f" → {self._gen_dir}"
        self._set_running(kind, False)
        self._status(kind, msg)

    def cancel_job(self):
        if not self._running:
            return
        self._cancel = True
        self._status(self._kind, "正在取消…")

    def close(self):
        """关闭唯一主窗口 = 退出程序。"""
        self._cancel = True
        if self._job is not None:
            try:
                self.win.after_cancel(self._job)
            except Exception:
                pass
            self._job = None
        self._running = False
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # 页签一：文本 → 二维码
    # ------------------------------------------------------------------
    def gen_lines(self):
        return [ln.strip() for ln in
                self.gen_text.get("1.0", "end").splitlines() if ln.strip()]

    def update_gen_count(self):
        self.gen_count_var.set(f"共 {len(self.gen_lines())} 条")

    def insert_lines(self, lines):
        if not lines:
            return 0
        cur = self.gen_text.get("1.0", "end")
        if cur.strip() and not cur.endswith("\n"):
            self.gen_text.insert("end", "\n")
        self.gen_text.insert("end", "\n".join(lines) + "\n")
        self.gen_text.see("end")
        self.update_gen_count()
        return len(lines)

    def _import_paths(self, paths):
        """导入多个清单文件，返回 (成功路径列表, 总条数)。

        单个文件失败不影响其余文件，失败原因汇总成一次弹窗。
        """
        oks, total, errors = [], 0, []
        for path in paths:
            try:
                total += self.insert_lines(parse_input_file(path))
                oks.append(path)
            except Exception as e:
                errors.append(f"{os.path.basename(path)}：{e}")
        if errors:
            detail = "\n".join(errors[:8])
            if len(errors) > 8:
                detail += f"\n…另有 {len(errors) - 8} 个文件失败"
            messagebox.showerror(
                "导入失败" if not oks else "部分文件导入失败",
                f"成功 {len(oks)} 个文件，失败 {len(errors)} 个：\n{detail}",
                parent=self.win)
        return oks, total

    def import_file(self):
        if self._running:
            return
        paths = filedialog.askopenfilenames(
            parent=self.win, title="导入文本清单（可多选）",
            filetypes=TEXT_FILETYPES)
        if not paths:
            return
        oks, total = self._import_paths(paths)
        if not oks:
            self._status("gen", "导入失败")
            return
        detail = (os.path.basename(oks[0]) if len(oks) == 1
                  else f"{len(oks)} 个文件")
        self._status("gen", f"已导入 {total} 条：{detail}")

    def paste_lines(self):
        if self._running:
            return
        try:
            text = self.win.clipboard_get()
        except tk.TclError:
            text = ""
        if not text.strip():
            messagebox.showwarning("提示", "剪贴板中没有文字", parent=self.win)
            return
        self.insert_lines([ln.strip() for ln in text.splitlines() if ln.strip()])

    def clear_lines(self):
        if self._running:
            return
        self.gen_text.delete("1.0", "end")
        self.update_gen_count()

    def choose_dir(self):
        if self._running:
            return
        d = filedialog.askdirectory(parent=self.win, title="选择输出目录",
                                    initialdir=self.gen_dir_var.get())
        if d:
            self.gen_dir_var.set(d)

    def open_out_dir(self):
        d = self.gen_dir_var.get().strip()
        if not os.path.isdir(d):
            messagebox.showwarning("提示", "输出目录还不存在，请先生成二维码",
                                   parent=self.win)
            return
        try:
            os.startfile(d)          # Windows 资源管理器
        except Exception:
            webbrowser.open(d)

    def _unique_name(self, i, text):
        prefix = self.gen_prefix_var.get().strip()
        if self.gen_name_var.get() == "内容命名":
            base = safe_filename(text)
        else:
            base = f"{self._gen_start + i:03d}"
        name = f"{prefix}{base}.png"
        low, n = name.lower(), 2
        while low in self._gen_used:
            name = f"{prefix}{base}_{n}.png"
            low, n = name.lower(), n + 1
        self._gen_used.add(low)
        return name

    def start_gen(self):
        if self._running:
            return
        lines = self.gen_lines()
        if not lines:
            messagebox.showwarning("提示", "请先输入或导入要生成的内容（每行一条）",
                                   parent=self.win)
            return
        outdir = self.gen_dir_var.get().strip()
        if not outdir:
            messagebox.showwarning("提示", "请先选择输出目录", parent=self.win)
            return
        try:
            os.makedirs(outdir, exist_ok=True)
        except OSError as e:
            messagebox.showerror("输出目录不可用", str(e), parent=self.win)
            return
        try:
            start = max(0, int(self.gen_start_var.get().strip()))
        except ValueError:
            start = 1

        self._gen_dir = outdir
        self._gen_start = start
        self._gen_tasks = lines
        self._gen_index = 0
        self._gen_used = {f.lower() for f in os.listdir(outdir)}  # 不覆盖已有文件
        self.gen_rows = []
        self.gen_tree.delete(*self.gen_tree.get_children())
        self.gen_prog["value"] = 0
        self._set_running("gen", True)
        self.update_gen_count()
        self._gen_step()

    def _gen_step(self):
        if self._cancel:
            self._finish("gen", cancelled=True)
            return
        total = len(self._gen_tasks)
        for _ in range(self.CHUNK_GEN):
            if self._gen_index >= total:
                break
            i = self._gen_index
            text = self._gen_tasks[i]
            path, tag = "", "err"
            try:
                img = make_qr_image(text)
                path = os.path.join(self._gen_dir, self._unique_name(i, text))
                img.save(path, "PNG")
                status, tag = "成功", "ok"
            except Exception as e:
                status, path = f"失败：{e}", ""
            self.gen_rows.append({"idx": i + 1, "content": text,
                                  "status": status, "file": path, "tag": tag})
            self.gen_tree.insert("", "end",
                                 values=(i + 1, text, status, os.path.basename(path)),
                                 tags=(tag,))
            self._gen_index += 1
        self.gen_tree.yview_moveto(1)
        self._progress("gen", self._gen_index, total)
        if self._gen_index >= total:
            self._finish("gen")
        else:
            self._job = self.win.after(1, self._gen_step)

    def export_gen(self):
        self.export_rows(
            "批量生成清单", ("序号", "内容", "状态", "输出文件"),
            [(r["idx"], r["content"], r["status"], r["file"])
             for r in self.gen_rows], "gen")

    # ------------------------------------------------------------------
    # 页签二：二维码 → 文本
    # ------------------------------------------------------------------
    def add_images(self):
        if self._running:
            return
        paths = filedialog.askopenfilenames(parent=self.win,
                                            title="选择二维码图片（可多选）",
                                            filetypes=IMG_FILETYPES)
        if paths:
            self.add_paths(paths, switch=False)

    def add_folder(self):
        if self._running:
            return
        d = filedialog.askdirectory(parent=self.win, title="选择图片文件夹")
        if d:
            self.add_paths([d], switch=False)

    def _add_one(self, path):
        if not path.lower().endswith(IMAGE_EXTS):
            return 0
        key = os.path.normcase(os.path.abspath(path))
        if key in self._dec_keys:
            return 0
        self._dec_keys.add(key)
        self.dec_paths.append(path)
        return 1

    def add_paths(self, paths, switch=True):
        """加入图片（可传文件、文件夹混合）；返回新增数量。"""
        if self._running:
            return 0
        if switch:
            self.nb.select(self.dec_frame)
        added = 0
        for p in paths:
            if os.path.isdir(p):
                if self.dec_rec_var.get():
                    for root, _dirs, files in os.walk(p):
                        for f in sorted(files):
                            added += self._add_one(os.path.join(root, f))
                else:
                    try:
                        names = sorted(os.listdir(p))
                    except OSError:
                        names = []
                    for f in names:
                        added += self._add_one(os.path.join(p, f))
            else:
                added += self._add_one(p)
        self.refresh_dec_list()
        if added:
            self._status("dec", f"新增 {added} 张图片，共 {len(self.dec_paths)} 张")
        return added

    def refresh_dec_list(self):
        self.dec_tree.delete(*self.dec_tree.get_children())
        for i, p in enumerate(self.dec_paths, 1):
            self.dec_tree.insert("", "end",
                                 values=(i, os.path.basename(p), "待识别", ""),
                                 tags=("wait",))
        self.dec_count_var.set(f"共 {len(self.dec_paths)} 张图片")

    def remove_selected(self):
        if self._running:
            return
        sel = self.dec_tree.selection()
        if not sel:
            return
        for i in sorted({self.dec_tree.index(s) for s in sel}, reverse=True):
            p = self.dec_paths.pop(i)
            self._dec_keys.discard(os.path.normcase(os.path.abspath(p)))
        self.refresh_dec_list()
        self._status("dec", f"共 {len(self.dec_paths)} 张图片")

    def clear_paths(self):
        if self._running:
            return
        self.dec_paths.clear()
        self._dec_keys.clear()
        self.dec_rows = []
        self.refresh_dec_list()
        self.dec_prog["value"] = 0
        self._status("dec", "就绪")

    def start_dec(self):
        if self._running:
            return
        if not self.dec_paths:
            messagebox.showwarning("提示", "请先添加二维码图片或文件夹",
                                   parent=self.win)
            return
        if zbar_decode is None:
            messagebox.showerror("错误", "缺少 pyzbar 库，请安装：pip install pyzbar",
                                 parent=self.win)
            return
        self.dec_rows = []
        self.dec_tree.delete(*self.dec_tree.get_children())
        self.dec_prog["value"] = 0
        self._dec_index = 0
        self._set_running("dec", True)
        self._dec_step()

    def _dec_step(self):
        if self._cancel:
            self._finish("dec", cancelled=True)
            return
        total = len(self.dec_paths)
        for _ in range(self.CHUNK_DEC):
            if self._dec_index >= total:
                break
            i = self._dec_index
            path = self.dec_paths[i]
            name = os.path.basename(path)
            texts, err = [], ""
            try:
                with Image.open(path) as im:
                    img = im.convert("RGB")
                texts = decode_qr_image(img)
            except Exception as e:
                err = str(e)
            if texts:
                result = " | ".join(texts)
                status = "成功" if len(texts) == 1 else f"成功（{len(texts)} 个）"
                tag = "ok"
            else:
                result = ""
                status = f"失败：{err}" if err else "未识别到二维码"
                tag = "err"
            self.dec_rows.append({"idx": i + 1, "file": name, "path": path,
                                  "status": status, "result": result, "tag": tag})
            self.dec_tree.insert("", "end", values=(i + 1, name, status, result),
                                 tags=(tag,))
            self._dec_index += 1
        self.dec_tree.yview_moveto(1)
        self._progress("dec", self._dec_index, total)
        if self._dec_index >= total:
            self._finish("dec")
        else:
            self._job = self.win.after(1, self._dec_step)

    def copy_dec_results(self):
        texts = [r["result"] for r in self.dec_rows if r["result"]]
        if not texts:
            messagebox.showwarning("提示", "还没有可复制的识别结果", parent=self.win)
            return
        self.win.clipboard_clear()
        self.win.clipboard_append("\n".join(texts))
        self._status("dec", f"已复制 {len(texts)} 条识别结果")

    def export_dec(self):
        self.export_rows(
            "批量识别结果", ("序号", "文件名", "状态", "识别结果"),
            [(r["idx"], r["file"], r["status"], r["result"])
             for r in self.dec_rows], "dec")

    # ------------------------------------------------------------------
    # 导出 / 拖拽
    # ------------------------------------------------------------------
    def export_rows(self, title, header, rows, kind):
        if not rows:
            messagebox.showwarning("提示", "还没有可导出的结果", parent=self.win)
            return
        path = filedialog.asksaveasfilename(
            parent=self.win, title="导出结果", defaultextension=".csv",
            initialfile=title + ".csv",
            filetypes=[("CSV 表格（Excel 可直接打开）", "*.csv"),
                       ("文本文件", "*.txt")])
        if not path:
            return
        try:
            is_csv = os.path.splitext(path)[1].lower() == ".csv"
            with open(path, "w", encoding="utf-8-sig" if is_csv else "utf-8",
                      newline="") as f:
                if is_csv:
                    writer = csv.writer(f)
                    writer.writerow(header)
                    writer.writerows(rows)
                else:
                    clean = lambda v: str(v).replace("\t", " ").replace("\r", " ").replace("\n", " ")
                    f.write("\t".join(header) + "\n")
                    for r in rows:
                        f.write("\t".join(clean(v) for v in r) + "\n")
        except OSError as e:
            messagebox.showerror("导出失败", str(e), parent=self.win)
            return
        self._status(kind, f"已导出 {len(rows)} 条：{path}")
        messagebox.showinfo("导出完成", f"已导出 {len(rows)} 条记录：\n{path}",
                            parent=self.win)

    def on_drop(self, event):
        if self._running:
            messagebox.showinfo("提示", "任务进行中，请等待完成或先取消",
                                parent=self.win)
            return
        paths = parse_drop_paths(self.win, event.data)
        docs = [p for p in paths if os.path.splitext(p)[1].lower() in TEXT_EXTS]
        if docs:
            self.nb.select(self.gen_frame)
            oks, total = self._import_paths(docs)
            self._status("gen", f"已导入 {total} 条（{len(oks)}/{len(docs)} 个清单文件）")
        rest = [p for p in paths if p not in docs]
        if rest:
            self.add_paths(rest, switch=True)


def main():
    # 高 DPI 感知（必须在创建窗口前设置，文字和控件才会清晰）
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    # 使用 TkinterDnD.Tk 代替 tk.Tk 以支持拖拽 (如果可用)
    if TkinterDnD:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()

    root.withdraw()   # 构建期间隐藏，避免窗口闪现
    BatchWindow(root)
    root.deiconify()
    root.lift()
    root.focus_force()
    root.mainloop()


if __name__ == "__main__":
    main()
