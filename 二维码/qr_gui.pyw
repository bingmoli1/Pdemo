# -*- coding: utf-8 -*-

"""
二维码互转 GUI 工具
1. 链接 -> 二维码：输入内容解析。保存图片、自定义预览二维码
2. 二维码 -> 链接：选择图片/粘贴前缀拖入图片，解析出内容，
   点击链接按钮在浏览器打开。可复制链接
"""

import os
import uuid
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import qrcode
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageTk

try:
    from pyzbar.pyzbar import decode as zbar_decode
except ImportError:
    zbar_decode = None

try:
    from PIL import ImageGrab
except ImportError:
    ImageGrab = None

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

    def _show(self, state):
        self.configure(image=self.images[state])

    def _on_enter(self, _e):
        if not self._down:
            self._show("hover")

    def _on_leave(self, _e):
        self._down = False
        self._show("normal")

    def _on_press(self, _e):
        self._down = True
        self._show("pressed")

    def _on_release(self, e):
        if not self._down:
            return
        self._down = False
        inside = (0 <= e.x < self.winfo_width()
                  and 0 <= e.y < self.winfo_height())
        self._show("hover" if inside else "normal")
        if inside and self.command:
            self.command()


class PreviewBox(tk.Frame):
    """圆角预览区：底图 + 居中图片/占位提示。"""

    def __init__(self, master, ui, hint):
        size = ui.P(CONTENT_W)
        super().__init__(master, bg=CARD, width=size, height=size,
                         highlightthickness=0, bd=0)
        self.pack_propagate(False)
        self.photo = ui.preview_bg(size)
        bg = tk.Label(self, image=self.photo, bd=0, bg=CARD,
                      highlightthickness=0)
        bg.place(x=0, y=0)
        self.img_lbl = tk.Label(self, bg=FIELD, bd=0, highlightthickness=0)
        self.img_lbl.place(relx=0.5, rely=0.5, anchor="center")
        self.hint_frame = tk.Frame(self, bg=FIELD)
        self.hint_frame.place(relx=0.5, rely=0.5, anchor="center")
        tk.Label(self.hint_frame, image=ui.placeholder(), bg=FIELD, bd=0,
                 highlightthickness=0).pack()
        tk.Label(self.hint_frame, text=hint, bg=FIELD, fg=MUTED,
                 font=(FONT, 9), justify="center").pack(pady=(ui.P(6), 0))

    def show(self, photo):
        self.img_lbl.configure(image=photo)
        self.hint_frame.place_forget()


class Card(tk.Frame):
    """白色圆角卡片 + 投影，内容先自然布局再合成底图。"""

    def __init__(self, master, ui, num, title, subtitle):
        super().__init__(master, bg=BG, highlightthickness=0, bd=0)
        self.ui = ui
        self.M = ui.P(SHADOW_M)
        self.R = ui.P(CARD_R)
        inner = self.inner = tk.Frame(self, bg=CARD)
        inner.pack()  # 先用 pack 完成自然测量，finish 时改为 place

        head = tk.Frame(inner, bg=CARD)
        head.pack(fill="x", padx=ui.P(6), pady=(ui.P(10), ui.P(6)))
        tk.Label(head, image=ui.chip(num), bg=CARD, bd=0,
                 highlightthickness=0).pack(side="left", anchor="n")
        tf = tk.Frame(head, bg=CARD)
        tf.pack(side="left", padx=(ui.P(10), 0))
        tk.Label(tf, text=title, bg=CARD, fg=TEXT,
                 font=(FONT, 11, "bold")).pack(anchor="w")
        tk.Label(tf, text=subtitle, bg=CARD, fg=MUTED,
                 font=(FONT, 9)).pack(anchor="w", pady=(ui.P(1), 0))

        tk.Frame(inner, bg=DIVIDER, height=1,
                 highlightthickness=0, bd=0).pack(fill="x", padx=ui.P(6))

        self.body = tk.Frame(inner, bg=CARD)
        self.body.pack(fill="x", padx=ui.P(6), pady=ui.P(10))

    def finish(self, force_h=None):
        """内容布局完成后：量尺寸 -> 渲染圆角底图 -> 切换为 place。

        白底矩形比内容四周各大 R（圆角半径），inner 恰好内接于白底矩形内，
        内容不会盖住圆角、描边和阴影。force_h 用于多卡强制等高。
        """
        self.ui.root.update_idletasks()
        cw = self.winfo_reqwidth()
        ch = force_h or self.winfo_reqheight()
        rect_w = cw + 2 * self.R
        rect_h = ch + 2 * self.R
        self.card_photo = self.ui.card_bg(rect_w, rect_h, self.R, self.M)
        self.configure(width=rect_w + 2 * self.M, height=rect_h + 2 * self.M)
        self.pack_propagate(False)
        self.inner.forget()
        bg = tk.Label(self, image=self.card_photo, bg=BG, bd=0,
                      highlightthickness=0)
        bg.place(x=0, y=0)
        self.inner.place(x=self.M + self.R, y=self.M + self.R,
                         width=cw, height=ch)
        self.inner.lift(bg)


