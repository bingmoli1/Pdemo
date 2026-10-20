# -*- coding: utf-8 -*-

"""
二维码互转 GUI 工具
1. 链接 -> 二维码：输入内容解析。保存图片、自定义预览二维码
2. 二维码 -> 链接：选择图片/粘贴前缀拖入图片，解析出内容，
   点击链接按钮在浏览器打开。可复制链接
"""

import os
import time
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

# 尝试安装 tkinterdnd2 以支持拖拽
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    TkinterDnD = None

PREVIEW_SIZE = 280  # 预览图最大尺寸

class QRApp:
    def __init__(self, root):
        self.root = root
        root.title("二维码工具")
        root.resizable(False, False)
        root.withdraw()          # 暂时隐藏，避免闪烁
        self.qr_photo = None      # 缓存预览图以防止被GC
        self.src_photo = None
        self.qr_image = None      # 生成的最终 PIL 图像
        self.last_link = ""       # 最近解码出的字符串
        self._build_ui()
        self.set_status("就绪")
        self.root.update_idletasks()
        w = self.root.winfo_reqwidth()
        h = self.root.winfo_reqheight()
        x = (self.root.winfo_screenwidth() - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        # 居中后直接显示，无闪烁
        root.deiconify()         # 恢复显示
        
        # 注册拖拽事件（如果安装了 tkinterdnd2）
        if TkinterDnD:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind('<<Drop>>', self.handle_drop)

    def _do_gen_qr(self, link: str, verbose: bool):
        """生成二维码。verbose=True 时出错误弹窗，False 时静默（自动检测用）。"""
        try:
            qr = qrcode.QRCode(
                error_correction=qrcode.constants.ERROR_CORRECT_H,
                box_size=10, border=4)
            qr.add_data(link)
            qr.make(fit=True)
            self.qr_image = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        except Exception as e:
            if verbose:
                messagebox.showerror("生成失败", str(e))
            return

        preview = self._scale(self.qr_image)
        self.qr_photo = ImageTk.PhotoImage(preview)
        self.qr_label.configure(image=self.qr_photo, text="")
        self.set_status(f"二维码已生成：{link}")

    def _auto_decode(self, img: Image.Image, verbose: bool):
        """静默解码（不弹窗）。"""
        if zbar_decode is None:
            if verbose:
                messagebox.showerror("错误", "缺少 pyzbar 库，请安装：pip install pyzbar")
            return
        self._show_preview(img)
        results = zbar_decode(img)
        if not results:
            big = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
            results = zbar_decode(big)
        if not results:
            self.result_var.set("")
            self.last_link = ""
            self.set_status("识别失败")
            return
        text = self._smart_decode(results[0].data)
        self.last_link = text
        self.result_var.set(text)
        if text.lower().startswith(("http://", "https://")):
            self.set_status("识别成功：" + text + "（点击“浏览器打开链接”可打开）")
        else:
            self.set_status("识别成功：" + text)

    def gen_qr(self):
        link = self.link_var.get().strip()
        if not link:
            messagebox.showwarning("提示", "请输入链接")
            return
        self._do_gen_qr(link, verbose=True)

    def _build_ui(self):
        body = ttk.Frame(self.root)
        body.pack(fill="both", expand=True, padx=10, pady=8)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)

        # ========== 左列：链接 -> 二维码 ==========
        gbox = ttk.LabelFrame(body, text=" 转换为二维码 ")
        gbox.grid(row=0, column=0, sticky="n", padx=(0, 6))

        row1 = ttk.Frame(gbox)
        row1.pack(fill="x", padx=8, pady=(8, 4))
        self.link_var = tk.StringVar()
        entry = ttk.Entry(row1, textvariable=self.link_var)
        entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        entry.bind("<Return>", lambda e: self.gen_qr())
        ttk.Button(row1, text="生成", width=7, command=self.gen_qr).pack(side="left")

        self.qr_frame = tk.Frame(gbox, width=PREVIEW_SIZE, height=PREVIEW_SIZE,
                                 bg="white", relief="groove", bd=1)
        self.qr_frame.pack(pady=8)
        self.qr_frame.pack_propagate(False)
        self.qr_label = ttk.Label(self.qr_frame, text="生成的结果将显示在这里",
                                  anchor="center")
        self.qr_label.pack(fill="both", expand=True)

        row2 = ttk.Frame(gbox)
        row2.pack(pady=(0, 10))
        ttk.Button(row2, text="保存为图片", command=self.save_qr).pack(side="left", padx=5)
        ttk.Button(row2, text="复制二维码", command=self._copy_qr).pack(side="left", padx=5)

        # ========== 右列：二维码 -> 链接 ==========
        dbox = ttk.LabelFrame(body, text=" 二维码识别 ")
        dbox.grid(row=0, column=1, sticky="n", padx=(6, 0))

        row3 = ttk.Frame(dbox)
        row3.pack(fill="x", padx=8, pady=(8, 4))
        ttk.Button(row3, text="选择图片", command=self.pick_image).pack(side="left")
        if ImageGrab is not None:
            ttk.Button(row3, text="剪贴板图片", command=self.paste_image).pack(side="left", padx=6)
        self.src_name_var = tk.StringVar(value="未选择")
        ttk.Label(row3, textvariable=self.src_name_var, foreground="#666",
                  width=18, anchor="w").pack(side="left", padx=(6, 0))

        self.src_frame = tk.Frame(dbox, width=270, height=275,
                                  bg="white", relief="groove", bd=1)
        self.src_frame.pack(pady=(8, 6))
        self.src_frame.pack_propagate(False)
        self.src_label = ttk.Label(self.src_frame, text="原图预览", anchor="center")
        self.src_label.pack(fill="both", expand=True)

        row4 = ttk.Frame(dbox)
        row4.pack(fill="x", padx=20)
        self.result_var = tk.StringVar()
        self.result_entry = ttk.Entry(row4, textvariable=self.result_var, state="readonly", width=40)
        self.result_entry.pack(fill="x")

        row5 = ttk.Frame(dbox)
        row5.pack(pady=(6, 10))
        ttk.Button(row5, text="浏览器打开链接", command=self.open_link).pack(side="left", padx=5)
        ttk.Button(row5, text="复制链接", command=self.copy_link).pack(side="left", padx=5)

        # ========== 底部状态栏 ==========
        self.status_var = tk.StringVar()
        ttk.Label(self.root, textvariable=self.status_var, anchor="w",
                  relief="sunken", foreground="#333",
                  width=70).pack(fill="x", side="bottom")

    def set_status(self, text: str):
        self.status_var.set("  " + text)

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
        self.set_status(f"已保存至：{path}")

    def pick_image(self):
        path = filedialog.askopenfilename(
            title="选择二维码图片",
            filetypes=[("图像文件", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"), ("所有文件", "*.*")])
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
            messagebox.showwarning("提示", "剪贴板中没有图片，请先复制图片（如Win+Shift+S）")
            return
        if isinstance(img, list):
            try:
                img = Image.open(img[0]).convert("RGB")
            except Exception as e:
                messagebox.showerror("打开失败", str(e))
                return
        else:
            img = img.convert("RGB")
        self.src_name_var.set("剪贴板图片")
        self.decode(img)

    def handle_drop(self, event):
        """处理文件拖入事件"""
        path = event.data
        # 处理 Windows 下路径带 {} 的情况 (例如 {C:/Path With Space/img.png})
        if path.startswith('{') and path.endswith('}'):
            path = path[1:-1]
        
        try:
            img = Image.open(path).convert("RGB")
            self.src_name_var.set(os.path.basename(path))
            self.decode(img)
            self.set_status(f"拖入解析：{os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("解析失败", f"无法解析拖入的文件：{e}")

    def decode(self, img: Image.Image):
        if zbar_decode is None:
            messagebox.showerror("错误", "缺少 pyzbar 库，请安装：pip install pyzbar")
            return
        self._show_preview(img)
        results = zbar_decode(img)
        if not results:
            big = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
            results = zbar_decode(big)
        if not results:
            self.result_var.set("")
            self.last_link = ""
            messagebox.showerror("识别失败", "没有识别到二维码，请尝试更清晰的图片")
            self.set_status("识别失败")
            return

        text = self._smart_decode(results[0].data)
        self.last_link = text
        self.result_var.set(text)
        if text.lower().startswith(("http://", "https://")):
            self.set_status("识别成功：" + text + "（点击“浏览器打开链接”可打开）")
        else:
            self.set_status("识别成功：" + text)

    @staticmethod
    def _smart_decode(data: bytes) -> str:
        plain = None
        for enc in ("utf-8", "gbk", "big5", "shift_jis"):
            try:
                s = data.decode(enc)
                if "\ufffd" not in s:
                    plain = s
                    break
            except (UnicodeDecodeError, UnicodeError):
                continue
        try:
            mojibake = data.decode("utf-8")
            recovered = mojibake.encode("latin-1")
            fixed = recovered.decode("utf-8")
            if "\ufffd" not in fixed:
                return fixed
        except (UnicodeDecodeError, UnicodeError, UnicodeEncodeError):
            pass
        if plain is not None:
            return plain
        return data.decode("utf-8", errors="replace")

    def _show_preview(self, img: Image.Image):
        preview = self._scale(img)
        self.src_photo = ImageTk.PhotoImage(preview)
        self.src_label.configure(image=self.src_photo, text="")

    def open_link(self):
        if not self.last_link:
            messagebox.showwarning("提示", "还没有解码结果")
            return
        # 不判断格式，直接交给默认浏览器打开
        webbrowser.open(self.last_link)
        self.set_status("已使用默认浏览器打开：" + self.last_link)

    def _copy_qr(self):
        try:
            if not self.qr_image:
                messagebox.showwarning("提示", "请先生成二维码")
                return
            self._copy_image_to_clipboard(self.qr_image)
            self.set_status("二维码图片已复制到剪贴板，可直接 Ctrl+V 粘贴使用")
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

    def copy_link(self):
        if not self.last_link:
            messagebox.showwarning("提示", "还没有解码结果")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.last_link)
        self.set_status("已复制到剪贴板")

    @staticmethod
    def _scale(img: Image.Image) -> Image.Image:
        w, h = img.size
        ratio = min(PREVIEW_SIZE / w, PREVIEW_SIZE / h, 1.0)
        if ratio < 1.0:
            img = img.resize((max(1, int(w * ratio)), max(1, int(h * ratio))), Image.NEAREST)
        return img

def main():
    # 使用 TkinterDnD.Tk 代替 tk.Tk 以支持拖拽 (如果可用)
    if TkinterDnD:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
    
    try:
        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
    except Exception:
        pass
    root.withdraw()   # 创建后立即隐藏，彻底避免窗口闪现
    QRApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
