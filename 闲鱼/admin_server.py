# -*- coding: utf-8 -*-
"""商品管理页面（本地网页，仅本机可访问）：
双击「商品管理.bat」打开，浏览器里可以：
  - 增/删/改商品：名字（填成闲鱼商品标题）、发货内容（整段多行）、发货话术
    匹配按"商品名/规格名与订单文字重合的字数"自动认商品与规格，无需填关键词
  - 每个商品配置多规格（规格名 + 该规格的发货内容）
  - 切换 演练模式/正式发货
  - 账号管理：新增（弹窗口扫码登录）/ 改名 / 切换 / 删除闲鱼登录账号
    （每个账号一个独立的浏览器档案目录）
  - 每个账号单独「启动 / 停止」自动发货：账号之间互不影响，可以同时跑多个
    （各自独立的登录档案、发货记录、日志文件，进程里只看得见自己这个账号）
保存时写回 products.json（发货内容存在各商品的 cards 字段里，一整段文本）；
账号信息写回 config.json 的 accounts / current_account / user_data_dir。
改完需在商品管理页对该账号「停止」后「启动」生效（或重启对应的自动发货实例）。
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
                    clear_run_pid, content_of, ensure_accounts, load_settings_and_products,
                    pid_alive, running_accounts, save_account_identity, save_products,
                    save_settings)

BASE = Path(__file__).resolve().parent
ADMIN_HTML = BASE / "admin.html"
PORT = 8765
APP_VERSION = 4  # 与 admin.html 里的 PAGE_VERSION 保持一致；不一致说明有一个旧服务进程还在跑
LOGIN_SCRIPT = BASE / "account_login.py"
RUN_SCRIPT = BASE / "auto_delivery.py"


def normalize_products(products):
    for p in products:
        p["name"] = str(p.get("name", "")).strip() or "未命名商品"
        p["enabled"] = bool(p.get("enabled", True))
        p["reply_text"] = str(p.get("reply_text", ""))
        p["cards"] = content_of(p.get("cards"))  # 一整段发货内容：原样保留换行，发货时整段发送
        p.pop("card_file", None)       # 旧字段：卡密内容现在直接存在商品里
        p.pop("match_keywords", None)  # 不再使用认单关键词，清理旧字段
        rules = []
        for r in p.get("variant_rules") or []:
            rname = str(r.get("name", "")).strip()
            if not rname:
                continue
            rules.append({
                "name": rname,
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


# ---------------- 新增账号：弹登录窗口，等扫码，自动登记 ----------------
_LOGIN_JOB = {"proc": None, "dir": "", "started": 0.0, "done": False, "result": None}
_PY_CACHE = {"exe": None}


def _python_has_playwright(exe: str) -> bool:
    try:
        r = subprocess.run([exe, "-c", "import playwright"],
                           capture_output=True, timeout=25)
        return r.returncode == 0
    except Exception:
        return False


def _candidate_pythons() -> list:
    """候选解释器：当前解释器 → 常见安装目录 → PATH（跳过 WindowsApps 存根）。"""
    cands = []
    if sys.executable:
        cands.append(sys.executable)
    home = Path(os.path.expanduser("~"))
    for base in (home / "AppData" / "Local" / "Programs" / "Python", Path("C:/Python")):
        try:
            if not base.exists():
                continue
            for d in sorted(base.glob("Python3*"), reverse=True):
                f = d / "python.exe"
                if f.exists():
                    cands.append(str(f))
        except Exception:
            pass
    for p in os.environ.get("PATH", "").split(os.pathsep):
        if not p or "WindowsApps" in p:
            continue
        f = Path(p) / "python.exe"
        if f.exists():
            cands.append(str(f))
    out, seen = [], set()
    for c in cands:
        k = str(c).lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(str(c))
    return out


def find_playwright_python() -> str:
    """找一个装了 playwright 的解释器（PATH 里默认的 python 未必装了）。"""
    if _PY_CACHE["exe"]:
        return _PY_CACHE["exe"]
    for c in _candidate_pythons():
        if _python_has_playwright(c):
            _PY_CACHE["exe"] = c
            return c
    return ""


def start_login_window(rel: str) -> tuple:
    """打开一个独立浏览器窗口等待扫码登录；登录成功后由子进程写回账号信息。"""
    prev = _LOGIN_JOB.get("proc")
    if prev is not None and prev.poll() is None:
        return False, "已经有一个登录窗口在等待扫码了，请先在那个窗口里完成登录（或关掉它再试）"
    if not LOGIN_SCRIPT.exists():
        return False, "缺少 account_login.py，请重新下载完整项目"
    exe = find_playwright_python()
    if not exe:
        return False, ("没找到装了 playwright 的 Python。请在项目目录执行：\n"
                       "  pip install -r requirements.txt\n  python -m playwright install chromium")
    try:
        proc = subprocess.Popen([exe, str(LOGIN_SCRIPT), rel], cwd=str(BASE),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       text=True, encoding="utf-8", errors="replace")
    except Exception as e:
        return False, f"打开登录窗口失败：{str(e)[:150]}"
    _LOGIN_JOB.update({"proc": proc, "dir": rel, "started": time.time(), "done": False, "result": None})
    return True, ""


def _collect_login_job():
    """子进程结束后读它的输出（最后一行 JSON）作为登录结果。"""
    j = _LOGIN_JOB
    proc = j.get("proc")
    if proc is None or j.get("done") or proc.poll() is None:
        return
    try:
        out, _ = proc.communicate(timeout=10)
    except Exception:
        out = ""
    info = {}
    for line in reversed((out or "").splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                info = json.loads(line)
                break
            except Exception:
                continue
    j["result"] = info or {"ok": False, "error": "登录窗口没有返回结果（可能被直接关掉了）"}
    j["done"] = True


def login_status() -> dict:
    _collect_login_job()
    j = _LOGIN_JOB
    proc = j.get("proc")
    res = j.get("result") or {}
    return {
        "running": bool(proc is not None and proc.poll() is None and not j.get("done")),
        "started": proc is not None,
        "dir": j.get("dir", ""),
        "elapsed": int(time.time() - j["started"]) if j.get("started") else 0,
        "ok": bool(res.get("ok")),
        "account": res.get("account", ""),
        "nick": res.get("nick", ""),
        "uid": res.get("uid", ""),
        "created": bool(res.get("created")),
        "error": res.get("error", ""),
    }


# ---------------- 每个账号一个自动发货进程（可多开，互不干扰） ----------------
_RUN_JOBS = {}   # 账号名 -> {"pid", "started"}；服务重启后靠 data/.running/*.json 恢复


def _alive_jobs() -> dict:
    """{账号名: 实例信息}，只含确实在跑的：内存记录 + pid 文件（死掉的自动清掉）。"""
    out = {}
    for name, job in list(_RUN_JOBS.items()):
        if job and pid_alive(job.get("pid")):
            out[name] = job
        else:
            _RUN_JOBS.pop(name, None)
    for name, info in running_accounts().items():
        out.setdefault(name, info)
    return out


def _kill_pid(pid) -> bool:
    """连进程树一起结束（浏览器窗口是它的子进程，要一起关掉）。"""
    try:
        pid = int(pid)
    except Exception:
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            # 不加 text=True：taskkill 的中文输出是 GBK，按 utf-8 解码会报错
            r = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                               capture_output=True, timeout=20)
            return r.returncode == 0
        except Exception:
            return False
    try:
        os.kill(pid, 15)
        return True
    except Exception:
        return False


def start_run(account: str) -> tuple:
    """给一个账号单独开一个控制台窗口跑自动发货（多账号可同时跑，各自独立沙盒）。"""
    cfg = load_settings_and_products()
    a = next((x for x in (cfg.get("accounts") or []) if x.get("name") == account), None)
    if a is None:
        return False, "账号不存在，请刷新页面"
    jobs = _alive_jobs()
    if account in jobs:
        return False, f"「{a.get('nick') or account}」已经在运行了（PID {jobs[account].get('pid')}）"
    # 同一个登录档案被别的账号实例占着也不能再开（两个 Chromium 抢同一个档案目录会出错）
    for name, info in jobs.items():
        if str(info.get("dir") or "") == str(a.get("dir")):
            return False, f"登录档案 {a.get('dir')} 正被「{name}」占用，一个档案目录同时只能跑一个实例"
    exe = find_playwright_python()
    if not exe:
        return False, ("没找到装了 playwright 的 Python。请在项目目录执行：\n"
                       "  pip install -r requirements.txt\n  python -m playwright install chromium")
    try:
        (BASE / str(a["dir"])).mkdir(parents=True, exist_ok=True)
        flags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
        proc = subprocess.Popen([exe, str(RUN_SCRIPT), "run", "--account", account],
                                cwd=str(BASE), creationflags=flags)
    except Exception as e:
        return False, f"启动失败：{str(e)[:150]}"
    job = {"pid": proc.pid, "started": time.strftime("%Y-%m-%d %H:%M:%S"),
           "account": account, "dir": a.get("dir", "")}
    _RUN_JOBS[account] = job
    who = a.get("nick") or account
    tip = "" if (a.get("nick") or a.get("uid")) else "该账号还没登录，弹出的窗口里扫码登录后就会开始监听；"
    return True, (f"已给「{who}」开了一个独立窗口开始自动发货（PID {proc.pid}）。{tip}"
                  "关掉那个黑窗口即停止这个账号，不影响其他账号。")


def stop_run(account: str) -> tuple:
    jobs = _alive_jobs()
    info = jobs.get(account)
    if not info:
        clear_run_pid(account)
        _RUN_JOBS.pop(account, None)
        return False, "这个账号现在没有在运行"
    pid = int(info.get("pid") or 0)
    _kill_pid(pid)
    _RUN_JOBS.pop(account, None)
    for _ in range(10):          # 等它真正退出（浏览器子进程也要关掉）
        if not pid_alive(pid):
            break
        time.sleep(0.4)
    clear_run_pid(account, pid)
    if pid_alive(pid):
        return False, f"停止失败：进程 {pid} 还在（可手动关掉那个黑窗口）"
    return True, f"已停止「{account}」的自动发货（PID {pid}）"


def start_all_runs() -> tuple:
    cfg = load_settings_and_products()
    accs = cfg.get("accounts") or []
    if not accs:
        return False, "还没有账号，先点「＋ 新增账号」扫码登录"
    jobs = _alive_jobs()
    started, skipped = [], []
    for a in accs:
        if a["name"] in jobs:
            skipped.append(a.get("nick") or a["name"])
            continue
        ok, _ = start_run(a["name"])
        (started if ok else skipped).append(a.get("nick") or a["name"])
        time.sleep(0.6)   # 错开启动，避免几个浏览器同时抢资源
    msg = ""
    if started:
        msg += "已启动：" + "、".join(started) + "。每个账号一个窗口，互不影响。"
    if skipped:
        msg += ("（跳过：" + "、".join(skipped) + "，已在运行或启动失败）") if msg \
            else "没有可启动的账号：" + "、".join(skipped)
    return bool(started), msg or "没有可启动的账号"


def stop_all_runs() -> tuple:
    jobs = _alive_jobs()
    if not jobs:
        return False, "现在没有账号在运行"
    stopped, failed = [], []
    for name in list(jobs):
        ok, _ = stop_run(name)
        (stopped if ok else failed).append(name)
    msg = "已停止：" + "、".join(stopped) if stopped else ""
    if failed:
        msg += ("（没能停止：" + "、".join(failed) + "，请手动关掉对应黑窗口）") if msg \
            else "没能停止：" + "、".join(failed)
    return bool(stopped), msg or "没能停止任何账号"


def handle_account_action(data: dict):
    """返回 (ok, message)。action: add / switch / rename / delete / start / stop / start_all / stop_all。"""
    action = str(data.get("action") or "")
    cfg = load_settings_and_products()   # 内部已 ensure_accounts
    accs = cfg.get("accounts") or []
    cur = cfg.get("current_account") or ""

    if action == "add":
        name = clean_account_name(data.get("name"))
        if name and any(a["name"] == name for a in accs):
            return False, f"账号「{name}」已存在，换个名字吧"
        rel = account_dir_for(name or "新账号", [a["dir"] for a in accs])
        (BASE / rel).mkdir(parents=True, exist_ok=True)
        aname = name or clean_account_name(Path(rel).name) or "新账号"
        accs.append({"name": aname, "dir": rel})
        save_settings(cfg)                  # 先落盘（未登录状态），登录成功后由子进程更新
        ok, msg = start_login_window(rel)   # 再弹出窗口等扫码，登录成功会自动登记并切换过去
        if not ok:
            accs.remove(next(a for a in accs if a["dir"] == rel))
            save_settings(cfg)              # 开窗口失败：撤掉刚加的空账号
            return False, msg
        return True, "已打开登录窗口：请在弹出的浏览器里用手机闲鱼/淘宝扫码登录，登录成功后会自动记录账号并切换过去。"

    elif action == "start":
        return start_run(clean_account_name(data.get("name")))

    elif action == "stop":
        return stop_run(clean_account_name(data.get("name")))

    elif action == "start_all":
        return start_all_runs()

    elif action == "stop_all":
        return stop_all_runs()

    elif action == "switch":
        name = clean_account_name(data.get("name"))
        a = next((x for x in accs if x["name"] == name), None)
        if not a:
            return False, "账号不存在，请刷新页面"
        (BASE / a["dir"]).mkdir(parents=True, exist_ok=True)
        cfg["current_account"] = a["name"]
        cfg["user_data_dir"] = a["dir"]
        msg = f"已切换到「{a.get('nick') or a['name']}」，请在商品管理页对该账号「停止」后「启动」生效。"

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
        if name in _alive_jobs():
            return False, "这个账号正在自动发货运行中，请先点「停止」再删除。"
        was_current = (a["name"] == cur)
        rest = [x for x in accs if x["name"] != a["name"]]

        # 彻底删除账号的登录档案（不留归档，数据不可恢复）
        p = BASE / a["dir"]
        if p.exists():
            try:
                remove_tree(p)
            except Exception:
                return False, ("删除失败：这个账号的登录档案正在被占用（多半是自动发货还在运行）。"
                               "请先在商品管理页对该账号点「■ 停止」关掉浏览器，再回来删除。")

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
            accounts = accounts_state(cfg)
            jobs = _alive_jobs()
            for it in accounts["items"]:
                job = jobs.get(it["name"]) or {}
                it["running"] = bool(job)
                it["pid"] = int(job.get("pid") or 0)
                it["run_since"] = str(job.get("started") or "")
            payload = {"version": APP_VERSION, "config": cfg, "accounts": accounts}
            self._send(200, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            return
        if path == "/api/login_status":
            self._send(200, json.dumps(login_status(), ensure_ascii=False).encode("utf-8"))
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
