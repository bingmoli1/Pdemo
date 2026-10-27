# -*- coding: utf-8 -*-
"""商品管理页面（本地网页，仅本机可访问）：
双击「商品管理.bat」打开，浏览器里可以：
  - 增/删/改商品：名字、认单关键词、发货内容（整段多行）、发货话术
  - 每个商品配置多规格（规格名 + 规格关键词 + 该规格的发货内容）
  - 切换 演练模式/正式发货
保存时写回 products.json（发货内容存在各商品的 cards 字段里，一整段文本）。
改完需重启「启动自动发货.bat」生效。
"""
import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from stores import content_of, load_settings_and_products, save_products, save_settings

BASE = Path(__file__).resolve().parent
ADMIN_HTML = BASE / "admin.html"
PORT = 8765


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
            self._send(200, json.dumps({"config": load_settings_and_products()}, ensure_ascii=False).encode("utf-8"))
            return
        self._send(404, b'{"error":"not found"}')

    def do_POST(self):
        if self.path.split("?")[0] != "/api/save":
            self._send(404, b'{"error":"not found"}')
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            products = data.get("products")
            if not isinstance(products, list):
                raise ValueError("products 必须是列表")

            cfg = load_settings_and_products()
            cfg["products"] = normalize_products(products)
            if "dry_run" in data:
                cfg["dry_run"] = bool(data["dry_run"])
            save_products(cfg["products"])   # 商品 → products.json
            save_settings(cfg)               # 其余设置 → config.json
            self._send(200, b'{"ok":true}')
        except Exception as e:
            self._send(500, json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False).encode("utf-8"))

    def log_message(self, *args):  # 静默访问日志
        pass


def main():
    url = f"http://127.0.0.1:{PORT}"
    print(f"商品管理页面已启动：{url}")
    print("浏览器即将自动打开；关闭本窗口即退出。")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
