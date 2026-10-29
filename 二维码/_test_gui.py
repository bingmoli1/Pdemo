# -*- coding: utf-8 -*-
"""GUI 功能级测试: 实例化真实 QRApp(窗口隐藏), 逐项验证各按钮背后的方法。
不进入 mainloop, 用 update() 驱动事件循环。
"""
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageGrab
import qrcode

import qr_gui
from qr_gui import QRApp, TkinterDnD

# 弹窗替换为记录器, 避免模态对话框阻塞测试
_popups = []
messagebox.showinfo = lambda *a, **k: _popups.append(("info", a))
messagebox.showwarning = lambda *a, **k: _popups.append(("warn", a))
messagebox.showerror = lambda *a, **k: _popups.append(("error", a))
qr_gui.messagebox = messagebox

PASS = []
FAIL = []


def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print(f"[OK  ] {name}")
    else:
        FAIL.append((name, detail))
        print(f"[FAIL] {name}: {detail}")


root = TkinterDnD.Tk() if TkinterDnD else tk.Tk()
root.withdraw()

# 1) 应用初始化
try:
    app = QRApp(root)
    root.update()
    check("应用初始化/构建UI", True)
except Exception as e:
    check("应用初始化/构建UI", False, repr(e))
    root.destroy()
    sys.exit(1)

# 2) 生成二维码 (正常链接)
app.link_var.set("https://example.com/test")
app.gen_qr()
root.update()
check("生成二维码", app.qr_image is not None and app.qr_box.img_lbl.cget("image") != "")
check("生成状态栏 ok", "二维码已生成" in app.status_var.get(), app.status_var.get())

# 3) 生成空输入提示
app.link_var.set("")
before = app.status_var.get()
_popups.clear()
app.gen_qr()
root.update()
check("空输入弹出提示", len(_popups) == 1 and _popups[0][0] == "warn", repr(_popups))
check("空输入不生成", app.qr_image is not None)  # 保留旧图, 不崩溃

# 4) 生成中文内容
app.link_var.set("你好，二维码！")
app._do_gen_qr("你好，二维码！", verbose=True)
root.update()
check("生成中文二维码", app.qr_image is not None)

# 5) 保存到临时文件
saved_path = os.path.join(tempfile.gettempdir(), "qr_test_save.png")
orig_asksave = filedialog.asksaveasfilename
filedialog.asksaveasfilename = lambda **kw: saved_path
try:
    app.save_qr()
finally:
    filedialog.asksaveasfilename = orig_asksave
check("保存为图片", os.path.exists(saved_path) and Image.open(saved_path).size[0] > 0)

# 6) 缩放逻辑
big = Image.new("RGB", (800, 400), "white")
scaled = app._scale(big)
check("大图缩放", scaled.size[0] <= app.preview_max and scaled.size[1] <= app.preview_max,
      str(scaled.size))
small = Image.new("RGB", (50, 50), "white")
check("小图不放大", app._scale(small).size == (50, 50))

# 7) 解码: 生成->保存->解码 完整链路
msg = "https://example.com/往返?x=1"
img = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H,
                    box_size=10, border=4)
img.add_data(msg.encode("utf-8"))
img.make(fit=True)
img = img.make_image().convert("RGB")
app.decode(img)
root.update()
check("解码往返", app.last_link == msg, app.last_link)
check("解码结果写入输入框", app.result_var.get() == msg)

# 8) 解码失败路径 (无二维码的纯白图)
app.decode(Image.new("RGB", (300, 300), "white"))
root.update()
check("解码失败处理", app.last_link == "" and app.status_var.get() == "识别失败")

# 9) open_link / copy_link 空结果保护
app.last_link = ""
app.result_var.set("")
app.open_link()
app.copy_link()
check("空结果保护(不崩溃)", True)

# 10) copy_link 功能
app.decode(img)
app.copy_link()
check("复制链接", root.clipboard_get() == msg)

# 11) 复制二维码图片到剪贴板 (CF_DIB) -> 再从剪贴板读取验证
app._do_gen_qr("clipboard-test", verbose=True)
app._copy_qr()
root.update()
clip = ImageGrab.grabclipboard()
check("复制二维码图片", clip is not None and isinstance(clip, Image.Image),
      repr(type(clip)))

