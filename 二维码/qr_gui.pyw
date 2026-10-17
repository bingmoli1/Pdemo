# -*- coding: utf-8 -*-
"""
二维码工具（单页面图形界面版）

1. 链接 -> 二维码：窗口内预览、保存图片、默认浏览器打开查看二维码
2. 二维码 -> 链接：选择图片/粘贴剪贴板截图，解码出链接，
   手动点击按钮才会在默认浏览器打开、可复制链接

双击本文件即可运行（pythonw 关联，无命令行窗口）
依赖：qrcode pillow pyzbar（已安装），tkinter 为 Python 自带
"""

import os
import uuid
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import qrcode
from PIL import Image, ImageTk

try:
    from pyzbar.pyzbar import decode as zbar_decode
except ImportError:
    zbar_decode = None

try:
    from PIL import ImageGrab
except ImportError:
    ImageGrab = None

PREVIEW_SIZE = 280  # 预览图最大边长


class QRApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("二维码工具  ·  链接 ⇄ 二维码")
        root.resizable(False, False)

        self.qr_photo = None      # 防止预览图被回收
        self.src_photo = None
        self.qr_image = None      # 生成的二维码 PIL 图片
        self.last_link = ""       # 最近解码出的内容

        self._build_ui()
        self.set_status("就绪")

    # ---------------- 界面（全部内容在同一页面） ----------------
    def _build_ui(self):
        body = ttk.Frame(self.root)
        body.pack(fill="both", expand=True, padx=10, pady=8)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)

        # ========== 左列：链接 -> 二维码 ==========
        gbox = ttk.LabelFrame(body, text=" 链接 → 二维码 ")
        gbox.grid(row=0, column=0, sticky="n", padx=(0, 6))

        row1 = ttk.Frame(gbox)
        row1.pack(fill="x", padx=8, pady=(8, 4))
        self.link_var = tk.StringVar()
        entry = ttk.Entry(row1, textvariable=self.link_var)
        entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        entry.bind("<Return>", lambda e: self.gen_qr())
        ttk.Button(row1, text="生成", width=7, command=self.gen_qr).pack(side="left")

        self.qr_label = ttk.Label(gbox, text="生成的二维码将显示在这里",
                                  anchor="center", width=34)
        self.qr_label.pack(pady=8)

        row2 = ttk.Frame(gbox)
        row2.pack(pady=(0, 10))
        ttk.Button(row2, text="保存为图片", command=self.save_qr).pack(side="left", padx=5)

        # ========== 右列：二维码 -> 链接 ==========
        dbox = ttk.LabelFrame(body, text=" 二维码 → 链接 ")
        dbox.grid(row=0, column=1, sticky="n", padx=(6, 0))

        row3 = ttk.Frame(dbox)
        row3.pack(fill="x", padx=8, pady=(8, 4))
        ttk.Button(row3, text="选择图片…", command=self.pick_image).pack(side="left")
        if ImageGrab is not None:
            ttk.Button(row3, text="粘贴截图", command=self.paste_image).pack(side="left", padx=6)
        self.src_name_var = tk.StringVar(value="未选择")
        ttk.Label(row3, textvariable=self.src_name_var, foreground="#666").pack(
            side="left", fill="x", expand=True)

        self.src_label = ttk.Label(dbox, text="原图预览", anchor="center", width=34)
        self.src_label.pack(pady=(8, 6))

        row4 = ttk.Frame(dbox)
        row4.pack(fill="x", padx=8)
        self.result_var = tk.StringVar()
        ttk.Entry(row4, textvariable=self.result_var, state="readonly").pack(
            side="left", fill="x", expand=True)

        row5 = ttk.Frame(dbox)
        row5.pack(pady=(6, 10))
        ttk.Button(row5, text="浏览器打开链接", command=self.open_link).pack(side="left", padx=5)
        ttk.Button(row5, text="复制链接", command=self.copy_link).pack(side="left", padx=5)

        # ========== 状态栏 ==========
        self.status_var = tk.StringVar()
        ttk.Label(self.root, textvariable=self.status_var, anchor="w",
                  relief="sunken", foreground="#333").pack(fill="x", side="bottom")

    def set_status(self, text: str):
        self.status_var.set("  " + text)

    # ---------------- 链接 -> 二维码 ----------------
    def gen_qr(self):
        link = self.link_var.get().strip()
        if not link:
            messagebox.showwarning("提示", "请先输入链接")
            return
        if not link.lower().startswith(("http://", "https://")):
            link = "https://" + link
        try:
            qr = qrcode.QRCode(
                error_correction=qrcode.constants.ERROR_CORRECT_H,
                box_size=10, border=4)
            qr.add_data(link)
            qr.make(fit=True)
            self.qr_image = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        except Exception as e:
            messagebox.showerror("生成失败", str(e))
            return

        preview = self._scale(self.qr_image)
        self.qr_photo = ImageTk.PhotoImage(preview)
        self.qr_label.configure(image=self.qr_photo, text="")
        self.set_status(f"二维码已生成（{link}）")

    def save_qr(self):
        if self.qr_image is None:
            messagebox.showwarning("提示", "请先生成二维码")
            return
        path = filedialog.asksaveasfilename(
            title="保存二维码",
            defaultextension=".png",
            initialfile=f"qr_{uuid.uuid4().hex[:8]}.png",
            filetypes=[("PNG 图片", "*.png"), ("所有文件", "*.*")])
        if not path:
            return
        self.qr_image.save(path)
        self.set_status(f"已保存：{path}")

    # ---------------- 二维码 -> 链接 ----------------
    def pick_image(self):
        path = filedialog.askopenfilename(
            title="选择二维码图片",
            filetypes=[("图片文件", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"), ("所有文件", "*.*")])
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
        img = ImageGrab.grabclipboard()
        if img is None:
            messagebox.showwarning("提示", "剪贴板里没有图片，请先截图（如微信截图/QQ截图/Win+Shift+S）")
            return
        if isinstance(img, list):  # 复制的是文件
            try:
                img = Image.open(img[0]).convert("RGB")
            except Exception as e:
                messagebox.showerror("打开失败", str(e))
                return
        else:
            img = img.convert("RGB")
        self.src_name_var.set("剪贴板图片")
        self.decode(img)

    def decode(self, img: Image.Image):
        if zbar_decode is None:
            messagebox.showerror("错误", "缺少 pyzbar 库，请运行：pip install pyzbar")
            return
        self._show_preview(img)
        results = zbar_decode(img)
        # 识别失败时放大 2 倍再试一次（小图更容易识别）
        if not results:
            big = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
            results = zbar_decode(big)
        if not results:
            self.result_var.set("")
            self.last_link = ""
            messagebox.showerror("识别失败", "没有识别到二维码，请换一张更清晰的图片")
            self.set_status("识别失败")
            return

        text = self._smart_decode(results[0].data)
        self.last_link = text
        self.result_var.set(text)
        # 不自动打开链接，由用户手动点击按钮
        if text.lower().startswith(("http://", "https://")):
            self.set_status("解码成功：" + text + "（点击“浏览器打开链接”可打开）")
        else:
            self.set_status("解码成功：" + text)

    @staticmethod
    def _smart_decode(data: bytes) -> str:
        """智能解码二维码字节内容，避免中文乱码（UTF-8 / GBK / mojibake 自动识别）。

        pyzbar 会把 UTF-8 中文按 latin-1 解码再编码，产生 mojibake。
        正确还原：bytes.decode('utf-8') -> 乱码文本 -> .encode('latin-1')
                  -> 还原回原始 UTF-8 字节 -> .decode('utf-8') -> 正确中文
        """
        # 1) 直接按常见编码解码，先看是否有干净结果
        plain = None
        for enc in ("utf-8", "gbk", "big5", "shift_jis"):
            try:
                s = data.decode(enc)
                if "\ufffd" not in s:
                    plain = s
                    break
            except (UnicodeDecodeError, UnicodeError):
                continue

        # 2) mojibake 还原：data 通常是合法 UTF-8 字节，但内容是乱码文本
        try:
            mojibake = data.decode("utf-8")            # 得到乱码文本
            recovered = mojibake.encode("latin-1")      # 还原回原始 UTF-8 字节
            fixed = recovered.decode("utf-8")           # 得到正确文本
            if "\ufffd" not in fixed:
                return fixed
        except (UnicodeDecodeError, UnicodeError, UnicodeEncodeError):
            pass

        # 3) 若 mojibake 还原失败，退回直接解码结果
        if plain is not None:
            return plain

        # 4) 全部失败就宽松解码
        return data.decode("utf-8", errors="replace")

    def _show_preview(self, img: Image.Image):
        preview = self._scale(img)
        self.src_photo = ImageTk.PhotoImage(preview)
        self.src_label.configure(image=self.src_photo, text="")

    def open_link(self):
        if not self.last_link:
            messagebox.showwarning("提示", "还没有解码结果")
            return
        if not self.last_link.lower().startswith(("http://", "https://")):
            messagebox.showinfo("提示", "解码内容不是网址链接：\n" + self.last_link)
            return
        webbrowser.open(self.last_link)
        self.set_status("已用默认浏览器打开：" + self.last_link)

    def copy_link(self):
        if not self.last_link:
            messagebox.showwarning("提示", "还没有解码结果")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.last_link)
        self.set_status("已复制到剪贴板")

    # ---------------- 工具 ----------------
    @staticmethod
    def _scale(img: Image.Image) -> Image.Image:
        w, h = img.size
        ratio = min(PREVIEW_SIZE / w, PREVIEW_SIZE / h, 1.0)
        if ratio < 1.0:
            img = img.resize((max(1, int(w * ratio)), max(1, int(h * ratio))), Image.NEAREST)
        return img


def main():
    root = tk.Tk()
    try:
        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
    except Exception:
        pass
    QRApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()