class QRApp:
    def __init__(self, root):
        self.root = root
        root.title("二维码工具")
        root.resizable(False, False)
        root.configure(bg=BG)
        root.withdraw()          # 暂时隐藏，避免闪烁
        # 高 DPI 缩放系数（未生效时为 1，行为与旧版一致）
        self.S = max(1.0, root.winfo_fpixels("1i") / 96.0)
        self.ui = UI(root, self.S)
        # 预览图片最大边长（预览框内留边）
        self.preview_max = self.ui.P(CONTENT_W - 20)
        setup_style(root, self.S)
        self._set_app_icon()
        self.qr_photo = None      # 缓存预览图以防止被GC
        self.src_photo = None
        self.qr_image = None      # 生成的最终 PIL 图像
        self.last_link = ""       # 最近解码出的字符串
        self._build_ui()
        self.root.update_idletasks()
        # 两张卡片强制等高（取自然高度较大者），整体更整齐
        card_h = max(self.gcard.winfo_reqheight(), self.dcard.winfo_reqheight())
        self.gcard.finish(card_h)
        self.dcard.finish(card_h)
        self.set_status("就绪")
        self.root.update_idletasks()
        w = self.root.winfo_reqwidth()
        h = self.root.winfo_reqheight()
        x = (self.root.winfo_screenwidth() - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        # 居中后直接显示，无闪烁
        root.deiconify()         # 恢复显示

        # 注册拖拽事件（如果安装了 tkinterdnd2 且根窗口支持）
        if TkinterDnD and hasattr(self.root, "drop_target_register"):
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind('<<Drop>>', self.handle_drop)

    # ------------------------------------------------------------------
    # 生成二维码
    # ------------------------------------------------------------------
    def _do_gen_qr(self, link: str, verbose: bool):
        """生成二维码。verbose=True 时出错误弹窗，False 时静默（自动检测用）。"""
        try:
            qr = qrcode.QRCode(
                error_correction=qrcode.constants.ERROR_CORRECT_H,
                box_size=10, border=4)
            # 关键：显式以 UTF-8 字节写入，避免不同 qrcode 版本对 str 的编码差异
            qr.add_data(link.encode("utf-8"))
            qr.make(fit=True)
            self.qr_image = qr.make_image(
                fill_color="black", back_color="white").convert("RGB")
        except Exception as e:
            if verbose:
                messagebox.showerror("生成失败", str(e))
            return

        preview = self._scale(self.qr_image, qr=True)
        self.qr_photo = ImageTk.PhotoImage(preview)
        self.qr_box.show(self.qr_photo)
        self.set_status(f"二维码已生成：{link}", "ok")

    def gen_qr(self):
        link = self.link_var.get().strip()
        if not link:
            messagebox.showwarning("提示", "请输入链接")
            return
        self._do_gen_qr(link, verbose=True)

    # ------------------------------------------------------------------
    # 解码公共逻辑
    # ------------------------------------------------------------------
    def _apply_decode_result(self, text: str):
        """把解码结果写入 UI 与状态栏。"""
        self.last_link = text
        self.result_var.set(text)
        if text.lower().startswith(("http://", "https://")):
            self.set_status("识别成功：" + text + "（点击“浏览器打开链接”可打开）", "ok")
        else:
            self.set_status("识别成功：" + text, "ok")

    def _decode_image(self, img: Image.Image, verbose: bool):
        """统一解码入口。verbose=True 时识别失败弹窗。"""
        if zbar_decode is None:
            if verbose:
                messagebox.showerror("错误", "缺少 pyzbar 库，请安装：pip install pyzbar")
            return

        self._show_preview(img)
        results = zbar_decode(img)
        if not results:
            # 放大重试：用 NEAREST 避免插值灰边导致误识别
            big = img.resize((img.width * 2, img.height * 2), Image.NEAREST)
            results = zbar_decode(big)
        if not results:
            self.result_var.set("")
            self.last_link = ""
            if verbose:
                messagebox.showerror("识别失败", "没有识别到二维码，请尝试更清晰的图片")
            self.set_status("识别失败", "err")
            return

        text = self._smart_decode(results[0].data)
        self._apply_decode_result(text)

    def decode(self, img: Image.Image):
        """用户主动选择/粘贴/拖入图片时调用（失败弹窗）。"""
        self._decode_image(img, verbose=True)

    # ------------------------------------------------------------------
    # 字节解码（核心：兼容多种 mojibake）
    # ------------------------------------------------------------------
    @staticmethod
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

    @staticmethod
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

    @staticmethod
    def _smart_decode(data: bytes) -> str:
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
                        and (QRApp._cjk_ratio(sjis_fixed) > QRApp._cjk_ratio(utf8_str)
                             or (has_hankana and "\ufffd" not in sjis_fixed))):
                    return sjis_fixed
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
            # 若 UTF-8 解出来像乱码，尝试 mojibake 修复
            if QRApp._is_mojibake(utf8_str):
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
                            and QRApp._cjk_ratio(gbk_fixed)
                            > QRApp._cjk_ratio(utf8_str) + 0.1):
                        return gbk_fixed
                except (UnicodeEncodeError, UnicodeDecodeError):
                    pass

            if "\ufffd" not in utf8_str:
                return utf8_str

        # 原始字节本身就是 GBK/Big5 等编码的情况
        for enc in ("gb18030", "gbk", "big5", "shift_jis"):
            try:
                s = data.decode(enc)
                if "\ufffd" not in s and not QRApp._is_mojibake(s):
                    return s
            except (UnicodeDecodeError, UnicodeError):
                continue

        return data.decode("utf-8", errors="replace")

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _set_app_icon(self):
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
            self.root.iconphoto(True, ImageTk.PhotoImage(img))
        except Exception:
            pass

    def _build_ui(self):
        ui = self.ui
        P = ui.P

        # ===== 底部状态栏（先打包，确保贴住窗口底边） =====
        bar = tk.Frame(self.root, bg=CARD, highlightthickness=0, bd=0)
        bar.pack(side="bottom", fill="x")
        self._dots = {k: ui.dot(c) for k, c in
                      (("info", ACCENT), ("ok", OK), ("warn", WARN), ("err", ERR))}
        self.status_dot = tk.Label(bar, image=self._dots["info"], bg=CARD,
                                   bd=0, highlightthickness=0)
        self.status_dot.pack(side="left", padx=(P(12), 0))
        self.status_var = tk.StringVar(value="就绪")
        tk.Label(bar, textvariable=self.status_var, bg=CARD, fg=STATUS_FG,
                 font=(FONT, 9), anchor="w",
                 highlightthickness=0).pack(
            side="left", fill="x", expand=True, padx=P(6), pady=P(5))
        tk.Frame(self.root, bg=DIVIDER, height=1,
                 highlightthickness=0, bd=0).pack(side="bottom", fill="x")

        # ===== 主体两列 =====
        body = tk.Frame(self.root, bg=BG, highlightthickness=0, bd=0)
        body.pack(fill="both", expand=True, padx=P(10), pady=P(8))
        body.columnconfigure(0, weight=1, uniform="col")
        body.columnconfigure(1, weight=1, uniform="col")

        gcard = Card(body, ui, 1, "链接 → 二维码", "输入文本，一键生成二维码")
        gcard.grid(row=0, column=0, sticky="nsew", padx=(0, P(4)))
        dcard = Card(body, ui, 2, "二维码 → 链接", "选图、粘贴或拖入图片识别")
        dcard.grid(row=0, column=1, sticky="nsew", padx=(P(4), 0))
        self.gcard, self.dcard = gcard, dcard

        # 行内按钮统一宽度（两枚等分一行）
        half = (P(CONTENT_W) - P(8)) // 2

        # ========== 左卡片：链接 -> 二维码 ==========
        row1 = tk.Frame(gcard.body, bg=CARD, highlightthickness=0, bd=0)
        row1.pack(fill="x")
        self.link_var = tk.StringVar()
        entry = ttk.Entry(row1, textvariable=self.link_var, font=(FONT, 10),
                          width=18)
        entry.pack(side="left", fill="x", expand=True, padx=(0, P(8)))
        entry.bind("<Return>", lambda e: self.gen_qr())
        Btn(row1, ui, "生成", self.gen_qr, kind="primary").pack(side="left")

        self.qr_box = PreviewBox(gcard.body, ui, "生成的二维码\n将显示在这里")
        self.qr_box.pack(pady=(P(10), 0))

        row2 = tk.Frame(gcard.body, bg=CARD, highlightthickness=0, bd=0)
        row2.pack(fill="x", pady=(P(10), 0))
        Btn(row2, ui, "保存为图片", self.save_qr, width=half).pack(
            side="left", padx=(0, P(8)))
        Btn(row2, ui, "复制二维码", self._copy_qr, width=half).pack(side="left")

        # ========== 右卡片：二维码 -> 链接 ==========
        row3 = tk.Frame(dcard.body, bg=CARD, highlightthickness=0, bd=0)
        row3.pack(fill="x")
        Btn(row3, ui, "选择图片", self.pick_image).pack(side="left")
        if ImageGrab is not None:
            Btn(row3, ui, "粘贴图片", self.paste_image).pack(
                side="left", padx=(P(8), 0))
        self.src_name_var = tk.StringVar(value="未选择")
        tk.Label(row3, textvariable=self.src_name_var, bg=CARD, fg=MUTED,
                 font=(FONT, 9), anchor="e", width=10,
                 highlightthickness=0).pack(side="right", fill="x", expand=True)

        self.src_box = PreviewBox(dcard.body, ui, "选择 / 粘贴 / 拖入\n二维码图片")
        self.src_box.pack(pady=(P(10), 0))

        row4 = tk.Frame(dcard.body, bg=CARD, highlightthickness=0, bd=0)
        row4.pack(fill="x", pady=(P(10), 0))
        tk.Label(row4, text="识别结果", bg=CARD, fg=MUTED, font=(FONT, 9),
                 highlightthickness=0).pack(side="left", padx=(0, P(8)))
        self.result_var = tk.StringVar()
        self.result_entry = ttk.Entry(row4, textvariable=self.result_var,
                                      state="readonly", font=(FONT, 10),
                                      width=18)
        self.result_entry.pack(side="left", fill="x", expand=True)

        row5 = tk.Frame(dcard.body, bg=CARD, highlightthickness=0, bd=0)
        row5.pack(fill="x", pady=(P(10), 0))
        Btn(row5, ui, "浏览器打开链接", self.open_link, kind="primary",
            width=half).pack(side="left", padx=(0, P(8)))
        Btn(row5, ui, "复制链接", self.copy_link, width=half).pack(side="left")

    def set_status(self, text: str, kind: str = "info"):
        self.status_var.set(text)
        self.status_dot.configure(image=self._dots.get(kind, self._dots["info"]))

    # ------------------------------------------------------------------
    # 按钮回调
    # ------------------------------------------------------------------
    def save_qr(self):
        if self.qr_image is None:
            messagebox.showwarning("提示", "请先生成二维码")
            return
        path = filedialog.asksaveasfilename(
            title="保存二维码",
            defaultextension=".png",
            initialfile=f"qr_{uuid.uuid4().hex[:8]}.png",
            filetypes=[("PNG 图像", "*.png"), ("所有文件", "*.*")])
        if not path:
            return
        self.qr_image.save(path)
        self.set_status(f"已保存至：{path}", "ok")

    def pick_image(self):
        path = filedialog.askopenfilename(
            title="选择二维码图片",
            filetypes=[("图像文件", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"),
                       ("所有文件", "*.*")])
        if not path:
            return
        try:
            img = Image.open(path).convert("RGB")
        except Exception as e:
            messagebox.showerror("打开失败", str(e))
            return
        self.src_name_var.set(os.path.basename(path))
        self.decode(img)

    def paste_image(self):
        """仅当剪贴板内容是真正的图片时才生效（送入解码识别）。

        其他任何内容（纯文本、非图片文件、空剪贴板）一律不处理：
        不生成二维码、不改写输入框，只提示“剪贴板中没有图片”。
        需要粘贴文本请直接用 Ctrl+V 粘到左侧输入框（Tk 输入框原生支持）。
        """
        try:
            clip = ImageGrab.grabclipboard()
        except Exception as e:
            messagebox.showerror("剪贴板不可用", str(e))
            return

        # 只认真正的图片：PIL 图像对象，或能被 PIL 打开的图片文件
        img = None
        if isinstance(clip, Image.Image):
            img = clip
        elif isinstance(clip, list):
            # 复制的是文件：逐个尝试，取第一个真正能作为图片打开的
            for p in clip:
                try:
                    img = Image.open(p)
                    break
                except Exception:
                    continue

        if img is None:
            # 不是图片 -> 不生效
            messagebox.showwarning(
                "提示", "剪贴板中没有图片，请先复制图片（如 Win+Shift+S 截图）")
            self.set_status("粘贴未生效：剪贴板内容不是图片", "warn")
            return

        try:
            img = img.convert("RGB")
        except Exception as e:
            messagebox.showerror("打开失败", str(e))
            return
        self.src_name_var.set("剪贴板图片")
        self.decode(img)

    def handle_drop(self, event):
        """处理文件拖入事件"""
        path = event.data
        # 处理 Windows 下路径带 {} 的情况
        if path.startswith('{') and path.endswith('}'):
            path = path[1:-1]

        try:
            img = Image.open(path).convert("RGB")
        except Exception:
            self.set_status(f"拖入的不是可解析的图片：{os.path.basename(path)}", "warn")
            return
        self.src_name_var.set(os.path.basename(path))
        self.decode(img)  # 识别结果状态放在后面，不被“拖入解析”覆盖

    def open_link(self):
        if not self.last_link:
            messagebox.showwarning("提示", "还没有解码结果")
            return
        webbrowser.open(self.last_link)
        self.set_status("已使用默认浏览器打开：" + self.last_link, "ok")

    def copy_link(self):
        if not self.last_link:
            messagebox.showwarning("提示", "还没有解码结果")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.last_link)
        self.set_status("已复制到剪贴板", "ok")

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------
    def _show_preview(self, img: Image.Image):
        preview = self._scale(img, qr=False)
        self.src_photo = ImageTk.PhotoImage(preview)
        self.src_box.show(self.src_photo)

    def _copy_qr(self):
        try:
            if not self.qr_image:
                messagebox.showwarning("提示", "请先生成二维码")
                return
            self._copy_image_to_clipboard(self.qr_image)
            self.set_status("二维码图片已复制到剪贴板，可直接 Ctrl+V 粘贴使用", "ok")
        except Exception as e:
            messagebox.showerror("复制失败", str(e))

    @staticmethod
    def _copy_image_to_clipboard(img: "Image.Image"):
        import io
        import ctypes
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="BMP")
        dib = buf.getvalue()[14:]
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
        user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
        user32.SetClipboardData.restype = ctypes.c_void_p
        CF_DIB = 8
        GMEM_MOVEABLE = 0x0002
        if not user32.OpenClipboard(0):
            raise RuntimeError("无法打开剪贴板")
        try:
            user32.EmptyClipboard()
            hGlobal = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(dib))
            if not hGlobal:
                raise RuntimeError("内存分配失败")
            pGlobal = kernel32.GlobalLock(hGlobal)
            if not pGlobal:
                kernel32.GlobalFree(hGlobal)
                raise RuntimeError("锁定内存失败")
            ctypes.memmove(pGlobal, dib, len(dib))
            kernel32.GlobalUnlock(hGlobal)
            if not user32.SetClipboardData(CF_DIB, hGlobal):
                kernel32.GlobalFree(hGlobal)
                raise RuntimeError("写入剪贴板失败")
        finally:
            user32.CloseClipboard()

    def _scale(self, img: Image.Image, qr: bool = False) -> Image.Image:
        """缩放到预览尺寸。二维码用 NEAREST 保持锐利，照片用 LANCZOS 更平滑。"""
        w, h = img.size
        ratio = min(self.preview_max / w, self.preview_max / h, 1.0)
        if ratio < 1.0:
            img = img.resize((max(1, int(w * ratio)), max(1, int(h * ratio))),
                             Image.NEAREST if qr else Image.LANCZOS)
        return img


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

    root.withdraw()   # 创建后立即隐藏，彻底避免窗口闪现
    QRApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