# 12) 粘贴非图片(文本) 不生效 —— 仅图片才处理
app.link_var.set("keep-me")      # 哨兵值：不应被改写
app.last_link = ""
app.result_var.set("")
root.clipboard_clear()
root.clipboard_append("pasted-text-123")
root.update()
_popups.clear()
app.paste_image()
root.update()
check("粘贴非图片(文本)不生效",
      app.link_var.get() == "keep-me"          # 输入框未被改写
      and app.last_link == ""                  # 未产生解码结果
      and len(_popups) == 1 and _popups[0][0] == "warn",
      f"link_var={app.link_var.get()!r} last_link={app.last_link!r} popups={_popups}")

# 13) 粘贴图片 (剪贴板为图片时解码)
app._do_gen_qr("paste-image-test", verbose=True)
app._copy_qr()
root.update()
check("复制后剪贴板含图片",
      isinstance(ImageGrab.grabclipboard(), Image.Image),
      repr(type(ImageGrab.grabclipboard())))
app.last_link = ""
app.paste_image()
root.update()
check("粘贴图片解码", app.last_link == "paste-image-test", app.last_link)

# 13b) 剪贴板为文件列表但不是图片 -> 不生效
orig_grab = ImageGrab.grabclipboard
txt_file = os.path.join(tempfile.gettempdir(), "qr_test_notimage.txt")
with open(txt_file, "w", encoding="utf-8") as f:
    f.write("not an image")
ImageGrab.grabclipboard = lambda: [txt_file]
try:
    app.link_var.set("keep-me2")
    app.last_link = ""
    _popups.clear()
    app.paste_image()
    root.update()
    check("剪贴板非图片文件不生效",
          app.link_var.get() == "keep-me2" and app.last_link == ""
          and len(_popups) == 1 and _popups[0][0] == "warn",
          f"link_var={app.link_var.get()!r} last_link={app.last_link!r} popups={_popups}")
finally:
    ImageGrab.grabclipboard = orig_grab

# 14) 拖入处理 (模拟 handle_drop)
drop_file = os.path.join(tempfile.gettempdir(), "qr_test_drop.png")
img.save(drop_file)
app.handle_drop(type("E", (), {"data": drop_file})())
root.update()
check("拖入解码", app.last_link == msg and app.src_name_var.get() == "qr_test_drop.png")

# 15) 拖入带花括号路径 (含空格路径)
spaced_dir = os.path.join(tempfile.gettempdir(), "qr test dir")
os.makedirs(spaced_dir, exist_ok=True)
spaced_file = os.path.join(spaced_dir, "qr pic.png")
img.save(spaced_file)
app.handle_drop(type("E", (), {"data": "{" + spaced_file + "}"})())
root.update()
check("拖入花括号路径", app.src_name_var.get() == "qr pic.png",
      app.src_name_var.get())

# 16) 拖入非图片
app.handle_drop(type("E", (), {"data": os.path.join(tempfile.gettempdir(),
               "not_exist_xyz.png")})())
root.update()
check("拖入非图片处理", "拖入的不是可解析的图片" in app.status_var.get())

# 17) smart_decode 边界: sjis 误读修复
raw = "中文测试abc".encode("utf-8")
sjis_case = raw.decode("latin-1").encode("utf-8")
out = QRApp._smart_decode(sjis_case)
check("SJIS/latin 双层乱码修复", out == "中文测试abc", out)

# 18) smart_decode: gbk 原始字节
out = QRApp._smart_decode("中文测试abc".encode("gbk"))
check("GBK 原始字节修复", out == "中文测试abc", out)

# 19) smart_decode: 空/短字节
check("smart_decode 空/短字节", QRApp._smart_decode(b"") == ""
      and QRApp._smart_decode(b"abc") == "abc")

# 20) 窗口几何: 两卡等高
gh = app.gcard.winfo_height()
dh = app.dcard.winfo_height()
check("双卡等高", gh == dh, f"{gh} vs {dh}")

# 清理
for p in (saved_path, drop_file, spaced_file, txt_file):
    try:
        os.remove(p)
    except OSError:
        pass
try:
    os.rmdir(spaced_dir)
except OSError:
    pass

print("=" * 60)
print(f"通过 {len(PASS)} 项, 失败 {len(FAIL)} 项")
for name, detail in FAIL:
    print(f"  FAIL: {name}: {detail}")
root.destroy()
sys.exit(1 if FAIL else 0)
