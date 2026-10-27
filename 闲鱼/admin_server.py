# -*- coding: utf-8 -*-
"""商品管理页面（本地网页，仅本机可访问）：
双击「商品管理.bat」打开，浏览器里可以：
  - 增/删/改商品：名字、认单关键词、发货内容（整段多行）、发货话术
  - 每个商品配置多规格（规格名 + 规格关键词 + 该规格的发货内容）
  - 切换 演练模式/正式发货
  - 账号管理：添加 / 切换 / 删除闲鱼登录账号（每个账号一个独立的浏览器档案目录）
保存时写回 products.json（发货内容存在各商品的 cards 字段里，一整段文本）；
账号信息写回 config.json 的 accounts / current_account / user_data_dir。
改完需重启「启动自动发货.bat」生效。
"""
import json
import os
import shutil
import stat
import subprocess
import sys
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from stores import (DeliveredStore, account_dir_for, accounts_state, clean_account_name,
                    content_of, ensure_accounts, load_settings_and_products,
                    save_account_identity, save_products, save_settings)

BASE = Path(__file__).resolve().parent
ADMIN_HTML = BASE / "admin.html"
PORT = 8765
APP_VERSION = 2  # 与 admin.html 里的 PAGE_VERSION 保持一致；不一致说明有一个旧服务进程还在跑


def normalize_products(products):
    for p in products:
        p["name"] = str(p.get("name", "")).strip() or "未命名商品"
        p["match_keywords"] = [str(k).strip() for k in (p.get("match_keywords") or []) if str(k).strip()]
        p["enabled"] = bool(p.get("enabled", True))
        p["reply_text"] = str(p.get("reply_text", ""))
        p["cards"] = content_of(p.get("cards"))  # 一整段发货内容：原样保留换行，发货时整段发送
        p.pop("card_file", None)  # 旧字段：卡密内容现在直接存在商品里
        rules = []
        for r in p.get("variant_rules") or []:
            kws = [str(k).strip() for k in (r.get("keywords") or []) if str(k).strip()]
            if not kws:
                continue
            rules.append({
                "name": str(r.get("name", "")).strip(),
                "keywords": kws,
                "cards": content_of(r.get("cards")),
            })
        p["variant_rules"] = rules
    return products


def remove_tree(path: Path) -> None:
    """彻底删除一个目录（含其全部内容）。

    Windows 下浏览器档案里常有只读文件，直接 rmtree 会报错；
    这里遇到失败就先去掉只读属性再重试。删不掉会抛出异常，由调用方给出提示。
    """
    path = Path(path)

    def _retry(func, p, exc_info):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except Exception:
            raise

    try:
        shutil.rmtree(path, onexc=_retry)      # Python 3.12+
    except TypeError:
        shutil.rmtree(path, onerror=_retry)    # 兼容更老的 Python


