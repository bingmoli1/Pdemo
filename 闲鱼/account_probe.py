# -*- coding: utf-8 -*-
"""读取某个账号档案（浏览器 profile）当前登录的闲鱼账号，输出一行 JSON。

用法（由商品管理页调用，也可手动跑）：
    python account_probe.py browser_data
    python account_probe.py "accounts/二号店"

只启动浏览器读取本地 cookie，不访问任何网页，速度快、也不会触发风控。
输出：{"ok": true, "uid": "...", "nick": "...", "logged_in": true}
"""
import json
import sys
from pathlib import Path
from urllib.parse import unquote

BASE = Path(__file__).resolve().parent

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def read_identity(user_data_dir: str) -> dict:
    from playwright.sync_api import sync_playwright
    out = {"ok": True, "uid": "", "nick": "", "logged_in": False}
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir,
            headless=True,
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            viewport={"width": 1000, "height": 700},
            args=["--disable-blink-features=AutomationControlled"],
        )
        try:
            cookies = {c.get("name"): str(c.get("value") or "") for c in ctx.cookies()}
        finally:
            try:
                ctx.close()
            except Exception:
                pass
    uid = cookies.get("unb", "").strip()
    nick = ""
    for k in ("_nk_", "tracknick", "lgc"):   # 淘宝/闲鱼的昵称类 cookie
        v = (cookies.get(k) or "").strip().strip('"')
        if not v:
            continue
        try:
            v = unquote(v)
        except Exception:
            pass
        v = v.strip()
        if v and not v.isdigit():
            nick = v
            break
    out.update(uid=uid, nick=nick, logged_in=bool(uid))
    return out


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "缺少账号档案目录参数"}, ensure_ascii=False))
        return
    rel = sys.argv[1]
    path = Path(rel)
    if not path.is_absolute():
        path = (BASE / rel).resolve()
    if not path.exists():
        print(json.dumps({"ok": False, "error": "该账号还没有登录过（档案目录不存在）"}, ensure_ascii=False))
        return
    try:
        info = read_identity(str(path))
        if not info["logged_in"]:
            info["ok"] = False
            info["error"] = "没有读到登录信息：这个账号可能还没登录，请启动自动发货扫码登录一次"
        print(json.dumps(info, ensure_ascii=False))
    except Exception as e:
        msg = str(e)
        if "ProcessSingleton" in msg or "lock" in msg.lower() or "in use" in msg.lower():
            msg = "该账号的登录档案正在被占用，请先关闭自动发货程序再识别"
        print(json.dumps({"ok": False, "error": msg[:300]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
