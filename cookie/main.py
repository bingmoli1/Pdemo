"""
网站登录管理器 - 浏览器版（无界面窗口）
双击“打开网站列表.bat”后自动在默认浏览器中打开管理页面：
- 页面是网站列表：新增网站、登录并记录状态、打开网站（直接登录）
- 登录状态保存在每个网站独立的浏览器配置目录（Chrome/Edge）中

仅使用 Python 标准库，无需安装任何第三方依赖。
"""

import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import urllib.request
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# 打包成 exe 后，数据文件放在 exe 所在目录
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SITES_FILE = os.path.join(BASE_DIR, "sites.json")
PROFILE_DIR = os.path.join(BASE_DIR, "profiles")

HOST = "127.0.0.1"
PORT_RANGE = range(8317, 8327)
APP_MARKER = "site-login-manager"
TOKEN = secrets.token_hex(16)

BROWSER_ARGS = [
    "--no-first-run",
    "--no-default-browser-check",
    "--hide-crash-restore-bubble",
]


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def find_browser():
    """查找本机浏览器：优先 Chrome，其次 Edge"""
    if sys.platform == "win32":
        import winreg
        for exe in ("chrome.exe", "msedge.exe"):
            key_path = rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{exe}"
            for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    with winreg.OpenKey(root, key_path) as key:
                        path = winreg.QueryValue(key, None)
                    if path and os.path.exists(path):
                        return path
                except OSError:
                    pass
        candidates = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        ]
    else:
        candidates = []

    for exe in ("chrome", "google-chrome", "msedge", "microsoft-edge"):
        found = shutil.which(exe)
        if found:
            return found
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def normalize_url(text):
    """补全协议并简单校验，无效返回 None"""
    text = text.strip()
    if not text:
        return None
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", text):
        text = "https://" + text
    if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9+.-]*://\S+", text):
        return None
    return text


def host_key(url):
    """从 URL 提取可作为目录名/标识的域名"""
    host = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", "", url)
    host = host.split("/")[0].split("@")[-1]
    return re.sub(r"[^0-9A-Za-z._-]", "_", host)


def fatal(msg):
    """无控制台运行时的错误提示（弹窗）"""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, msg, "网站登录管理器", 0x10)
    except Exception:
        pass


# ---------------- 网站数据与操作 ----------------

class SiteStore:
    def __init__(self):
        self.sites = []   # [{url, added, recorded}]
        self.procs = {}   # host -> Popen
        self.browser_path = find_browser()
        self.load_sites()

    def load_sites(self):
        if not os.path.exists(SITES_FILE):
            return
        try:
            with open(SITES_FILE, "r", encoding="utf-8") as f:
                self.sites = json.load(f).get("sites", [])
        except Exception:
            self.sites = []

    def save_sites(self):
        with open(SITES_FILE, "w", encoding="utf-8") as f:
            json.dump({"sites": self.sites}, f, indent=2, ensure_ascii=False)

    def get_site(self, url):
        for site in self.sites:
            if site["url"] == url:
                return site
        return None

    def is_running(self, url):
        proc = self.procs.get(host_key(url))
        return bool(proc and proc.poll() is None)

    def launch_browser(self, url):
        """用该网站独立的浏览器配置目录打开网页"""
        profile = os.path.join(PROFILE_DIR, host_key(url))
        os.makedirs(profile, exist_ok=True)
        return subprocess.Popen(
            [self.browser_path, f"--user-data-dir={profile}", *BROWSER_ARGS, url])

    def add_site(self, url):
        url = normalize_url(url or "")
        if not url:
            return False, "网站地址无效，请输入类似 https://example.com 的地址"
        if self.get_site(url):
            return False, "该网站已在列表中"
        self.sites.append({"url": url, "added": now_str(), "recorded": ""})
        self.save_sites()
        return True, f"已添加 {url}，请先点一次【登录并记录状态】完成登录"

    def open_site(self, url):
        site = self.get_site(url)
        if not site:
            return False, "网站不存在"
        if not self.browser_path:
            return False, "未找到 Chrome 或 Edge 浏览器，请先安装"
        self.launch_browser(url)
        if site.get("recorded"):
            return True, f"正在使用已记录的登录状态打开 {url} …"
        return True, f"正在打开 {url}（尚未记录登录状态，可先点【登录并记录状态】）"

    def login_site(self, url):
        site = self.get_site(url)
        if not site:
            return False, "网站不存在"
        if not self.browser_path:
            return False, "未找到 Chrome 或 Edge 浏览器，请先安装"
        host = host_key(url)
        proc = self.procs.get(host)
        if proc and proc.poll() is None:
            return False, "该网站的浏览器窗口已打开，请在其中完成登录后关闭该窗口"
        proc = self.launch_browser(url)
        self.procs[host] = proc
        threading.Thread(target=self._watch_login, args=(site, host, proc),
                         daemon=True).start()
        return True, "浏览器已打开，请在网页中完成登录，然后关闭该浏览器窗口，状态会自动记录"

    def _watch_login(self, site, host, proc):
        """等待登录浏览器关闭，自动记录状态"""
        try:
            proc.wait()
        except Exception:
            pass
        self.procs.pop(host, None)
        site["recorded"] = now_str()
        self.save_sites()

    def clear_site(self, url):
        site = self.get_site(url)
        if not site:
            return False, "网站不存在"
        if self.is_running(url):
            return False, "该网站的浏览器窗口正在运行，请先关闭"
        shutil.rmtree(os.path.join(PROFILE_DIR, host_key(url)), ignore_errors=True)
        site["recorded"] = ""
        self.save_sites()
        return True, f"{url} 的登录状态已清除"

    def delete_site(self, url):
        site = self.get_site(url)
        if not site:
            return False, "网站不存在"
        if self.is_running(url):
            return False, "该网站的浏览器窗口正在运行，请先关闭"
        shutil.rmtree(os.path.join(PROFILE_DIR, host_key(url)), ignore_errors=True)
        self.sites.remove(site)
        self.save_sites()
        return True, f"已删除 {url}"


