# -*- coding: utf-8 -*-
"""发货内容与发货记录的本地存储。

发货内容是一整段文本，直接存在 products.json 各商品的 cards 字段里；
发货时把这段内容原样整段发给买家，**不做消耗、不删除**，同一商品可以反复使用。
每次发货仍会记录到 data/used_cards.log（仅作记录）。
"""
import json
import os
import re
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / "data"
LOGS_DIR = BASE / "logs"
DEFAULT_ACCOUNT = "默认账号"


def _read_text(path: Path) -> str:
    """读取文本，优先 utf-8，兼容 Windows 记事本保存的 gbk。"""
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def content_of(value) -> str:
    """把商品的 cards 字段统一成"一整段发货内容"字符串。

    兼容三种来源：字符串（原样）、列表（旧版一行一个，用换行拼起来）、None。
    只去掉首尾空行和每行尾部空格，保留中间的换行与缩进，方便发多行内容。
    """
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        text = "\n".join(str(x) for x in value)
    elif isinstance(value, str):
        text = value
    else:
        text = str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return text.strip("\n")


def migrate_product_cards(p: dict, base: Path = BASE) -> dict:
    """兼容旧配置：商品里没有 cards 但有 card_file 时，把该文件的内容读进 cards。

    返回商品本身（就地修改）；原卡密文件保留在磁盘上不动，作为备份。
    """
    if p.get("cards") is None:
        content = ""
        rel = str(p.get("card_file", "")).strip()
        if rel:
            f = (base / rel).resolve()
            if f.exists() and str(f).startswith(str((base / "cards").resolve()) + os.sep):
                content = _read_text(f)
        p["cards"] = content
    p["cards"] = content_of(p["cards"])
    for r in p.get("variant_rules") or []:
        r["cards"] = content_of(r.get("cards"))
    return p


def log_used_card(product_name: str, card: str, base: Path = BASE) -> None:
    """发货记录：时间、商品、发出的内容（换行压成\\n，过长截断）。"""
    try:
        data_dir = base / "data"
        data_dir.mkdir(exist_ok=True)
        brief = "\\n".join(card.split("\n"))[:300]
        with (data_dir / "used_cards.log").open("a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{product_name}\t{brief}\n")
    except Exception:
        pass


# ---------------- 多账号 ----------------
# 账号 = 一个独立的浏览器登录档案目录（config.json 的 accounts / current_account / user_data_dir）。
_BAD_NAME = re.compile(r'[\\/:*?"\'<>|\r\n\t]')


def clean_account_name(name) -> str:
    s = _BAD_NAME.sub("", str(name or "")).strip().strip(".").strip()
    return s[:24]


def account_dir_for(name: str, used=(), base: Path = BASE) -> str:
    """给账号生成一个不冲突的档案目录（相对项目目录）。"""
    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fa5_-]+", "_", name).strip("_") or "account"
    rel = f"accounts/{slug}"
    i = 2
    while (Path(base) / rel).exists() or rel in used:
        rel = f"accounts/{slug}_{i}"
        i += 1
    return rel


def ensure_accounts(cfg: dict, base: Path = BASE) -> dict:
    """保证 cfg 里有合法的 accounts / current_account，并把 user_data_dir 对齐到当前账号。

    - 老版本没有 accounts：把现有 user_data_dir（如 browser_data）登记为「默认账号」；
      若该目录也不存在，则认为是全新项目，账号列表为空。
    - 手动改过 config.json 的 user_data_dir（老办法换号）：自动登记成一个账号。
    """
    base = Path(base)
    accs = cfg.get("accounts")
    if not isinstance(accs, list):
        rel = str(cfg.get("user_data_dir") or "browser_data").strip().replace("\\", "/").strip("/")
        if (base / rel).exists():
            accs = [{"name": DEFAULT_ACCOUNT, "dir": rel}]
            cfg["current_account"] = DEFAULT_ACCOUNT
        else:
            accs = []
            cfg["current_account"] = ""
        cfg["accounts"] = accs

    accs[:] = [a for a in accs
               if isinstance(a, dict) and str(a.get("name", "")).strip() and str(a.get("dir", "")).strip()]
    for a in accs:
        a["name"] = clean_account_name(a["name"]) or DEFAULT_ACCOUNT
        a["dir"] = str(a["dir"]).replace("\\", "/").strip("/")

    # 手动改过 user_data_dir（或账号列表被清空后只剩档案目录）：登记成账号，方便在页面里看到和切换
    rel = str(cfg.get("user_data_dir") or "").strip().replace("\\", "/").strip("/")
    if not rel and not accs and (base / "browser_data").exists():
        rel = "browser_data"      # 账号列表被删空、但老的登录档案还在：认回「默认账号」
    if rel and not any(a["dir"] == rel for a in accs) and (base / rel).exists():
        dir_name = clean_account_name(Path(rel).name or "")
        if not accs and rel == "browser_data":
            name = DEFAULT_ACCOUNT          # 老版本的 browser_data 仍叫「默认账号」
        else:
            name = dir_name or DEFAULT_ACCOUNT   # 其它目录按目录名登记，避免名字和档案对不上
        base_name, i = name, 2
        while any(a["name"] == name for a in accs):
            name = f"{base_name}{i}"
            i += 1
        accs.append({"name": name, "dir": rel})

    cur = str(cfg.get("current_account") or "").strip()
    if not any(a["name"] == cur for a in accs):
        cur = accs[0]["name"] if accs else ""
    cfg["current_account"] = cur
    if cur:
        cfg["user_data_dir"] = next(a["dir"] for a in accs if a["name"] == cur)
    return cfg


