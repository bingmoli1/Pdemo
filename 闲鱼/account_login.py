# -*- coding: utf-8 -*-
"""「＋ 新增账号」用：打开一个独立的可见浏览器窗口，等人工扫码登录，登录成功后自动登记账号。

用法（由商品管理页调用，也可手动跑）：
    python account_login.py "accounts/新账号1"

流程：
    用该账号自己的档案目录启动浏览器 → 打开闲鱼「消息」页 → 检测到已登录（cookie 里有 unb）
    → 读出真实昵称/用户ID → 写回 config.json 的 accounts，并把「当前使用」切到这个账号。

输出（最后一行）：
    {"ok": true, "account": "...", "nick": "...", "uid": "...", "dir": "..."}
出错时 ok=false 并带 error。
"""
import json
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def login_and_register(rel: str) -> dict:
    info = {"ok": False, "dir": rel, "account": "", "nick": "", "uid": "", "created": False,
           "error": ""}
    try:
        from browser_session import BrowserSession
        from stores import load_settings_and_products, register_account_login
    except ImportError as e:
        info["error"] = (f"缺少依赖：{e}。请执行 pip install -r requirements.txt "
                         "与 python -m playwright install chromium")
        return info

    cfg = load_settings_and_products()
    cfg["user_data_dir"] = rel
    cfg["headless"] = os.environ.get("XY_HEADLESS") == "1"      # 正常必须可见，才能扫码
    if os.environ.get("XY_LOGIN_WAIT"):
        cfg["login_wait_seconds"] = int(os.environ["XY_LOGIN_WAIT"])

    bs = BrowserSession(cfg)
    try:
        bs.launch()
        bs.open_im()
        if not bs.ensure_login():
            info["error"] = "等待扫码登录超时，请重新点「＋ 新增账号」再试一次"
            return info
        # cookie 落盘有延迟，多读几次再放弃
        uid = nick = ""
        for _ in range(5):
            bs.page.wait_for_timeout(1500)
            ident = bs.self_identity() or {}
            uid = str(ident.get("uid") or bs.self_user_id() or "").strip()
            nick = str(ident.get("nick") or "").strip()
            if uid:
                break
        if not (uid or nick):
            info["error"] = "登录成功但没读到账号信息（Cookie 里没有 unb），请重新点「＋ 新增账号」"
            return info
        res = register_account_login(rel, uid, nick)
        info.update(ok=True, uid=uid, nick=nick,
                    account=res.get("account") or "", created=bool(res.get("created")))
        return info
    except Exception as e:
        msg = str(e)
        low = msg.lower()
        if ("has been closed" in low or "target closed" in low or "browser closed" in low
                or "processsingleton" in low.replace(" ", "")):
            msg = "登录窗口被关闭了（或档案被别的程序占用），未记录账号，可重新点「＋ 新增账号」"
        elif "等待登录超时" in msg:
            msg = "等待扫码登录超时（10 分钟），未记录账号，可重新点「＋ 新增账号」再试"
        info["error"] = msg[:300]
        return info
    finally:
        try:
            bs.close()
        except Exception:
            pass


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "缺少账号档案目录参数"}, ensure_ascii=False))
        return
    print(json.dumps(login_and_register(sys.argv[1]), ensure_ascii=False))


if __name__ == "__main__":
    main()
