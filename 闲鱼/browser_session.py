# -*- coding: utf-8 -*-
"""Playwright 持久化浏览器会话：首次扫码登录后，会话保存在 browser_data/，之后免登录。

inspect 命令会抓取页面候选选择器并截图，用于校准 selectors.json。
"""
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = Path(__file__).resolve().parent
LOGS_DIR = BASE / "logs"


class BrowserSession:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.user_data_dir = str((BASE / (cfg.get("user_data_dir") or "browser_data")).resolve())
        self.pw = None
        self.ctx = None
        self.page = None

    def launch(self):
        self.pw = sync_playwright().start()
        self.ctx = self.pw.chromium.launch_persistent_context(
            self.user_data_dir,
            headless=bool(self.cfg.get("headless", False)),
            locale=self.cfg.get("locale", "zh-CN"),
            timezone_id=self.cfg.get("timezone_id", "Asia/Shanghai"),
            viewport=self.cfg.get("viewport") or {"width": 1280, "height": 850},
            args=["--disable-blink-features=AutomationControlled"],
        )
        self.ctx.set_default_timeout(10000)
        self.page = self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page()
        return self.page

    def close(self):
        try:
            if self.ctx:
                self.ctx.close()
        finally:
            if self.pw:
                self.pw.stop()

    def open_im(self):
        url = self.cfg.get("im_url", "https://www.goofish.com/im")
        self.page.goto(url, wait_until="domcontentloaded")
        try:
            self.page.wait_for_load_state("load", timeout=15000)
        except Exception:
            pass
        self.page.wait_for_timeout(int(self.cfg.get("page_load_wait_ms", 3000)))
        self.snapshot("screen_open_im.png")

    def snapshot(self, name: str):
        """当前页面截图到 logs/，便于排查登录/页面状态。"""
        try:
            LOGS_DIR.mkdir(exist_ok=True)
            self.page.screenshot(path=str(LOGS_DIR / name), full_page=False)
        except Exception:
            pass

    def ensure_login(self, timeout_s: int = 0) -> bool:
        """检测未登录则等待人工扫码；登录态保存在各账号自己的档案目录里。"""
        timeout_s = timeout_s or int(self.cfg.get("login_wait_seconds", 600))

        def need_login() -> bool:
            # 登录态最可靠的判据就是 unb（用户ID）这个 cookie：有就说明登录过了
            if self.self_user_id():
                return False
            if "login" in self.page.url:
                return True
            # 登录表单可能嵌在 iframe 里，逐个 frame 检查
            keywords = ("扫码登录", "登录淘宝", "请先登录", "扫一扫登录", "扫码", "登录后")
            for fr in self.page.frames:
                try:
                    txt = fr.locator("body").inner_text(timeout=1500)[:2000]
                except Exception:
                    continue
                if any(k in txt for k in keywords):
                    return True
            return True      # 没有 unb → 视为未登录，继续等扫码

        if not need_login():
            return True
        print("[登录] 检测到未登录，请在弹出的浏览器窗口中用手机闲鱼/淘宝 扫码登录……")
        self.snapshot("screen_need_login.png")
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            self.page.wait_for_timeout(3000)
            if not need_login():
                print("[登录] 登录成功，会话已保存，下次运行免登录。")
                return True
        raise RuntimeError("等待登录超时（10 分钟）。请重新运行 login 命令。")

    def self_user_id(self) -> str:
        """从 cookie 读取本机闲鱼用户ID（unb），用于忽略自己发出的消息。"""
        if self.cfg.get("my_user_id"):
            return str(self.cfg["my_user_id"])
        try:
            for c in self.ctx.cookies():
                if c.get("name") == "unb":
                    return str(c.get("value", ""))
        except Exception:
            pass
        return ""

    def self_identity(self) -> dict:
        """读 cookie 得到当前登录账号的昵称/用户ID（用于账号管理页显示真实账号）。"""
        from urllib.parse import unquote
        out = {"uid": "", "nick": ""}
        try:
            cookies = {c.get("name"): str(c.get("value") or "") for c in self.ctx.cookies()}
        except Exception:
            return out
        out["uid"] = cookies.get("unb", "").strip()
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
                out["nick"] = v
                break
        return out


def _probe(page, sel: str) -> int:
    try:
        return page.locator(sel).count()
    except Exception:
        return -1


def inspect_page(page, selectors: dict, label: str) -> list:
    lines = ["", f"===== {label} =====", f"URL: {page.url}"]
    try:
        lines.append(f"标题: {page.title()}")
    except Exception:
        pass

    lines.append("-- 会话列表候选选择器（配到 config.json 的 selectors.conversation_items）--")
    candidates = list(selectors.get("conversation_items", [])) + [
        "[class*='conv'] li", "[class*='session'] li", "[class*='chat-list'] li",
        "[class*='Conv'] li", "[class*='list'] li", "ul li",
    ]
    seen = set()
    for sel in candidates:
        if sel in seen:
            continue
        seen.add(sel)
        n = _probe(page, sel)
        if n > 0:
            lines.append(f"  命中 {n:>4} 个  ->  {sel}")

    lines.append("-- 输入框候选选择器（配到 chat_input）--")
    for sel in list(selectors.get("chat_input", [])) + [
        "[contenteditable='true']", "textarea", "input[placeholder*='输入']", "input[type='text']"
    ]:
        n = _probe(page, sel)
        if n > 0:
            try:
                ph = page.locator(sel).first.get_attribute("placeholder") or ""
            except Exception:
                ph = ""
            lines.append(f"  命中 {n:>4} 个  ->  {sel}   placeholder={ph!r}")

    lines.append("-- 页面上的按钮文字（发送按钮配到 send_button_text）--")
    try:
        btns = [t.strip() for t in page.locator("button").all_inner_texts() if t.strip()]
        lines.append("  " + " | ".join(dict.fromkeys(btns[:30])))
    except Exception:
        pass

    return lines


def run_inspect(cfg: dict, selectors: dict) -> str:
    LOGS_DIR.mkdir(exist_ok=True)
    bs = BrowserSession(cfg)
    report = ["闲鱼页面选择器检查报告（inspect）"]
    try:
        bs.launch()
        bs.ensure_login()
        bs.open_im()
        report += inspect_page(bs.page, selectors, "IM 消息页")
        shot = str(LOGS_DIR / "inspect_im.png")
        bs.page.screenshot(path=shot, full_page=True)
        report.append(f"截图: {shot}")
        orders_url = cfg.get("orders_url", "")
        if orders_url:
            bs.page.goto(orders_url, wait_until="domcontentloaded")
            bs.page.wait_for_timeout(3000)
            report += inspect_page(bs.page, selectors, "订单页 " + orders_url)
            shot2 = str(LOGS_DIR / "inspect_orders.png")
            bs.page.screenshot(path=shot2, full_page=True)
            report.append(f"截图: {shot2}")
    finally:
        bs.close()
    out = str(LOGS_DIR / "inspect_report.txt")
    Path(out).write_text("\n".join(report), encoding="utf-8")
    return out