def accounts_state(cfg: dict, base: Path = BASE) -> dict:
    """给管理页用的账号视图（含真实昵称/ID、目录是否存在）。"""
    base = Path(base)
    cur = cfg.get("current_account") or ""
    items = []
    for a in cfg.get("accounts") or []:
        items.append({
            "name": a["name"],
            "dir": a["dir"],
            "nick": str(a.get("nick") or ""),
            "uid": str(a.get("uid") or ""),
            "last_login": str(a.get("last_login") or ""),
            "exists": (base / a["dir"]).exists(),
            "active": a["name"] == cur,
        })
    return {"current": cur, "items": items}


def save_account_identity(account: str, uid: str = "", nick: str = "", base: Path = BASE) -> bool:
    """把登录后读到的真实闲鱼账号信息（昵称/用户ID）写进 config.json 的账号记录。

    找不到对应账号时（比如账号列表被删空、或备注名被改过）会自动按档案目录匹配，
    还是没有就新建一个账号记下来——保证"登录了就能在账号管理里看到这个号"。
    返回是否写入了配置。
    """
    path = Path(base) / "config.json"
    if not path.exists():
        return False
    try:
        cfg = json.loads(_read_text(path))
    except Exception:
        return False
    if not isinstance(cfg.get("accounts"), list):
        cfg["accounts"] = []
    accs = cfg["accounts"]
    for a in accs:                       # 清掉脏数据，后面按下标写回
        if not isinstance(a, dict):
            accs.remove(a)
    account = clean_account_name(account)
    rel = str(cfg.get("user_data_dir") or "browser_data").replace("\\", "/").strip("/") or "browser_data"

    target = next((a for a in accs if a.get("name") == account), None) if account else None
    if target is None:
        target = next((a for a in accs if str(a.get("dir") or "").replace("\\", "/").strip("/") == rel), None)

    created = False
    if target is None:
        name = clean_account_name(nick) or account or (
            DEFAULT_ACCOUNT if rel == "browser_data" else clean_account_name(Path(rel).name))
        name = name or DEFAULT_ACCOUNT
        base_name, i = name, 2
        while any(a.get("name") == name for a in accs):
            name = f"{base_name}{i}"
            i += 1
        target = {"name": name, "dir": rel}
        accs.append(target)
        cfg["current_account"] = name
        cfg["user_data_dir"] = rel
        created = True

    changed = created
    if uid and str(target.get("uid") or "") != str(uid):
        target["uid"] = str(uid)
        changed = True
    if nick and str(target.get("nick") or "") != str(nick):
        target["nick"] = str(nick)
        changed = True
    if uid or nick:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        if target.get("last_login") != stamp:
            target["last_login"] = stamp
            changed = True
    if changed:
        try:
            _atomic_write(path, json.dumps(cfg, ensure_ascii=False, indent=2))
        except Exception:
            return False
    return True


PRODUCTS_NAME = "products.json"



def load_settings_and_products(base: Path = BASE) -> dict:
    """读取全局设置 config.json + 商品 products.json，合并成一个 cfg 返回。

    首次运行时若 products.json 不存在，自动把旧 config.json 里的 products
    拆分到 products.json，并从 config.json 中移除该字段。
    """
    base = Path(base)
    cfg_path = base / "config.json"
    cfg = json.loads(_read_text(cfg_path)) if cfg_path.exists() else {}
    prod_path = base / PRODUCTS_NAME
    if prod_path.exists():
        data = json.loads(_read_text(prod_path))
        products = data.get("products", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
    else:
        products = cfg.get("products", [])
        _atomic_write(prod_path, json.dumps({"products": products}, ensure_ascii=False, indent=2))
        cfg.pop("products", None)
        _atomic_write(cfg_path, json.dumps(cfg, ensure_ascii=False, indent=2))
    for p in products:
        migrate_product_cards(p, base)
    cfg["products"] = products
    ensure_accounts(cfg, base)  # 保证账号信息可用（老配置自动登记现有档案）
    return cfg


def save_products(products: list, base: Path = BASE) -> None:
    _atomic_write(base / PRODUCTS_NAME, json.dumps({"products": products}, ensure_ascii=False, indent=2))


def save_settings(cfg: dict, base: Path = BASE) -> None:
    """把合并 cfg 里的全局设置（去掉 products）写回 config.json。"""
    out = {k: v for k, v in cfg.items() if k != "products"}
    _atomic_write(base / "config.json", json.dumps(out, ensure_ascii=False, indent=2))


class DeliveredStore:
    """发货记录（去重）：key -> 信息，存于 data/delivered*.json。

    多个闲鱼账号之间去重记录互相独立（避免不同账号的同名买家被误判成"已发过"）：
    默认账号沿用旧的 delivered.json，其它账号各用 delivered.<账号名>.json。
    """

    def __init__(self, base: Path = BASE, account: str = ""):
        self.data_dir = base / "data"
        self.data_dir.mkdir(exist_ok=True)
        self.path = self.data_dir / self._filename(account)
        try:
            self.items = json.loads(_read_text(self.path)) if self.path.exists() else {}
        except Exception:
            self.items = {}
        if not isinstance(self.items, dict):
            self.items = {}

    @staticmethod
    def _filename(account: str) -> str:
        name = str(account or "").strip()
        if not name or name == "默认账号":
            return "delivered.json"
        safe = re.sub(r'[\\/:*?"<>|\s]+', "_", name)[:20] or "account"
        return f"delivered.{safe}.json"

    def is_new(self, key: str) -> bool:
        return key not in self.items

    def mark(self, key: str, info: dict) -> None:
        info = dict(info)
        info["time"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self.items[key] = info
        self._save()

    def _save(self) -> None:
        _atomic_write(self.path, json.dumps(self.items, ensure_ascii=False, indent=2))
