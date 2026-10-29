# -*- coding: utf-8 -*-
"""闲鱼本地自动发货工具（网页版 goofish.com）

命令：
  python auto_delivery.py login                 首次运行：打开浏览器扫码登录，保存会话
  python auto_delivery.py run                    启动自动发货监听（默认用账号管理里的当前账号）
  python auto_delivery.py run --account 账号名   只跑指定的那个账号（可多个账号同时各开一个窗口）
  python auto_delivery.py inspect                抓取页面候选选择器 + 截图（校准 config.json 的 selectors 用）
  python auto_delivery.py send-test --search 关键词 --text 内容
                                                手动向某个会话发送一条消息（真实发送，测试用）
  python auto_delivery.py cards                 查看各商品的发货内容是否已填写

多账号并行：每个账号一个独立沙盒（自己的登录档案 / 发货记录 / 日志），
进程里只有自己那一个账号的信息，看不到也不会改动其他账号，彼此互不影响。
"""
import argparse
import atexit
import json
import logging
import os
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from stores import (DeliveredStore, LOGS_DIR, clear_run_pid, content_of,  # noqa: E402
                    load_settings_and_products, pid_alive, read_run_pid,
                    running_accounts, sandbox_for, safe_slug, write_run_pid)


def load_json(path: Path, required: bool = True) -> dict:
    if not path.exists():
        if required:
            print(f"缺少文件：{path}")
            sys.exit(1)
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def setup_logging(account: str = "") -> logging.Logger:
    """每个账号一个日志文件（多个账号并行时不会互相覆盖）。"""
    LOGS_DIR.mkdir(exist_ok=True)
    logger = logging.getLogger("xy")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    fh = logging.FileHandler(LOGS_DIR / f"run_{safe_slug(account or 'default')}.log", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(ch)
    logger.addHandler(fh)
    return logger


def set_console_title(text: str) -> None:
    """Windows：把黑窗口标题改成「自动发货 - 账号名」，多开时一眼分清哪个窗口是哪个号。"""
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleTitleW(str(text)[:200])
    except Exception:
        pass


def claim_account_slot(cfg: dict) -> str:
    """登记"这个账号正在运行"，并挡掉重复启动（同一账号/同一档案目录只能有一个实例）。

    返回账号名；已在运行时直接退出程序。
    """
    account = str(cfg.get("current_account") or "").strip() or "默认账号"
    my_dir = str(cfg.get("user_data_dir") or "").strip()
    running = running_accounts()
    for name, info in running.items():
        same = (name == account) or (str(info.get("dir") or "").strip() == my_dir and my_dir)
        if same and int(info.get("pid") or 0) != os.getpid() and pid_alive(info.get("pid")):
            print(f"✘ 账号「{name}」的自动发货已经在运行了（PID {info.get('pid')}），不能重复启动。")
            print("  想换配置就先在那个窗口按 Ctrl+C（或到商品管理页点「停止」）停掉，再重新启动。")
            sys.exit(2)
    write_run_pid(account, {"pid": os.getpid(), "account": account, "dir": my_dir,
                            "started": time.strftime("%Y-%m-%d %H:%M:%S")})
    atexit.register(clear_run_pid, account, os.getpid())
    return account


def get_browser_session_class():
    try:
        from browser_session import BrowserSession
        return BrowserSession
    except ImportError:
        print("未安装 playwright，请先执行：")
        print("  pip install -r requirements.txt")
        print("  python -m playwright install chromium")
        sys.exit(1)


def cmd_login(cfg: dict):
    account = str(cfg.get("current_account") or "").strip()
    if account:
        set_console_title(f"闲鱼登录 - {account}")
    bs = get_browser_session_class()(cfg)
    bs.launch()
    try:
        bs.open_im()
        bs.ensure_login()
        print(f"✔ 登录完成，会话已保存到 {cfg.get('user_data_dir')}/，以后运行 run 命令即可免登录。")
        time.sleep(2)
    finally:
        bs.close()


def cmd_run(cfg: dict, selectors: dict):
    account = claim_account_slot(cfg)          # 挡掉同一账号重复启动
    set_console_title(f"自动发货 - {account}（关闭此窗口即停止）")
    log = setup_logging(account)               # 每个账号一个日志文件，互不覆盖
    log.info(f"账号沙盒[{account}]：登录档案={cfg.get('user_data_dir')} | "
             f"发货记录=data/{DeliveredStore._filename(account)} | 日志=logs/run_{safe_slug(account)}.log")
    bs = get_browser_session_class()(cfg)
    bs.launch()
    from app import AutoDeliverer
    deliverer = AutoDeliverer(bs, cfg, selectors, DeliveredStore(account=cfg.get("current_account") or ""), log)
    try:
        deliverer.start()
    except KeyboardInterrupt:
        log.info("已手动停止。")
    finally:
        try:
            bs.close()
        except Exception:
            pass


def cmd_inspect(cfg: dict, selectors: dict):
    from browser_session import run_inspect
    out = run_inspect(cfg, selectors)
    print(f"✔ 检查报告已写入：{out}")
    print("按报告里『命中 N 个』的选择器，更新 config.json 的 selectors 部分，然后重新运行 run。")


def cmd_send_test(cfg: dict, selectors: dict, search: str, text: str):
    log = setup_logging(cfg.get("current_account") or "")
    bs = get_browser_session_class()(cfg)
    bs.launch()
    try:
        bs.open_im()
        bs.ensure_login()
        from app import AutoDeliverer
        d = AutoDeliverer(bs, cfg, selectors, DeliveredStore(account=cfg.get("current_account") or ""), log)
        row = d.find_row_by_text(search)
        if row is None:
            log.error(f"会话列表里没找到包含『{search}』的会话")
            return
        row.click()
        bs.page.wait_for_timeout(1500)
        ok = d.send_message(text)
        log.info("✔ 测试消息已发送" if ok else "✘ 发送失败")
    finally:
        try:
            bs.close()
        except Exception:
            pass


def cmd_cards(cfg: dict):
    """查看各商品/规格的发货内容是否已填写（内容整段发送、不消耗）。"""
    missing = 0
    for p in cfg.get("products", []):
        c = content_of(p.get("cards"))
        if not c:
            missing += 1
        desc = f"{len(c)} 字 / {len(c.splitlines())} 行" if c else "发货内容为空"
        lines = [f"  [{'OK' if c else '未填写!'}] {p.get('name', '?')}：{desc}"]
        for r in p.get("variant_rules") or []:
            rc = content_of(r.get("cards"))
            if not rc:
                missing += 1
            label = r.get("name") or "、".join(r.get("keywords", [])) or "未命名规格"
            rdesc = f"{len(rc)} 字 / {len(rc.splitlines())} 行" if rc else "发货内容为空"
            lines.append(f"        规格[{label}]：{rdesc}")
        print("\n".join(lines))
    print(f"共 {len(cfg.get('products', []))} 个商品；未填写发货内容的项：{missing} 个")
    print("提示：发货内容整段发给买家，发完不删除，可反复使用。")


def main():
    ap = argparse.ArgumentParser(description="闲鱼本地自动发货工具")
    ap.add_argument("command", choices=["login", "run", "inspect", "send-test", "cards"])
    ap.add_argument("--account", help="用账号管理里的哪个账号运行（不填=当前账号）")
    ap.add_argument("--search", help="send-test：用于定位会话的关键词（买家名或商品名）")
    ap.add_argument("--text", help="send-test：要发送的内容")
    args = ap.parse_args()

    cfg = load_settings_and_products()  # 全局设置读 config.json，商品读 products.json（首次自动拆分）

    # 指定了账号：收敛成只属于该账号的沙盒（登录档案/发货记录/日志全隔离，看不见其他账号）
    if args.account:
        try:
            cfg = sandbox_for(cfg, args.account)
        except KeyError:
            names = "、".join(a["name"] for a in (cfg.get("accounts") or [])) or "（还没有账号）"
            print(f"✘ 账号管理里没有「{args.account}」。现有账号：{names}")
            print("  可运行的账号见商品管理页「账号管理」，或双击「启动自动发货.bat」用当前账号。")
            sys.exit(1)

    selectors = cfg.get("selectors") or load_json(BASE / "selectors.json", required=False) or {}

    if args.command == "login":
        cmd_login(cfg)
    elif args.command == "run":
        cmd_run(cfg, selectors)
    elif args.command == "inspect":
        cmd_inspect(cfg, selectors)
    elif args.command == "send-test":
        if not args.search or not args.text:
            print("用法：python auto_delivery.py send-test --search 关键词 --text 内容")
            sys.exit(1)
        cmd_send_test(cfg, selectors, args.search, args.text)
    elif args.command == "cards":
        cmd_cards(cfg)


if __name__ == "__main__":
    main()
