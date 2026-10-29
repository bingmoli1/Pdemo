# -*- coding: utf-8 -*-
"""内部测试: 验证 tkinter 初始化后 zbar 仍能正常解码 + smart_decode 逻辑正确
smart_decode 直接复用 qr_gui.QRApp 的真实实现, 避免测试副本过期误报
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import tkinter as tk
from qr_gui import QRApp, TkinterDnD

# 初始化 tkinter（模拟 GUI 运行环境）
root = TkinterDnD.Tk() if TkinterDnD else tk.Tk()
root.withdraw()
if TkinterDnD:
    root.drop_target_register("DND_Files")
    print("TkinterDnD 注册成功")

from pyzbar import pyzbar
from PIL import Image
import qrcode

def smart_decode(data):
    return QRApp._smart_decode(data)


def make_qr(s):
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H,
                       box_size=10, border=4)
    qr.add_data(s.encode("utf-8"))
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")

# 测试往返: 中文
for s in ["你", "测试", "https://example.com/测试"]:
    img = make_qr(s)
    res = pyzbar.decode(img)
    assert res, f"zbar 未识别: {s}"
    out = smart_decode(res[0].data)
    assert out == s, f"{s!r} -> {out!r}"
    print(f"OK: {s!r} -> {out!r}")

# 测试 smart_decode: mojibake 与 SJIS 误读修复
raw = "中文测试abc".encode("utf-8")
sjis_case = raw.decode("latin-1").encode("utf-8")  # latin-1 双层编码
assert smart_decode(sjis_case) == "中文测试abc"
print("OK: latin-1 mojibake 修复")

gbk_raw = "中文测试abc".encode("gbk")
assert smart_decode(gbk_raw) == "中文测试abc"
print("OK: GBK 直接编码修复")

latin_only = "Æ‡é".encode("utf-8")
assert smart_decode(latin_only) == "Æ‡é", smart_decode(latin_only)
print("OK: 纯拉丁重音字符不被误修复")

# 边界: 空 / 无法解码内容不抛异常
print("边界:", repr(smart_decode(b"")), repr(smart_decode(b"abc")))
print("all tests passed")
root.destroy()
