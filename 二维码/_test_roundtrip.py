# -*- coding: utf-8 -*-
"""完整测试: 生成二维码 -> 解码 -> smart_decode, 验证往返正确
smart_decode 直接复用 qr_gui.QRApp 的真实实现, 避免测试副本过期误报
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import qrcode
from PIL import Image
from pyzbar.pyzbar import decode as zbar_decode
from qr_gui import QRApp

smart_decode = QRApp._smart_decode


def make_qr(s):
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=4)
    qr.add_data(s.encode("utf-8"))
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


samples = [
    "你", "好", "中", "文", "汉", "字", "乱", "码", "测", "试",
    "你好世界", "中文abc123", "https://example.com/path?a=1&b=中文",
    "12345", "hello world", "二维码工具v2", "Æ‡é", "换行\ntest",
    "é", "好", "中", "那", "们", "工具", "ｦｧabc",
]
fails = []
for s in samples:
    img = make_qr(s)
    res = zbar_decode(img)
    if not res:
        fails.append((s, "<识别失败>"))
        print(f"[FAIL] {s!r:26} 解码失败")
        continue
    out = smart_decode(res[0].data)
    status = "OK  " if out == s else "FAIL"
    if out != s:
        fails.append((s, out))
    print(f"[{status}] {s!r:26} -> {out!r}")

print("=" * 60)
if fails:
    print(f"往返测试失败 {len(fails)} 项:")
    for s, out in fails:
        print(f"  {s!r} => {out!r}")
    sys.exit(1)
print(f"全部 {len(samples)} 项往返测试通过 ✓")
