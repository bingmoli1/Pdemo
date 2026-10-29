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


def log_used_card(product_name: str, card: str, base: Path = BASE, account: str = "") -> None:
    """发货记录：时间、商品、发出的内容（换行压成\\n，过长截断）。

    多个账号同时运行时各写一个文件（避免几个进程抢同一个日志文件），
    默认账号沿用旧的 used_cards.log。
    """
    try:
        data_dir = base / "data"
        data_dir.mkdir(exist_ok=True)
        brief = "\\n".join(card.split("\n"))[:300]
        name = "used_cards.log" if (not account or account == DEFAULT_ACCOUNT) \
            else f"used_cards.{safe_slug(account)}.log"
        with (data_dir / name).open("a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{product_name}\t{brief}\n")
    except Exception:
        pass


# ---------------- 多账号 ----------------
# 账号 = 一个独立的浏览器登录档案目录（config.json 的 accounts / current_account / user_data_dir）。
_BAD_NAME = re.compile(r'[\\/:*?"\'<>|\r\n\t]')


def clean_account_name(name) -> str:
    s = _BAD_NAME.sub("", str(name or "")).strip().strip(".").strip()
    return s[:24]


def safe_slug(name) -> str:
    """账号名 → 文件名/日志名里能用的片段（中文保留）。"""
    s = re.sub(r'[\\/:*?"<>|\s]+', "_", str(name or "")).strip("_.")
    return s[:20] or "account"


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