def handle_account_action(data: dict):
    """返回 (ok, message)。action: add / switch / rename / delete / identify。"""
    action = str(data.get("action") or "")
    cfg = load_settings_and_products()   # 内部已 ensure_accounts
    accs = cfg.get("accounts") or []
    cur = cfg.get("current_account") or ""

    if action == "add":
        name = clean_account_name(data.get("name"))
        if not name:
            return False, "请填写账号备注名（可用中文、字母、数字）"
        if any(a["name"] == name for a in accs):
            return False, f"账号「{name}」已存在，换个名字吧"
        rel = account_dir_for(name, [a["dir"] for a in accs])
        (BASE / rel).mkdir(parents=True, exist_ok=True)
        accs.append({"name": name, "dir": rel})
        cfg["current_account"] = name
        cfg["user_data_dir"] = rel
        msg = f"已添加账号「{name}」并切换过去。启动自动发货后扫码登录这个号即可。"

    elif action == "switch":
        name = clean_account_name(data.get("name"))
        a = next((x for x in accs if x["name"] == name), None)
        if not a:
            return False, "账号不存在，请刷新页面"
        (BASE / a["dir"]).mkdir(parents=True, exist_ok=True)
        cfg["current_account"] = a["name"]
        cfg["user_data_dir"] = a["dir"]
        msg = f"已切换到「{a.get('nick') or a['name']}」，重启「启动自动发货.bat」生效。"

    elif action == "rename":
        old = clean_account_name(data.get("name"))
        new = clean_account_name(data.get("new_name"))
        a = next((x for x in accs if x["name"] == old), None)
        if not a:
            return False, "账号不存在，请刷新页面"
        if not new:
            return False, "请填写新的账号名（可用中文、字母、数字）"
        if new == old:
            return False, "新名字和原来一样，没有改动"
        if any(x["name"] == new for x in accs):
            return False, f"已经有账号叫「{new}」了，换个名字吧"
        a["name"] = new
        if was_cur := (old == cur):
            cfg["current_account"] = new
        # 发货去重记录是按账号名存的，改名时一并改文件名，避免改名后把老买家当新单重发
        try:
            old_f = DeliveredStore(BASE, old).path
            new_f = DeliveredStore(BASE, new).path
            if old_f.exists() and old_f != new_f and not new_f.exists():
                old_f.rename(new_f)
        except Exception:
            pass
        msg = (f"已把「{a.get('nick') or old}」改名为「{new}」"
               + ("（当前账号已同步）" if was_cur else "")
               + "，登录档案和登录状态不变。")

    elif action == "delete":
        name = clean_account_name(data.get("name"))
        a = next((x for x in accs if x["name"] == name), None)
        if not a:
            return False, "账号不存在，请刷新页面"
        was_current = (a["name"] == cur)
        rest = [x for x in accs if x["name"] != a["name"]]

        # 彻底删除账号的登录档案（不留归档，数据不可恢复）
        p = BASE / a["dir"]
        if p.exists():
            try:
                remove_tree(p)
            except Exception:
                return False, ("删除失败：这个账号的登录档案正在被占用（多半是自动发货还在运行）。"
                               "请先双击「停止自动发货.bat」关掉浏览器，再回来删除。")

        accs.remove(a)
        switched = ""
        if was_current:
            # 删的是当前账号：自动切到剩下的第一个；一个都不剩就清空，下次启动是全新登录
            cfg["current_account"] = rest[0]["name"] if rest else ""
            cfg["user_data_dir"] = rest[0]["dir"] if rest else ""
            if rest:
                switched = f"（已自动切换到「{rest[0].get('nick') or rest[0]['name']}」）"
            else:
                switched = "（已没有可用账号，添加新账号后重新扫码登录即可）"
        msg = f"已删除账号「{a.get('nick') or name}」{switched}，登录档案已彻底删除（不可恢复）"

    elif action == "identify":
        name = clean_account_name(data.get("name"))
        a = next((x for x in accs if x["name"] == name), None)
        if not a:
            return False, "账号不存在，请刷新页面"
        if not (BASE / a["dir"]).exists():
            return False, "这个账号还没登录过（档案目录不存在），请先启动自动发货扫码登录"
        try:
            proc = subprocess.run(
                [sys.executable, str(BASE / "account_probe.py"), a["dir"]],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=150,
            )
            out = (proc.stdout or "").strip()
            info = json.loads(out.splitlines()[-1]) if out else {}
        except Exception as e:
            return False, f"识别失败：{str(e)[:120]}"
        if not info.get("ok"):
            return False, info.get("error") or "识别失败，请稍后重试"
        save_account_identity(a["name"], info.get("uid", ""), info.get("nick", ""))
        who = info.get("nick") or "(未取到昵称)"
        return True, f"已识别：{who}（ID {info.get('uid') or '未知'}）"

    else:
        return False, "未知操作"

    save_settings(cfg)
    return True, msg


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")  # 页面/数据不缓存，F5 永远拿到最新版
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            self._send(200, ADMIN_HTML.read_bytes(), "text/html; charset=utf-8")
            return
        if path == "/api/state":
            cfg = load_settings_and_products()
            payload = {"version": APP_VERSION, "config": cfg, "accounts": accounts_state(cfg)}
            self._send(200, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            return
        self._send(404, b'{"error":"not found"}')

    def do_POST(self):
        path = self.path.split("?")[0]
        if path not in ("/api/save", "/api/account"):
            self._send(404, b'{"error":"not found"}')
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length).decode("utf-8"))

            if path == "/api/account":
                ok, msg = handle_account_action(data)
                body = {"ok": ok, "message": msg, "version": APP_VERSION} if ok else {"ok": False, "error": msg}
                self._send(200 if ok else 400, json.dumps(body, ensure_ascii=False).encode("utf-8"))
                return

            products = data.get("products")
            if not isinstance(products, list):
                raise ValueError("products 必须是列表")

            cfg = load_settings_and_products()
            cfg["products"] = normalize_products(products)
            if "dry_run" in data:
                cfg["dry_run"] = bool(data["dry_run"])
            save_products(cfg["products"])   # 商品 → products.json
            save_settings(cfg)               # 其余设置（含账号）→ config.json
            self._send(200, b'{"ok":true}')
        except Exception as e:
            self._send(500, json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False).encode("utf-8"))

    def log_message(self, *args):  # 静默访问日志
        pass


class AdminServer(ThreadingHTTPServer):
    # Windows 下 allow_reuse_address=True 会让第二个实例也能绑同一端口，
    # 导致旧版本进程抢走请求（页面看着"没更新"）。这里禁止重复绑定。
    allow_reuse_address = False
    daemon_threads = True


def _port_in_use() -> bool:
    """8765 上是否已经有一个在正常服务的实例。"""
    import socket
    s = socket.socket()
    s.settimeout(0.4)
    try:
        return s.connect_ex(("127.0.0.1", PORT)) == 0
    except Exception:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def main():
    url = f"http://127.0.0.1:{PORT}"
    srv = None
    waited = False
    for i in range(120):   # 刚重启时端口可能还在 TIME_WAIT（最多约 2 分钟），持续重试
        try:
            srv = AdminServer(("127.0.0.1", PORT), Handler)
            break
        except OSError:
            if _port_in_use():
                print(f"商品管理页面已经在运行了（{url}）。")
                print("已为你打开浏览器；如果页面还是旧的，请先把之前那个「商品管理」黑窗口关掉再重新双击本文件。")
                try:
                    webbrowser.open(url)
                except Exception:
                    pass
                return
            if i >= 4 and not waited:
                print("系统还没释放 8765 端口（上次关掉后要等一会儿），最多等 60 秒，请勿关闭本窗口…")
                waited = True
            time.sleep(0.5)
    if srv is None:
        print("启动失败：端口 8765 一直没释放。请稍等一分钟再双击本文件，或重启电脑后再试。")
        return
    print(f"商品管理页面已启动：{url}")
    print("浏览器即将自动打开；关闭本窗口即退出。")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    srv.serve_forever()


if __name__ == "__main__":
    main()