# ---------------- 页面 ----------------

PAGE_HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>网站登录管理器</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: "Microsoft YaHei", sans-serif; margin: 0; background: #f5f6f8; color: #333; }
  .wrap { max-width: 920px; margin: 30px auto; padding: 0 16px 40px; }
  .bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
  h1 { font-size: 22px; margin: 12px 0; }
  .btn { border: 0; border-radius: 6px; padding: 7px 12px; cursor: pointer; color: #fff; font-size: 13px; }
  .btn:hover { filter: brightness(1.08); }
  .add { background: #4caf50; font-size: 14px; font-weight: bold; }
  .exit { background: #607d8b; }
  .open { background: #9c27b0; } .login { background: #2196f3; }
  .clear { background: #ff9800; } .del { background: #f44336; }
  table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px;
          overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,.08); }
  th, td { padding: 10px 12px; text-align: left; font-size: 14px; border-bottom: 1px solid #f0f0f0; }
  th { background: #fafafa; }
  tr:hover td { background: #fbfbfd; }
  .url { word-break: break-all; }
  .ok { color: #1b7e1b; } .none { color: #999; } .run { color: #e67e22; }
  #tip { min-height: 20px; color: #555; font-size: 13px; margin: 12px 0; }
  .hint { color: #888; font-size: 13px; margin-bottom: 12px; }
  .empty { text-align: center; color: #999; padding: 30px 0; }
</style>
</head>
<body>
<div class="wrap">
  <div class="bar">
    <h1>网站登录管理器</h1>
    <div>
      <button class="btn add" onclick="addSite()">➕ 新增网站</button>
      <button class="btn exit" onclick="exitApp()">退出程序</button>
    </div>
  </div>
  <div class="hint">先点【🔑 登录并记录状态】登录一次，以后点【🚀 打开】即可直接登录。页面每 2 秒自动刷新。</div>
  <div id="tip"></div>
  <table>
    <thead><tr>
      <th style="width:30%">网站</th><th style="width:16%">登录状态</th>
      <th style="width:16%">记录时间</th><th style="width:16%">添加时间</th><th>操作</th>
    </tr></thead>
    <tbody id="rows"></tbody>
  </table>
</div>
<script>
const TOKEN = "__TOKEN__";
let sites = [];

function esc(s) { const d = document.createElement("div"); d.textContent = s == null ? "" : s; return d.innerHTML; }
function tip(t) { document.getElementById("tip").textContent = t || ""; }

async function api(path, body) {
  try {
    const r = await fetch(path, {method: "POST",
      headers: {"Content-Type": "application/json", "X-Token": TOKEN},
      body: JSON.stringify(body || {})});
    return await r.json();
  } catch (e) { return {ok: false, msg: "无法连接本地服务，程序可能已退出"}; }
}

async function refresh() {
  let data;
  try {
    const r = await fetch("/api/sites");
    data = await r.json();
  } catch (e) { return; }
  sites = data.sites || [];
  const rows = document.getElementById("rows");
  if (!sites.length) {
    rows.innerHTML = '<tr><td colspan="5" class="empty">列表为空，点击右上角【➕ 新增网站】添加</td></tr>';
    return;
  }
  rows.innerHTML = sites.map(s => {
    const status = s.running ? '<span class="run">🔄 浏览器已打开</span>'
        : (s.recorded ? '<span class="ok">✅ 已记录</span>' : '<span class="none">未登录</span>');
    return '<tr data-url="' + esc(s.url) + '">' +
      '<td class="url">' + esc(s.url) + '</td>' +
      '<td>' + status + '</td>' +
      '<td>' + esc(s.recorded || "—") + '</td>' +
      '<td>' + esc(s.added || "—") + '</td>' +
      '<td>' +
        '<button class="btn open" data-act="open">🚀 打开</button> ' +
        '<button class="btn login" data-act="login">🔑 登录并记录</button> ' +
        '<button class="btn clear" data-act="clear">🧹</button> ' +
        '<button class="btn del" data-act="del">🗑️</button>' +
      '</td></tr>';
  }).join("");
}

document.getElementById("rows").addEventListener("click", async e => {
  const b = e.target.closest("button");
  if (!b) return;
  const url = b.closest("tr").dataset.url;
  const act = b.dataset.act;
  if (act === "open") tip((await api("/api/open", {url})).msg);
  if (act === "login") tip((await api("/api/login", {url})).msg);
  if (act === "clear") {
    if (!confirm("清除该网站已记录的登录状态？（需要重新登录）")) return;
    tip((await api("/api/clear", {url})).msg);
  }
  if (act === "del") {
    if (!confirm("删除该网站？（其记录的登录状态会一并删除）")) return;
    tip((await api("/api/delete", {url})).msg);
  }
  refresh();
});

async function addSite() {
  const url = prompt("请输入网站地址：", "https://");
  if (url === null) return;
  const r = await api("/api/add", {url});
  tip(r.msg);
  refresh();
}

async function exitApp() {
  if (!confirm("退出网站登录管理器？")) return;
  await api("/api/exit", {});
  tip("程序已退出，可以关闭此页面。");
}

setInterval(refresh, 2000);
refresh();
</script>
</body>
</html>
"""


# ---------------- HTTP 服务 ----------------

class Handler(BaseHTTPRequestHandler):
    store = None          # SiteStore，启动时注入
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass  # 静默访问日志

    def _send(self, code, data, content_type="application/json; charset=utf-8"):
        body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            page = PAGE_HTML.replace("__TOKEN__", TOKEN).encode("utf-8")
            self._send(200, page, "text/html; charset=utf-8")
        elif self.path == "/api/sites":
            self._send(200, {
                "app": APP_MARKER,
                "sites": [dict(s, running=self.store.is_running(s["url"]))
                          for s in self.store.sites],
            })
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.headers.get("X-Token") != TOKEN:
            return self._send(403, {"ok": False, "msg": "forbidden"})
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return self._send(400, {"ok": False, "msg": "请求格式错误"})
        url = body.get("url", "")

        if self.path == "/api/add":
            ok, msg = self.store.add_site(url)
        elif self.path == "/api/open":
            ok, msg = self.store.open_site(url)
        elif self.path == "/api/login":
            ok, msg = self.store.login_site(url)
        elif self.path == "/api/clear":
            ok, msg = self.store.clear_site(url)
        elif self.path == "/api/delete":
            ok, msg = self.store.delete_site(url)
        elif self.path == "/api/exit":
            self._send(200, {"ok": True, "msg": "程序已退出"})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        else:
            return self._send(404, {"ok": False, "msg": "接口不存在"})
        self._send(200, {"ok": ok, "msg": msg})


def probe_existing():
    """已有一个本程序实例在运行则返回其端口"""
    for port in PORT_RANGE:
        try:
            with urllib.request.urlopen(f"http://{HOST}:{port}/api/sites", timeout=0.5) as r:
                if json.loads(r.read().decode("utf-8")).get("app") == APP_MARKER:
                    return port
        except Exception:
            continue
    return None


def main():
    port = probe_existing()
    if port is not None:
        webbrowser.open(f"http://{HOST}:{port}/")
        return

    store = SiteStore()
    Handler.store = store

    httpd = None
    for p in PORT_RANGE:
        try:
            httpd = ThreadingHTTPServer((HOST, p), Handler)
            port = p
            break
        except OSError:
            continue
    if httpd is None:
        fatal(f"端口 {PORT_RANGE.start}-{PORT_RANGE.stop - 1} 均被占用，无法启动。")
        return

    url = f"http://{HOST}:{port}/"
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
