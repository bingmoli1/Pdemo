# -*- coding: utf-8 -*-
"""发货内容与发货记录的本地存储。

发货内容是一整段文本，直接存在 products.json 各商品的 cards 字段里；
发货时把这段内容原样整段发给买家，**不做消耗、不删除**，同一商品可以反复使用。
每次发货仍会记录到 data/used_cards.log（仅作记录）。
"""
import json
import os
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / "data"
LOGS_DIR = BASE / "logs"


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
    return cfg


def save_products(products: list, base: Path = BASE) -> None:
    _atomic_write(base / PRODUCTS_NAME, json.dumps({"products": products}, ensure_ascii=False, indent=2))


def save_settings(cfg: dict, base: Path = BASE) -> None:
    """把合并 cfg 里的全局设置（去掉 products）写回 config.json。"""
    out = {k: v for k, v in cfg.items() if k != "products"}
    _atomic_write(base / "config.json", json.dumps(out, ensure_ascii=False, indent=2))


class DeliveredStore:
    """发货记录（去重）：key -> 信息，存于 data/delivered.json。"""

    def __init__(self, base: Path = BASE):
        self.data_dir = base / "data"
        self.data_dir.mkdir(exist_ok=True)
        self.path = self.data_dir / "delivered.json"
        try:
            self.items = json.loads(_read_text(self.path)) if self.path.exists() else {}
        except Exception:
            self.items = {}
        if not isinstance(self.items, dict):
            self.items = {}

    def is_new(self, key: str) -> bool:
        return key not in self.items

    def mark(self, key: str, info: dict) -> None:
        info = dict(info)
        info["time"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self.items[key] = info
        self._save()

    def _save(self) -> None:
        _atomic_write(self.path, json.dumps(self.items, ensure_ascii=False, indent=2))
