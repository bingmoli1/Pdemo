# -*- coding: utf-8 -*-
"""闲鱼本地自动发货工具（网页版 goofish.com）

命令：
  python auto_delivery.py login                 首次运行：打开浏览器扫码登录，保存会话
  python auto_delivery.py run                   启动自动发货监听
  python auto_delivery.py inspect               抓取页面候选选择器 + 截图（校准 config.json 的 selectors 用）
  python auto_delivery.py send-test --search 关键词 --text 内容
                                                手动向某个会话发送一条消息（真实发送，测试用）
  python auto_delivery.py cards                 查看各商品的发货内容是否已填写
"""
import argparse
import json
import logging
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from stores import DeliveredStore, LOGS_DIR, content_of, load_settings_and_products  # noqa: E402


def load_json(path: Path, required: bool = True) -> dict:
    if not path.exists():
        if required:
            print(f"缺少文件：{path}")
            sys.exit(1)
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def setup_logging() -> logging.Logger:
    LOGS_DIR.mkdir(exist_ok=True)
    logger = logging.getLogger("xy")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    fh = logging.FileHandler(LOGS_DIR / "app.log", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(ch)
    logger.addHandler(fh)
    return logger


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
    bs = get_browser_session_class()(cfg)
    bs.launch()
    try:
        bs.open_im()
        bs.ensure_login()
        print("✔ 登录完成，会话已保存到 browser_data/，以后运行 run 命令即可免登录。")
        time.sleep(2)
    finally:
        bs.close()


def cmd_run(cfg: dict, selectors: dict):
    log = setup_logging()
    bs = get_browser_session_class()(cfg)
    bs.launch()
    from app import AutoDeliverer
    deliverer = AutoDeliverer(bs, cfg, selectors, DeliveredStore(), log)
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
    log = setup_logging()
    bs = get_browser_session_class()(cfg)
    bs.launch()
    try:
        bs.open_im()
        bs.ensure_login()
        from app import AutoDeliverer
        d = AutoDeliverer(bs, cfg, selectors, DeliveredStore(), log)
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
    ap.add_argument("--search", help="send-test：用于定位会话的关键词（买家名或商品名）")
    ap.add_argument("--text", help="send-test：要发送的内容")
    args = ap.parse_args()

    cfg = load_settings_and_products()  # 全局设置读 config.json，商品读 products.json（首次自动拆分）
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