def save_account_identity(account: str, uid: str = "", nick: str = "", base: Path = BASE,
                          set_current: bool = True) -> bool:
    """把登录后读到的真实闲鱼账号信息（昵称/用户ID）写进 config.json 的账号记录。

    找不到对应账号时（比如账号列表被删空、或备注名被改过）会自动按档案目录匹配，
    还是没有就新建一个账号记下来——保证"登录了就能在账号管理里看到这个号"。
    set_current=False 时只更新这个账号自己的信息，**不改动 current_account / user_data_dir**
    （多账号并行运行时用，避免一个实例把别的实例/管理页的当前账号改掉）。
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
        if set_current:
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


def register_account_login(rel_dir: str, uid: str = "", nick: str = "", base: Path = BASE) -> dict:
    """把一次扫码登录的结果登记到账号列表：按档案目录匹配，找不到就新建，并切为当前账号。

    rel_dir：该账号的档案目录（相对项目目录，如 accounts/新账号1）。
    账号名还是默认的「新账号N」时，会用登录到的昵称替掉，列表里一眼能认出是哪个号。
    返回 {"ok": bool, "account": 账号名, "created": 是否新建}。
    """
    path = Path(base) / "config.json"
    if not path.exists():
        return {"ok": False, "account": "", "created": False}
    try:
        cfg = json.loads(_read_text(path))
    except Exception:
        return {"ok": False, "account": "", "created": False}
    if not isinstance(cfg.get("accounts"), list):
        cfg["accounts"] = []
    ensure_accounts(cfg, base)                 # 顺带自愈老配置
    accs = cfg["accounts"]
    rel = str(rel_dir or "").replace("\\", "/").strip("/")
    if not rel:
        return {"ok": False, "account": "", "created": False}
    (Path(base) / rel).mkdir(parents=True, exist_ok=True)

    target = next((a for a in accs if str(a.get("dir") or "").replace("\\", "/").strip("/") == rel), None)
    created = False
    if target is None:
        base_name = clean_account_name(nick or Path(rel).name) or DEFAULT_ACCOUNT
        nm, i = base_name, 2
        while any(a.get("name") == nm for a in accs):
            nm = f"{base_name}{i}"
            i += 1
        target = {"name": nm, "dir": rel}
        accs.append(target)
        created = True
    elif nick and str(target.get("name", "")).startswith("新账号") \
            and not any(a.get("name") == nick for a in accs):
        target["name"] = clean_account_name(nick) or target["name"]   # 默认名换成真实昵称

    if uid:
        target["uid"] = str(uid)
    if nick:
        target["nick"] = str(nick)
    if uid or nick:
        target["last_login"] = time.strftime("%Y-%m-%d %H:%M:%S")
    cfg["current_account"] = target["name"]
    cfg["user_data_dir"] = rel
    try:
        _atomic_write(path, json.dumps(cfg, ensure_ascii=False, indent=2))
    except Exception:
        return {"ok": False, "account": "", "created": False}
    return {"ok": True, "account": target["name"], "created": created}


def sandbox_for(cfg: dict, account: str, base: Path = BASE) -> dict:
    """把配置收敛成「只属于这一个账号」的沙盒副本，供自动发货进程使用。

    沙盒里：accounts 只剩自己这一条（程序根本看不到其他账号的存在）、
    user_data_dir/current_account 都指向自己，登录档案、发货去重、日志随之隔离。
    只改内存里的副本，不会写回 config.json，所以多个账号的实例可以并存、互不干扰。
    """
    accs = [a for a in (cfg.get("accounts") or []) if isinstance(a, dict)]
    key = str(account or "").strip()
    a = next((x for x in accs if str(x.get("name")) == key), None) \
        or next((x for x in accs if str(x.get("dir")) == key), None)
    if a is None:
        raise KeyError(account)
    out = dict(cfg)
    out["accounts"] = [dict(a)]
    out["current_account"] = str(a.get("name"))
    out["user_data_dir"] = str(a.get("dir"))
    out["sandbox"] = True                       # 标记：写回账号信息时不要抢「当前账号」
    return out


# ---------------- 运行中的自动发货实例（多账号并行时用 pid 文件记账） ----------------
RUN_DIR_NAME = ".running"      # data/.running/<账号>.json


def run_dir(base: Path = BASE) -> Path:
    p = Path(base) / "data" / RUN_DIR_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def run_pid_path(account: str, base: Path = BASE) -> Path:
    return run_dir(base) / f"{safe_slug(account)}.json"


def pid_alive(pid) -> bool:
    """进程是否还活着（Windows 用 OpenProcess，避免 os.kill(pid,0) 的坑）。"""
    try:
        pid = int(pid)
    except Exception:
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
            if not handle:
                return False
            try:
                code = ctypes.c_ulong()
                if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                    return code.value == 259                    # STILL_ACTIVE
                return False
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def write_run_pid(account: str, info: dict, base: Path = BASE) -> None:
    data = dict(info)
    data["account"] = account
    data["pid"] = int(data.get("pid") or os.getpid())
    data.setdefault("started", time.strftime("%Y-%m-%d %H:%M:%S"))
    try:
        _atomic_write(run_pid_path(account, base), json.dumps(data, ensure_ascii=False, indent=2))
    except Exception:
        pass


def read_run_pid(account: str, base: Path = BASE):
    """返回还在运行的实例信息；进程已死或文件是别的实例的残留则返回 None（顺手清理）。"""
    p = run_pid_path(account, base)
    if not p.exists():
        return None
    try:
        info = json.loads(_read_text(p))
    except Exception:
        try:
            p.unlink()
        except Exception:
            pass
        return None
    if not isinstance(info, dict) or not pid_alive(info.get("pid")):
        try:
            p.unlink()
        except Exception:
            pass
        return None
    return info


def clear_run_pid(account: str, pid=None, base: Path = BASE) -> None:
    """进程退出时删掉自己的记账文件（只删属于自己的那条，别把新实例的删了）。"""
    p = run_pid_path(account, base)
    if not p.exists():
        return
    if pid is not None:
        try:
            info = json.loads(_read_text(p))
        except Exception:
            info = {}
        if int(info.get("pid") or -1) != int(pid):
            return
    try:
        p.unlink()
    except Exception:
        pass


def running_accounts(base: Path = BASE) -> dict:
    """{账号名: 实例信息}（只含确实在跑的）。"""
    out = {}
    try:
        files = sorted(run_dir(base).glob("*.json"))
    except Exception:
        return out
    for f in files:
        try:
            info = json.loads(_read_text(f))
        except Exception:
            continue
        if not isinstance(info, dict):
            continue
        name = str(info.get("account") or f.stem)
        if not pid_alive(info.get("pid")):
            try:
                f.unlink()
            except Exception:
                pass
            continue
        out[name] = info
    return out


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
        if not name or name == DEFAULT_ACCOUNT:
            return "delivered.json"
        return f"delivered.{safe_slug(name)}.json"

    def is_new(self, key: str) -> bool:
        return key not in self.items

    def mark(self, key: str, info: dict) -> None:
        info = dict(info)
        info["time"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self.items[key] = info
        self._save()

    def _save(self) -> None:
        _atomic_write(self.path, json.dumps(self.items, ensure_ascii=False, indent=2))
