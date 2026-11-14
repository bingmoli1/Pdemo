# -*- coding: utf-8 -*-

"""
二维码批量转码工具

启动即进入批量转码主界面（唯一窗口），两个页签：
1. 文本 → 二维码（批量生成）：TXT/CSV/TSV/Excel/Word 清单批量生成 PNG
2. 二维码 → 文本（批量识别）：多张图片/文件夹批量识别并导出
"""

import csv
import json
import os
import re
import webbrowser
import zipfile
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import qrcode
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageTk, ImageGrab

try:
    from pyzbar.pyzbar import decode as zbar_decode
except ImportError:
    zbar_decode = None

# 尝试安装 tkinterdnd2 以支持拖拽
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    TkinterDnD = None

# ----------------------------------------------------------------------
# 视觉规范（浅色 + 圆角卡片 + 柔和阴影）
# ----------------------------------------------------------------------
BG = "#F3F5FA"           # 窗口背景
CARD = "#FFFFFF"         # 卡片背景
FIELD = "#F8FAFD"        # 预览区底色
BORDER = "#E9EDF5"       # 卡片描边
FIELD_BORDER = "#E7ECF4" # 预览区描边
DIVIDER = "#EFF2F8"      # 分隔线
TEXT = "#1D2534"         # 主文字
MUTED = "#8A93A8"        # 次要文字
STATUS_FG = "#6B7488"    # 状态栏文字
PLACEHOLDER = "#C7D0E0"  # 占位图形颜色
ACCENT = "#3B82F6"       # 主题色
ACCENT_HOVER = "#2E6FE4"
ACCENT_ACTIVE = "#2A62D0"
OK = "#16A34A"
WARN = "#D97706"
ERR = "#EF4444"

FONT = "Microsoft YaHei UI"
CONTENT_W = 244          # 卡片内容/预览区宽度（96 DPI 逻辑像素）
CARD_R = 12              # 卡片圆角
PREV_R = 10              # 预览区圆角
BTN_R = 7                # 按钮圆角
SHADOW_M = 8             # 卡片阴影留白

# ----------------------------------------------------------------------
# 批量转码共用定义（单张与批量走同一套编解码实现，结果完全一致）
# ----------------------------------------------------------------------
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff")
TEXT_EXTS = (".txt", ".csv", ".tsv")
DOC_EXTS = (".docx", ".xlsx")          # Office 清单（zip + XML，标准库直接解析）
LIST_EXTS = TEXT_EXTS + DOC_EXTS       # 所有可作为清单导入的格式
IMG_FILETYPES = [("图像文件", "*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tif *.tiff"),
                 ("所有文件", "*.*")]
TEXT_FILETYPES = [("清单文件（文本 / CSV / Excel / Word）",
                   "*.txt *.csv *.tsv *.xlsx *.docx"),
                  ("所有文件", "*.*")]
DEFAULT_OUT_NAME = "二维码批量输出"
TABLE_HEADERS = {"内容", "文本", "链接", "网址", "content", "text", "link",
                 "url", "data", "value"}
# Excel 读取整行所有单元格时用于判定「表头行」，避免编号/备注等列被当成二维码内容
HEADER_WORDS = TABLE_HEADERS | {
    "编号", "序号", "名称", "备注", "说明", "编码", "二维码", "标题",
    "id", "no", "num", "index", "name", "remark", "note", "title", "seq",
    "code", "key", "sn", "qr", "qrcode",
}
# 结果导出的保存类型（对话框描述 → 扩展名），顺序即对话框里的顺序
EXPORT_TYPES = (
    ("CSV 表格（Excel 可直接打开）", ".csv"),
    ("Excel 工作簿", ".xlsx"),
    ("Word 文档", ".docx"),
    ("文本文件", ".txt"),
)
EXPORT_EXT_BY_LABEL = {label: ext for label, ext in EXPORT_TYPES}
EXPORT_LABEL_BY_EXT = {ext: label for label, ext in EXPORT_TYPES}

# ----------------------------------------------------------------------
# 上次设置：%APPDATA%\二维码工具\settings.json
#   纯文本 JSON，可直接查看 / 修改 / 删除（删掉即恢复默认）；不放在 exe 目录，
#   项目目录保持干净。只记界面设置，不记输入内容和识别结果。
# ----------------------------------------------------------------------
SETTING_DEFAULTS = {
    "version": 1,
    "gen_dir": "",              # 空 = 桌面 / 二维码批量输出
    "gen_name": "内容命名",
    "gen_prefix": "",
    "gen_start": "1",
    "dec_rec": True,
    "export_ext": ".csv",
    "tab": 0,
}


def settings_path() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "二维码工具", "settings.json")


def load_settings() -> dict:
    """读取上次设置；文件不存在或内容损坏时安静地用默认值。"""
    cfg = dict(SETTING_DEFAULTS)
    try:
        with open(settings_path(), "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            for key in cfg:
                if key in raw:
                    cfg[key] = raw[key]
    except (OSError, ValueError, TypeError):
        return dict(SETTING_DEFAULTS)
    # 清洗：手工改坏配置也不会让界面崩
    if (not isinstance(cfg["gen_dir"], str)
            or (cfg["gen_dir"] and not os.path.isabs(cfg["gen_dir"]))):
        cfg["gen_dir"] = ""
    if cfg["gen_name"] not in ("内容命名", "序号命名"):
        cfg["gen_name"] = SETTING_DEFAULTS["gen_name"]
    if not isinstance(cfg["gen_prefix"], str):
        cfg["gen_prefix"] = ""
    cfg["gen_prefix"] = cfg["gen_prefix"][:64]
    if (not str(cfg["gen_start"]).isdigit()
            or int(cfg["gen_start"]) > 999999):
        cfg["gen_start"] = "1"
    cfg["gen_start"] = str(cfg["gen_start"])
    cfg["dec_rec"] = bool(cfg["dec_rec"])
    if cfg["export_ext"] not in EXPORT_LABEL_BY_EXT:
        cfg["export_ext"] = ".csv"
    try:
        cfg["tab"] = int(cfg["tab"])
    except (TypeError, ValueError):
        cfg["tab"] = 0
    if cfg["tab"] not in (0, 1):
        cfg["tab"] = 0
    return cfg


def save_settings(values: dict) -> bool:
    """原子写入；只读环境 / 权限受限时静默跳过，绝不影响使用。"""
    path = settings_path()
    tmp = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(values, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except (OSError, ValueError, TypeError):
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        return False


def _cjk_ratio(s: str) -> float:
    """统计 CJK 汉字占比，用于挑选最像正常文本的候选。"""
    if not s:
        return 0.0
    total = 0
    cjk = 0
    for c in s:
        if c.isspace():
            continue
        total += 1
        o = ord(c)
        # 基本汉字 + 扩展A + 兼容汉字
        if (0x4E00 <= o <= 0x9FFF) or (0x3400 <= o <= 0x4DBF) or (0xF900 <= o <= 0xFAFF):
            cjk += 1
    return cjk / total if total else 0.0

def _is_mojibake(s: str) -> bool:
    """粗略判断 s 是否像 mojibake（含大量拉丁扩展/生僻符号但不像正常文本）。"""
    if not s:
        return False
    # 含替换符 → 一定坏
    if "\ufffd" in s:
        return True
    # 含大量 Latin-1 扩展区字符（如 ä½ å¥½）→ 典型 latin-1 mojibake
    latin_like = sum(1 for c in s if 0x80 <= ord(c) <= 0x024F)
    if latin_like and latin_like / max(1, len(s)) > 0.3:
        return True
    # 含大量 CJK 兼容/生僻区字符（如 蝸ｯ蟇ｹ蝠頑弍）→ 典型 gbk mojibake
    rare_cjk = sum(1 for c in s if 0x3400 <= ord(c) <= 0x4DBF
                   or 0xF900 <= ord(c) <= 0xFAFF
                   or 0x20000 <= ord(c) <= 0x2FFFF)
    if rare_cjk and rare_cjk / max(1, len(s)) > 0.3:
        return True
    return False

def smart_decode(data: bytes) -> str:
    """
    兼容多种情况：
    1. data 是原始 UTF-8 字节 → 直接 UTF-8 解
    2. data 是 "UTF-8 字节被 Latin-1 显示后再 encode" 的产物 → latin-1 mojibake 修复
    3. data 是 "UTF-8 字节被 GBK 解后再 encode" 的产物 → gbk mojibake 修复
    4. data 是 GBK/Big5 等中文编码原始字节 → 按顺序尝试
    """
    # 先拿 UTF-8 候选
    utf8_str = None
    try:
        utf8_str = data.decode("utf-8")
    except UnicodeDecodeError:
        pass

    if utf8_str is not None:
        # bugfix: zbar 有时把 UTF-8 字节按 Shift_JIS 解释后重新编码返回,
        # 中文识别成生僻汉字+半角假名(如 "二维码工具" -> "莠檎ｻｴ遐∝…"),
        # 且表面汉字占比正常, 不触发 _is_mojibake。
        # 反向修复: 按 cp932 重新编码, 若能严格读回 UTF-8 且中文占比更高则采用
        try:
            sjis_fixed = utf8_str.encode("cp932").decode("utf-8")
            # 半角假名(U+FF61-FF9F)是 SJIS 误读的强特征, 用于修复
            # 纯字母/数字内容(如 é -> ﾃｩ)这类汉字占比不变的乱码
            has_hankana = any("\uff61" <= ch <= "\uff9f" for ch in utf8_str)
            if (sjis_fixed != utf8_str
                    and (_cjk_ratio(sjis_fixed) > _cjk_ratio(utf8_str)
                         or (has_hankana and "\ufffd" not in sjis_fixed))):
                return sjis_fixed
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
        # 若 UTF-8 解出来像乱码，尝试 mojibake 修复
        if _is_mojibake(utf8_str):
            # latin/cp1252 双层编码方向：能重新读回 UTF-8 基本即可信
            # (纯 ASCII 不会进这里；正常带重音符号的文本读不回 UTF-8)
            for codec in ("cp1252", "latin-1"):
                try:
                    latin_fixed = utf8_str.encode(codec, "ignore").decode("utf-8")
                    if latin_fixed:
                        return latin_fixed
                except (UnicodeEncodeError, UnicodeDecodeError):
                    continue
            # gbk 方向：修复结果汉字占比明显更高才采用
            try:
                gbk_fixed = utf8_str.encode("gbk", "ignore").decode("utf-8", "ignore")
                if (gbk_fixed and "\ufffd" not in gbk_fixed
                        and _cjk_ratio(gbk_fixed)
                        > _cjk_ratio(utf8_str) + 0.1):
                    return gbk_fixed
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass

        if "\ufffd" not in utf8_str:
            return utf8_str

    # 原始字节本身就是 GBK/Big5 等编码的情况
    for enc in ("gb18030", "gbk", "big5", "shift_jis"):
        try:
            s = data.decode(enc)
            if "\ufffd" not in s and not _is_mojibake(s):
                return s
        except (UnicodeDecodeError, UnicodeError):
            continue

    return data.decode("utf-8", errors="replace")


def make_qr_image(link: str) -> "Image.Image":
    """按工具统一参数生成二维码（UTF-8 字节写入、H 级纠错、白底黑块）。"""
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10, border=4)
    qr.add_data(link.encode("utf-8"))
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


def decode_qr_image(img: "Image.Image") -> list:
    """识别图片中所有二维码，返回文本列表；未识别到返回空列表。"""
    if zbar_decode is None:
        raise RuntimeError("缺少 pyzbar 库，请安装：pip install pyzbar")
    results = zbar_decode(img)
    if not results:
        # 放大重试：用 NEAREST 避免插值灰边导致误识别
        big = img.resize((img.width * 2, img.height * 2), Image.NEAREST)
        results = zbar_decode(big)
    return [smart_decode(r.data) for r in results]


def safe_filename(name: str, maxlen: int = 48) -> str:
    """把内容清洗成 Windows 合法文件名（含设备保留名兜底）。"""
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")[:maxlen].strip(" .")
    name = name or "qr"
    if name.split(".")[0].upper() in {
            "CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10))}:
        name = "_" + name
    return name


S_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _local(tag) -> str:
    """取 XML 标签本地名，兼容 transitional / strict 两套 OOXML 命名空间。"""
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _clean_items(items, check_header=True) -> list:
    """清单统一收尾：去空行；check_header 时首条若是表头则跳过（CSV 行为）。

    Excel 已在行级处理过表头，传 check_header=False，避免重复判定。
    """
    out, first = [], True
    for cell in items:
        cell = (cell or "").strip()
        if not cell:
            continue
        if check_header and first and cell.lower() in TABLE_HEADERS:
            first = False
            continue
        first = False
        out.append(cell)
    return out


def parse_docx_lines(path: str) -> list:
    """Word 文档按「一行一条」读取。

    正文段落 = 一行（段落内的手动换行再拆行）；表格每行取第一个非空
    单元格，备注列不会被当成二维码内容（Word 规则与 Excel 不同）。
    只读正文，不读页眉页脚 / 批注。
    """
    try:
        with zipfile.ZipFile(path) as z:
            try:
                data = z.read("word/document.xml")
            except KeyError:
                raise ValueError("不是有效的 .docx 文件（缺少正文）")
        root = ET.fromstring(data)
    except (zipfile.BadZipFile, OSError, ET.ParseError) as e:
        raise ValueError(f"Word 文档无法读取：{e}")

    def para_lines(p):
        parts, buf = [], []
        for el in p.iter():
            tag = _local(el.tag)
            if tag == "t" and el.text:
                buf.append(el.text)
            elif tag == "tab":
                buf.append(" ")
            elif tag in ("br", "cr"):
                parts.append("".join(buf).strip())
                buf = []
        parts.append("".join(buf).strip())
        return [s for s in parts if s]

    lines = []

    def walk(node):
        for child in node:
            tag = _local(child.tag)
            if tag == "p":
                lines.extend(para_lines(child))
            elif tag == "tbl":
                for tr in child.iter():
                    if _local(tr.tag) != "tr":
                        continue
                    cell = ""
                    for tc in tr:
                        if _local(tc.tag) != "tc":
                            continue
                        text = " ".join(
                            s for p in tc.iter() if _local(p.tag) == "p"
                            for s in para_lines(p)).strip()
                        if text:
                            cell = text
                            break      # 表格行只取第一个非空单元格
                    if cell:
                        lines.append(cell)
            elif tag in ("body", "sdt", "sdtContent"):
                walk(child)

    walk(root)
    return lines


def parse_xlsx_lines(path: str) -> list:
    """Excel 取第一个工作表，按行优先读取所有非空单元格，每格 = 一条。

    表头行（首格为表头词，或整行都是常见表头词）整行跳过；空单元格忽略。
    """
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            shared = []
            if "xl/sharedStrings.xml" in names:
                sroot = ET.fromstring(z.read("xl/sharedStrings.xml"))
                for si in sroot:
                    shared.append("".join(
                        t.text or "" for t in si.iter(S_NS + "t")))

            sheet = "xl/worksheets/sheet1.xml"
            if "xl/workbook.xml" in names:
                wb = ET.fromstring(z.read("xl/workbook.xml"))
                sh = next((e for e in wb.iter(S_NS + "sheet")), None)
                rid = sh.get(R_NS + "id") if sh is not None else None
                if rid and "xl/_rels/workbook.xml.rels" in names:
                    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
                    for rel in rels:
                        if rel.get("Id") == rid:
                            target = rel.get("Target", "")
                            if target.startswith("/"):
                                target = target.lstrip("/")
                            elif not target.startswith("xl/"):
                                target = "xl/" + target
                            if target in names:
                                sheet = target
                            break
            if sheet not in names:
                cands = sorted(n for n in names
                               if n.startswith("xl/worksheets/sheet")
                               and n.endswith(".xml"))
                if not cands:
                    raise ValueError("不是有效的 .xlsx 文件（找不到工作表）")
                sheet = cands[0]
            sroot = ET.fromstring(z.read(sheet))
    except (zipfile.BadZipFile, OSError, ET.ParseError, KeyError) as e:
        raise ValueError(f"Excel 表格无法读取：{e}")

    items = []
    first_row = True
    for row in sroot.iter(S_NS + "row"):
        cells = []
        for c in row.iter(S_NS + "c"):
            t = c.get("t")
            if t == "inlineStr":
                val = "".join(n.text or "" for n in c.iter(S_NS + "t"))
            else:
                v = c.find(S_NS + "v")
                val = "" if v is None or v.text is None else v.text
                if t == "s":
                    try:
                        val = shared[int(val)]
                    except (ValueError, IndexError):
                        val = ""
            val = val.strip()
            if val:
                cells.append(val)      # 所有方框都收，不再只取第一格
        if not cells:
            continue
        if first_row:
            first_row = False
            # 表头整行跳过：首格是表头词，或整行都是「编号/内容/备注」这类词
            if (cells[0].lower() in TABLE_HEADERS
                    or all(c.lower() in HEADER_WORDS for c in cells)):
                continue
        items.extend(cells)
    return _clean_items(items, check_header=False)


def parse_input_file(path: str) -> list:
    """读取清单：TXT 每行一条；CSV/TSV 每行首格一条；Excel 所有单元格；Word 按行。"""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".doc", ".xls"):
        raise ValueError("旧版 .doc/.xls 不支持，请另存为 .docx/.xlsx 或 CSV")
    if ext == ".docx":
        return parse_docx_lines(path)
    if ext == ".xlsx":
        return parse_xlsx_lines(path)
    with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as f:
        if ext in (".csv", ".tsv"):
            cells = (next((c.strip() for c in row if c.strip()), "")
                     for row in csv.reader(
                         f, delimiter="\t" if ext == ".tsv" else ","))
            return _clean_items(cells)
        return [ln.strip() for ln in f if ln.strip()]


# ----------------------------------------------------------------------
# 结果导出：Excel 四列表格 / Word、TXT 一行一条纯文本（标准库手写 OOXML，
# 无需安装 Office / 第三方库）
# ----------------------------------------------------------------------
_XML_BAD = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_OOXML_REL_NS = ("http://schemas.openxmlformats.org/officeDocument/2006/"
                 "relationships")
_S_NS_URI = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_W_NS_URI = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _xml_text(value) -> str:
    """转义为 XML 文本，同时剔除 XML 1.0 不允许的控制字符。"""
    s = "" if value is None else str(value)
    return escape(_XML_BAD.sub("", s))


def _col_letter(n: int) -> str:
    """列号转 Excel 列名：1 → A，27 → AA。"""
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _root_rels(target: str) -> str:
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<Relationships xmlns="{_PKG_REL_NS}">'
            f'<Relationship Id="rId1" Type="{_OOXML_REL_NS}/officeDocument" '
            f'Target="{target}"/></Relationships>')


def _doc_para(text, bold=False) -> str:
    """Word 段落：文本内换行转 <w:br/>，空格用 xml:space 保留。"""
    lines = str(text if text is not None else "").replace(
        "\r\n", "\n").replace("\r", "\n").split("\n")
    runs = []
    for i, line in enumerate(lines):
        if i:
            runs.append("<w:r><w:br/></w:r>")
        rpr = "<w:rPr><w:b/></w:rPr>" if bold else ""
        runs.append(f'<w:r>{rpr}<w:t xml:space="preserve">'
                    f'{_xml_text(line)}</w:t></w:r>')
    return "<w:p>" + "".join(runs) + "</w:p>"


def plain_result_lines(rows, col=-1) -> list:
    """抽取结果行里的正文（默认最后一列），压平换行、跳过空内容。

    Word / TXT 导出的「一行一条识别内容」与「复制全部结果」一致：
    条目内的换行压成空格，保证一个段落 / 一行就是一条，可直接拖回本工具。
    """
    out = []
    for r in rows:
        v = r[col] if r and -len(r) <= col < len(r) else ""
        v = re.sub(r"[\t\r\n]+", " ", "" if v is None else str(v)).strip()
        if v:
            out.append(v)
    return out


def write_xlsx(path, header, rows) -> None:
    """写出单工作表 .xlsx：表头 + 数据，单元格用 inlineStr。"""
    data = [list(header)] + [list(r) for r in rows]
    body = []
    for ri, row in enumerate(data, 1):
        cells = "".join(
            f'<c r="{_col_letter(ci)}{ri}" t="inlineStr">'
            f'<is><t xml:space="preserve">{_xml_text(v)}</t></is></c>'
            for ci, v in enumerate(row, 1))
        body.append(f'<row r="{ri}">{cells}</row>')
    sheet = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             f'<worksheet xmlns="{_S_NS_URI}"><sheetData>'
             + "".join(body) + '</sheetData></worksheet>')
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
          'content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxml'
          'formats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/xl/workbook.xml" ContentType="application/'
          'vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
          '<Override PartName="/xl/worksheets/sheet1.xml" ContentType='
          '"application/vnd.openxmlformats-officedocument.spreadsheetml.'
          'worksheet+xml"/>'
          '<Override PartName="/xl/styles.xml" ContentType="application/'
          'vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
          '</Types>')
    wb = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          f'<workbook xmlns="{_S_NS_URI}" xmlns:r="{_OOXML_REL_NS}">'
          '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/>'
          '</sheets></workbook>')
    wbrels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              f'<Relationships xmlns="{_PKG_REL_NS}">'
              f'<Relationship Id="rId1" Type="{_OOXML_REL_NS}/worksheet" '
              'Target="worksheets/sheet1.xml"/>'
              f'<Relationship Id="rId2" Type="{_OOXML_REL_NS}/styles" '
              'Target="styles.xml"/></Relationships>')
    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              f'<styleSheet xmlns="{_S_NS_URI}">'
              '<fonts count="1"><font><sz val="11"/>'
              '<name val="Calibri"/></font></fonts>'
              '<fills count="2"><fill><patternFill patternType="none"/>'
              '</fill><fill><patternFill patternType="gray125"/></fill>'
              '</fills><borders count="1"><border><left/><right/><top/>'
              '<bottom/><diagonal/></border></borders>'
              '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" '
              'fillId="0" borderId="0"/></cellStyleXfs>'
              '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" '
              'borderId="0" xfId="0"/></cellXfs>'
              '<cellStyles count="1"><cellStyle name="Normal" xfId="0" '
              'builtinId="0"/></cellStyles></styleSheet>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", _root_rels("xl/workbook.xml"))
        z.writestr("xl/workbook.xml", wb)
        z.writestr("xl/_rels/workbook.xml.rels", wbrels)
        z.writestr("xl/styles.xml", styles)
        z.writestr("xl/worksheets/sheet1.xml", sheet)


def write_docx_lines(path, lines) -> None:
    """写出 .docx：一段（一行）一条识别内容，无标题、无表格。"""
    body = "".join(_doc_para(line) for line in lines)
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           f'<w:document xmlns:w="{_W_NS_URI}"><w:body>'
           + body
           + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
           '</w:sectPr></w:body></w:document>')
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
          'content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxml'
          'formats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/word/document.xml" ContentType="application/'
          'vnd.openxmlformats-officedocument.wordprocessingml.document.'
          'main+xml"/></Types>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", _root_rels("word/document.xml"))
        z.writestr("word/document.xml", doc)


def parse_drop_paths(widget, data: str) -> list:
    """解析拖拽数据（Tcl list，可能含多个带花括号的路径）。

    不能用 tk.splitlist：它会把 Windows 路径里的反斜杠当 Tcl 转义符吃掉
    （C:\\Temp\\a.png -> C:Tempa.png）。这里只按花括号/空白分词，原样保留路径。
    """
    data = (data or "").strip()
    if not data:
        return []
    parts, buf, in_brace = [], [], False
    for ch in data:
        if ch == "{" and not in_brace:
            in_brace, buf = True, []
        elif ch == "}" and in_brace:
            parts.append("".join(buf))
            buf, in_brace = [], False
        elif in_brace:
            buf.append(ch)
        elif ch.isspace():
            if buf:
                parts.append("".join(buf))
                buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))
    parts = [p for p in parts if p]
    # 兼容未加花括号但含空格的单个路径
    if len(parts) > 1 and os.path.isfile(" ".join(parts)):
        parts = [" ".join(parts)]
    return parts


def default_out_dir() -> str:
    return os.path.join(os.path.expanduser("~"), "Desktop", DEFAULT_OUT_NAME)


def _rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def _load_ttf(px, bold):
    """加载微软雅黑（UI 字面），失败时逐级回退。"""
    candidates = [
        ("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc", 1),
        ("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc", 0),
        ("C:/Windows/Fonts/simhei.ttf" if bold else "C:/Windows/Fonts/simsun.ttc", 0),
        ("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf", 0),
    ]
    for path, idx in candidates:
        try:
            return ImageFont.truetype(path, px, index=idx)
        except Exception:
            continue
    return ImageFont.load_default()


def setup_style(root, S):
    """tkk 只保留输入框样式；按钮/卡片均为自绘圆角控件。"""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure(".", background=BG, foreground=TEXT, font=(FONT, 10),
                    selectbackground=ACCENT, selectforeground="#FFFFFF")
    style.configure("TEntry", fieldbackground="#FFFFFF", foreground=TEXT,
                    insertcolor=TEXT, bordercolor=BORDER,
                    lightcolor=BORDER, darkcolor=BORDER,
                    padding=round(4 * S), selectbackground=ACCENT,
                    selectforeground="#FFFFFF")
    style.map("TEntry",
              bordercolor=[("focus", ACCENT)],
              lightcolor=[("focus", ACCENT)],
              darkcolor=[("focus", ACCENT)],
              fieldbackground=[("readonly", "#FFFFFF")],
              foreground=[("readonly", TEXT)])


def set_app_icon(root):
    """运行时生成一枚二维码风格的应用图标，无需外部文件。"""
    try:
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, size - 1, size - 1], radius=14, fill=ACCENT)
        d.rounded_rectangle([7, 7, size - 8, size - 8], radius=7, fill="#FFFFFF")
        dark = "#1E3A8A"
        for x, y in ((13, 13), (37, 13), (13, 37)):
            d.rectangle([x, y, x + 13, y + 13], fill=dark)
            d.rectangle([x + 3, y + 3, x + 10, y + 10], fill="#FFFFFF")
            d.rectangle([x + 5, y + 5, x + 8, y + 8], fill=dark)
        for x, y in ((37, 37), (45, 37), (37, 45), (45, 45), (29, 45), (45, 29)):
            d.rectangle([x, y, x + 4, y + 4], fill=dark)
        root.iconphoto(True, ImageTk.PhotoImage(img))
    except Exception:
        pass


class UI:
    """用 PIL 渲染圆角/阴影/文字位图资源（超采样抗锯齿）。"""

    BTN_STYLES = {
        "primary": {
            "normal":  (ACCENT, ACCENT, "#FFFFFF", 0),
            "hover":   (ACCENT_HOVER, ACCENT_HOVER, "#FFFFFF", 0),
            "pressed": (ACCENT_ACTIVE, ACCENT_ACTIVE, "#FFFFFF", 1),
        },
        "secondary": {
            "normal":  ("#FCFDFF", "#E2E7F0", "#3D4759", 0),
            "hover":   ("#F3F6FB", "#D5DEEB", "#2A3242", 0),
            "pressed": ("#ECF1F8", "#CFD9E8", "#2A3242", 1),
        },
    }

    def __init__(self, root, S):
        self.root = root
        self.S = S
        self.dpi = root.winfo_fpixels("1i")
        self.SS = 4  # 超采样倍率
        self._fonts = {}
        self._dots = {}
        self._chips = {}
        self._placeholder = None

    def P(self, n):
        return round(n * self.S)

    def font(self, pt, bold=False):
        key = (pt, bold)
        if key not in self._fonts:
            px = max(8, round(pt * self.dpi / 72))
            self._fonts[key] = _load_ttf(px, bold)
        return self._fonts[key]

    # --- 底层渲染 ---
    def _base(self, w, h, color):
        img = Image.new("RGBA", (w * self.SS, h * self.SS), _rgb(color) + (255,))
        return img, ImageDraw.Draw(img)

    def _down(self, img, w, h):
        return img.resize((w, h), Image.LANCZOS)

    # --- 卡片背景：白色圆角 + 柔和投影 ---
    def card_bg(self, w, h, radius, margin):
        W, H = w + 2 * margin, h + 2 * margin
        SS = self.SS
        alpha = Image.new("L", (W * SS, H * SS), 0)
        d = ImageDraw.Draw(alpha)
        d.rounded_rectangle(
            [margin * SS, (margin + self.P(2)) * SS,
             (margin + w) * SS, (margin + self.P(2) + h) * SS],
            radius=radius * SS, fill=255)
        alpha = alpha.filter(ImageFilter.GaussianBlur(self.P(2.5) * SS))
        alpha = alpha.point(lambda v: int(v * 0.10))
        base = Image.new("RGBA", (W * SS, H * SS), _rgb(BG) + (255,))
        shadow = Image.new("RGBA", (W * SS, H * SS), (15, 23, 42, 255))
        shadow.putalpha(alpha)
        base.alpha_composite(shadow)
        d2 = ImageDraw.Draw(base)
        d2.rounded_rectangle(
            [margin * SS, margin * SS, (margin + w) * SS, (margin + h) * SS],
            radius=radius * SS, fill=_rgb(CARD) + (255,),
            outline=_rgb(BORDER) + (255,), width=SS)
        out = base.resize((W, H), Image.LANCZOS).convert("RGB")
        return ImageTk.PhotoImage(out, master=self.root)

    # --- 预览区背景 ---
    def preview_bg(self, size):
        img, d = self._base(size, size, CARD)
        d.rounded_rectangle([0, 0, size * self.SS - 1, size * self.SS - 1],
                            radius=PREV_R * self.SS, fill=_rgb(FIELD) + (255,),
                            outline=_rgb(FIELD_BORDER) + (255,), width=self.SS)
        out = self._down(img, size, size).convert("RGB")
        return ImageTk.PhotoImage(out, master=self.root)

    # --- 按钮：三态圆角位图（文字 1x 绘制保持锐利） ---
    def button_states(self, text, kind, w, pt=10):
        h = self.P(30)
        f = self.font(pt, kind == "primary")
        out = {}
        for state, (fill, border, fg, dy) in self.BTN_STYLES[kind].items():
            img, d = self._base(w, h, CARD)
            d.rounded_rectangle([0, 0, w * self.SS - 1, h * self.SS - 1],
                                radius=BTN_R * self.SS, fill=_rgb(fill) + (255,),
                                outline=_rgb(border) + (255,), width=self.SS)
            small = self._down(img, w, h).convert("RGB")
            ImageDraw.Draw(small).text((w / 2, h / 2 + dy), text, font=f,
                                       fill=fg, anchor="mm")
            out[state] = ImageTk.PhotoImage(small, master=self.root)
        return out

    # --- 标题序号圆角徽标 ---
    def chip(self, num):
        if num not in self._chips:
            s = self.P(22)
            img, d = self._base(s, s, CARD)
            d.rounded_rectangle([0, 0, s * self.SS - 1, s * self.SS - 1],
                                radius=self.P(7) * self.SS,
                                fill=_rgb(ACCENT) + (255,))
            small = self._down(img, s, s).convert("RGB")
            ImageDraw.Draw(small).text((s / 2, s / 2 + self.S / 2), str(num),
                                       font=self.font(10, True),
                                       fill="#FFFFFF", anchor="mm")
            self._chips[num] = ImageTk.PhotoImage(small, master=self.root)
        return self._chips[num]

    # --- 预览区占位图形（二维码风格） ---
    def placeholder(self):
        if self._placeholder is None:
            s = self.P(36)
            SS = self.SS
            img, d = self._base(s, s, FIELD)
            c = _rgb(PLACEHOLDER) + (255,)
            lw = max(2, round(s * 0.09)) * SS
            f = round(s * 0.30)
            m = round(s * 0.10)
            for x, y in ((m, m), (s - m - f, m), (m, s - m - f)):
                d.rounded_rectangle([x * SS, y * SS, (x + f) * SS, (y + f) * SS],
                                    radius=4 * SS, outline=c, width=lw)
                cxy = x + f // 2
                r = f * 0.16
                d.rectangle([(cxy - r) * SS, (cxy - r) * SS,
                             (cxy + r) * SS, (cxy + r) * SS], fill=c)
            for dx, dy in ((0.56, 0.56), (0.70, 0.56), (0.84, 0.56),
                           (0.56, 0.70), (0.70, 0.70), (0.56, 0.84)):
                r = s * 0.055
                d.ellipse([(s * dx - r) * SS, (s * dy - r) * SS,
                           (s * dx + r) * SS, (s * dy + r) * SS], fill=c)
            small = self._down(img, s, s).convert("RGB")
            self._placeholder = ImageTk.PhotoImage(small, master=self.root)
        return self._placeholder

    # --- 状态栏圆点 ---
    def dot(self, color):
        if color not in self._dots:
            s = max(5, self.P(8))
            img, d = self._base(s, s, CARD)
            d.ellipse([0, 0, s * self.SS - 1, s * self.SS - 1],
                      fill=_rgb(color) + (255,))
            self._dots[color] = ImageTk.PhotoImage(
                self._down(img, s, s).convert("RGB"), master=self.root)
        return self._dots[color]


class Btn(tk.Label):
    """自绘圆角按钮：悬停/按下三态 + 按下微沉降。"""

    def __init__(self, master, ui, text, command, kind="secondary",
                 width=None, pt=10):
        self.command = command
        if width is None:
            width = int(ui.font(pt, kind == "primary").getlength(text)) + ui.P(22)
        self.images = ui.button_states(text, kind, width, pt)
        super().__init__(master, image=self.images["normal"], bd=0,
                         bg=CARD, cursor="hand2", highlightthickness=0)
        self._down = False
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self._enabled = True

    def _show(self, state):
        self.configure(image=self.images[state])

    def set_enabled(self, on: bool):
        """批量任务运行时禁用按钮（Label 的 state=disabled 不拦截事件，故自行守卫）。"""
        self._enabled = bool(on)
        self.configure(cursor="hand2" if self._enabled else "arrow")
        if not self._enabled:
            self._down = False
            self._show("normal")

    def _on_enter(self, _e):
        if self._enabled and not self._down:
            self._show("hover")

    def _on_leave(self, _e):
        self._down = False
        self._show("normal")

    def _on_press(self, _e):
        if not self._enabled:
            return
        self._down = True
        self._show("pressed")

    def _on_release(self, e):
        if not self._down or not self._enabled:
            return
        self._down = False
        inside = (0 <= e.x < self.winfo_width()
                  and 0 <= e.y < self.winfo_height())
        self._show("hover" if inside else "normal")
        if inside and self.command:
            self.command()


class SlimScrollbar(tk.Canvas):
    """自绘细圆角滚动条：无箭头、淡轨道、悬停加深加宽、拖动变主题蓝。

    对外接口与 ttk.Scrollbar 一致：可当 Text / Treeview 的
    yscrollcommand / xscrollcommand 目标，command 指向 xview / yview。
    内容未溢出时只留白、不画滑块（保留占位，避免布局抖动）。
    """

    TRACK = "#F0F3F9"          # 极淡轨道
    THUMB = "#BFCBDF"          # 常态滑块
    THUMB_HOVER = "#94A5C1"    # 悬停
    THUMB_DRAG = ACCENT        # 拖动

    def __init__(self, master, orient="vertical", width=12, command=None, **kw):
        self._vertical = orient == "vertical"
        self._command = command
        self._thick = max(8, int(width))
        self._first, self._last = 0.0, 1.0
        self._hover = False
        self._drag = None
        self._imgs = {}            # 胶囊位图缓存：(长, 宽, 颜色) -> PhotoImage
        self._min_thumb = max(24, round(self._thick * 2.4))
        if self._vertical:
            kw.update(width=self._thick, height=1)
        else:
            kw.update(width=1, height=self._thick)
        kw.setdefault("bg", CARD)
        kw.setdefault("bd", 0)
        kw.setdefault("highlightthickness", 0)
        kw.setdefault("takefocus", 0)
        super().__init__(master, **kw)
        self.bind("<Configure>", lambda _e: self._draw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_motion)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<MouseWheel>", self._on_wheel)

    # --- 兼容 ttk.Scrollbar 的 command / set / get ---
    def configure(self, cnf=None, **kw):
        if isinstance(cnf, dict):
            kw = {**cnf, **kw}
            cnf = None
        if "command" in kw:
            self._command = kw.pop("command")
        return super().configure(cnf, **kw)

    config = configure

    def set(self, first, last):
        try:
            f, l = float(first), float(last)
        except (TypeError, ValueError):
            f, l = 0.0, 1.0
        self._first = min(1.0, max(0.0, f))
        self._last = min(1.0, max(0.0, l))
        self._draw()

    def get(self):
        return (self._first, self._last)

    def _invoke(self, *args):
        if not self._command:
            return
        if isinstance(self._command, str):
            self.tk.call(self._command, *args)
        else:
            self._command(*args)

    # --- 几何与绘制 ---
    def _metrics(self):
        """返回 (pad, 轨道长, 滑块长, 滑块起点)；内容未溢出时返回 None。"""
        length = self.winfo_height() if self._vertical else self.winfo_width()
        pad = max(2, round(self._thick * 0.18))
        track = length - 2 * pad
        span = min(1.0, max(0.0, self._last - self._first))
        if length < 12 or track <= 0 or span >= 0.999:
            return None
        tlen = min(track, max(self._min_thumb, round(track * span)))
        denom = 1.0 - span
        pos = pad + (self._first * (track - tlen) / denom if denom > 0 else 0)
        return pad, track, tlen, pos

    def _capsule_image(self, length, thick, color):
        """超采样画圆角胶囊再缩小，得到抗锯齿的平滑边缘；按尺寸缓存。"""
        key = (length, thick, color)
        if key not in self._imgs:
            ss = 3
            if self._vertical:
                big, small = (thick * ss, length * ss), (thick, length)
            else:
                big, small = (length * ss, thick * ss), (length, thick)
            im = Image.new("RGBA", big, (0, 0, 0, 0))
            ImageDraw.Draw(im).rounded_rectangle(
                [0, 0, big[0] - 1, big[1] - 1], radius=min(big) // 2,
                fill=color)
            self._imgs[key] = ImageTk.PhotoImage(
                im.resize(small, Image.LANCZOS), master=self)
        return self._imgs[key]

    def _band(self, a0, a1, thick, color):
        length = int(round(a1 - a0))
        thick = int(round(thick))
        if length < 1 or thick < 1:
            return
        img = self._capsule_image(length, thick, color)
        c = self._thick / 2.0
        mid = a0 + (a1 - a0) / 2.0
        if self._vertical:
            self.create_image(c, mid, image=img)
        else:
            self.create_image(mid, c, image=img)

    def _draw(self):
        self.delete("all")
        m = self._metrics()
        if m is None:
            return
        pad, track, tlen, pos = m
        active = self._hover or self._drag is not None
        track_w = max(3, round(self._thick * 0.30))
        thumb_w = max(5, round(self._thick * (0.72 if active else 0.52)))
        color = (self.THUMB_DRAG if self._drag else
                 self.THUMB_HOVER if self._hover else self.THUMB)
        self._band(pad, pad + track, track_w, self.TRACK)
        self._band(pos, pos + tlen, thumb_w, color)

    # --- 交互 ---
    def _along(self, e):
        return e.y if self._vertical else e.x

    def _on_enter(self, _e):
        self._hover = True
        self._draw()

    def _on_leave(self, _e):
        if self._drag:          # 拖出条外仍保持拖动
            return
        self._hover = False
        self._draw()

    def _on_press(self, e):
        m = self._metrics()
        if m is None:
            return
        pad, track, tlen, pos = m
        p = self._along(e)
        if pos <= p <= pos + tlen:
            self._drag = (p - pos, track, tlen, pad)
            self._draw()
        else:
            self._invoke("scroll", "1" if p > pos + tlen else "-1", "pages")

    def _on_motion(self, e):
        if not self._drag:
            return
        grab, track, tlen, pad = self._drag
        denom = track - tlen
        frac = (self._along(e) - grab - pad) / denom if denom > 0 else 0.0
        self._invoke("moveto", "%.6f" % min(1.0, max(0.0, frac)))

    def _on_release(self, _e):
        if not self._drag:
            return
        self._drag = None
        x, y = self.winfo_pointerxy()
        rx, ry = self.winfo_rootx(), self.winfo_rooty()
        self._hover = (rx <= x < rx + self.winfo_width()
                       and ry <= y < ry + self.winfo_height())
        self._draw()

    def _on_wheel(self, e):
        step = -3 if e.delta > 0 else 3
        self._invoke("scroll", str(step), "units")
        return "break"


class BatchWindow:
    """批量转码主窗口（程序的唯一窗口，直接以 Tk 根窗口为界面）。

    页签一 文本 → 二维码：TXT/CSV/TSV 清单或手工多行输入，批量生成 PNG。
    页签二 二维码 → 文本：多选图片 / 文件夹 / 拖拽，批量识别并导出 CSV/TXT。
    任务用 after() 分片执行，界面保持响应，可中途取消。
    """

    CHUNK_GEN = 4      # 每次事件循环处理条数
    CHUNK_DEC = 2      # 解码较慢，每片少一些

    def __init__(self, root):
        self.win = win = root
        win.title("二维码工具")
        win.configure(bg=BG)
        self.S = max(1.0, win.winfo_fpixels("1i") / 96.0)
        self.ui = UI(win, self.S)
        self.P = self.ui.P
        self.cfg = load_settings()
        self._last_export = self.cfg["export_ext"]
        self._save_job = None
        self._save_ready = False      # 构建期间不触发保存
        setup_style(win, self.S)
        set_app_icon(win)
        win.minsize(self.P(780), self.P(540))

        self._job = None
        self._running = False
        self._cancel = False
        self._kind = ""
        self.gen_rows = []
        self.dec_rows = []
        self.dec_paths = []
        self._dec_keys = set()
        self._clip_images = {}       # 虚拟路径 -> 剪贴板图片（只存内存，不落盘）
        self._clip_seq = 0
        self._gen_tasks = []
        self._gen_index = 0
        self._gen_used = set()
        self._gen_dir = ""
        self._gen_start = 1
        self._dec_index = 0

        self._init_style()
        self._build()
        w, h = self.P(900), self.P(630)
        x = max(0, (win.winfo_screenwidth() - w) // 2)
        y = max(0, (win.winfo_screenheight() - h) // 2)
        win.geometry(f"{w}x{h}+{x}+{y}")
        win.protocol("WM_DELETE_WINDOW", self.close)

        if TkinterDnD and hasattr(win, "drop_target_register"):
            try:
                win.drop_target_register(DND_FILES)
                win.dnd_bind("<<Drop>>", self.on_drop)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 样式与布局
    # ------------------------------------------------------------------
    def _init_style(self):
        P = self.P
        st = ttk.Style(self.win)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        # clam 主题的 Notebook.client / Notebook.tab 会画一圈 #9E9A91 深灰描边，
        # 设 borderwidth=0 也去不掉；把两个元素的边框三色都改成窗口底色，
        # 视觉上彻底去掉这圈把页面围起来的「黑框」。
        st.configure("TNotebook", background=BG, borderwidth=0,
                     bordercolor=BG, lightcolor=BG, darkcolor=BG)
        # 当前页签更大更醒目（大字号加粗 + 更多留白 + 主题色），
        # 未选中的页签收敛成小号淡色，避免「反客为主」。
        st.configure("TNotebook.Tab", background="#E9EEF7", foreground=MUTED,
                     padding=(P(12), P(4)), font=(FONT, 9),
                     bordercolor=BG, lightcolor=BG, darkcolor=BG)
        st.map("TNotebook.Tab",
               background=[("selected", CARD), ("active", "#DDE8FA")],
               foreground=[("selected", ACCENT), ("active", TEXT)],
               font=[("selected", (FONT, 10, "bold"))],
               padding=[("selected", (P(16), P(6)))])
        st.configure("Treeview", background="#FFFFFF", fieldbackground="#FFFFFF",
                     foreground=TEXT, bordercolor=BORDER, rowheight=P(24),
                     font=(FONT, 9))
        st.configure("Treeview.Heading", background="#F1F5FB", foreground=MUTED,
                     font=(FONT, 9, "bold"), relief="flat", padding=(P(4), P(4)))
        st.map("Treeview", background=[("selected", "#DBEAFE")],
               foreground=[("selected", TEXT)])
        st.configure("TCombobox", fieldbackground="#FFFFFF", background="#FFFFFF",
                     foreground=TEXT, arrowcolor=MUTED, bordercolor=BORDER)
        st.configure("TCheckbutton", background=CARD, foreground=TEXT,
                     font=(FONT, 9))
        st.map("TCheckbutton", background=[("active", CARD)])
        self._init_tick_checkbutton(st)

    def _init_tick_checkbutton(self, st):
        """clam 主题复选框选中时画的是叉号，换成蓝底白色对勾。"""
        size = max(14, self.P(16))
        s = size * 2

        def make(fill, outline, tick):
            im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            d.rounded_rectangle([2, 2, s - 3, s - 3], radius=s // 8,
                                fill=fill, outline=outline,
                                width=max(2, s // 16))
            if tick:
                d.line([(s * 0.28, s * 0.50), (s * 0.44, s * 0.66),
                        (s * 0.74, s * 0.28)],
                       fill="#FFFFFF", width=max(3, s // 10), joint="curve")
            return ImageTk.PhotoImage(im.resize((size, size), Image.LANCZOS),
                                     master=self.win)

        off = make(CARD, "#A9B4C8", False)
        hover = make("#F2F6FE", ACCENT, False)
        on = make(ACCENT, ACCENT, True)
        on_hover = make(ACCENT_HOVER, ACCENT_HOVER, True)
        # 必须持有引用，否则 PhotoImage 被 GC 后 Tcl 侧图片失效
        self._tick_images = (off, hover, on, on_hover)

        if "Tick.indicator" not in st.element_names():
            # 状态规则按「更具体」优先：悬停时同时带 selected+active，
            # 若把 ("active", hover) 放前面会先命中空框、把对勾盖掉。
            st.element_create("Tick.indicator", "image", off,
                              ("selected", "active", on_hover),
                              ("selected", on),
                              ("active", hover),
                              width=size, sticky="")
        layout = st.layout("TCheckbutton")

        def replace(node):
            out = []
            for name, opts in node:
                o = dict(opts)
                if "children" in o:
                    o["children"] = replace(o["children"])
                out.append(("Tick.indicator" if name == "Checkbutton.indicator"
                            else name, o))
            return out

        st.layout("Tick.TCheckbutton", replace(layout))
        st.configure("Tick.TCheckbutton", background=CARD, foreground=TEXT,
                     font=(FONT, 9), padding=2)
        st.map("Tick.TCheckbutton", background=[("active", CARD)])

    @staticmethod
    def _panel(parent):
        return tk.Frame(parent, bg=CARD, highlightthickness=1,
                        highlightbackground=BORDER, highlightcolor=BORDER, bd=0)

    @staticmethod
    def _label(parent, text, *, bold=False, muted=False, side=None, **kw):
        lbl = tk.Label(parent, text=text, bg=CARD,
                       fg=MUTED if muted else TEXT,
                       font=(FONT, 10, "bold") if bold else (FONT, 9),
                       highlightthickness=0, **kw)
        if side:
            lbl.pack(side=side)
        return lbl

    def _build(self):
        P = self.P
        outer = tk.Frame(self.win, bg=BG)
        outer.pack(fill="both", expand=True, padx=P(12), pady=P(10))
        nb = ttk.Notebook(outer)
        nb.pack(fill="both", expand=True)
        self.gen_frame = tk.Frame(nb, bg=BG)
        self.dec_frame = tk.Frame(nb, bg=BG)
        nb.add(self.gen_frame, text="  文本 → 二维码  ")
        nb.add(self.dec_frame, text="  二维码 → 文本  ")
        self.nb = nb
        self._build_gen(self.gen_frame)
        self._build_dec(self.dec_frame)
        # 设置变化后延迟落盘；当前页签也一起记住
        for var in (self.gen_dir_var, self.gen_name_var, self.gen_prefix_var,
                    self.gen_start_var, self.dec_rec_var):
            var.trace_add("write", self._schedule_save)
        nb.bind("<<NotebookTabChanged>>", self._schedule_save)
        if self.cfg["tab"] == 1:
            try:
                nb.select(1)
            except tk.TclError:
                pass
        self._save_ready = True
        foot = tk.Frame(outer, bg=BG)
        foot.pack(fill="x", pady=(P(8), 0))
        tk.Label(foot, text="提示：可直接把 TXT/CSV/Excel/Word 清单、二维码图片或文件夹拖入本窗口",
                 bg=BG, fg=MUTED, font=(FONT, 9), anchor="w",
                 highlightthickness=0).pack(side="left")

    def _make_tree(self, parent, cols, heads, widths):
        P = self.P
        wrap = tk.Frame(parent, bg=CARD)
        wrap.pack(fill="both", expand=True, padx=P(10), pady=(0, P(2)))
        vy = SlimScrollbar(wrap, orient="vertical", width=P(12))
        vy.pack(side="right", fill="y")
        vx = SlimScrollbar(wrap, orient="horizontal", width=P(12))
        vx.pack(side="bottom", fill="x")
        tv = ttk.Treeview(wrap, columns=cols, show="headings",
                          selectmode="extended",
                          yscrollcommand=vy.set, xscrollcommand=vx.set)
        tv.pack(side="left", fill="both", expand=True)
        vy.configure(command=tv.yview)
        vx.configure(command=tv.xview)
        for c, h, w in zip(cols, heads, widths):
            tv.heading(c, text=h, anchor="w")
            tv.column(c, width=P(w), minwidth=P(30), anchor="w",
                      stretch=c not in ("idx", "status"))
        tv.tag_configure("ok", foreground=OK)
        tv.tag_configure("err", foreground=ERR)
        tv.tag_configure("wait", foreground=MUTED)
        return tv

    def _build_gen(self, parent):
        P = self.P
        parent.columnconfigure(0, minsize=P(288))
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(0, weight=1)
        left = self._panel(parent)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, P(5)), pady=P(8))
        right = self._panel(parent)
        right.grid(row=0, column=1, sticky="nsew", padx=(P(5), 0), pady=P(8))

        # ===== 左：输入清单 =====
        head = tk.Frame(left, bg=CARD)
        head.pack(fill="x", padx=P(10), pady=(P(10), P(6)))
        self._label(head, "输入内容", bold=True, side="left")
        self.gen_count_var = tk.StringVar(value="共 0 条")
        tk.Label(head, textvariable=self.gen_count_var, bg=CARD, fg=MUTED,
                 font=(FONT, 9), highlightthickness=0).pack(side="right")

        # 固定高度区块先打包到底部，窗口缩小时也不会把设置项挤没
        fixed = tk.Frame(left, bg=CARD)
        fixed.pack(side="bottom", fill="x")
        tk.Label(fixed, text="一行 = 一张二维码，空行自动忽略", bg=CARD,
                 fg=MUTED, font=(FONT, 9), anchor="w",
                 highlightthickness=0).pack(fill="x", padx=P(10), pady=(P(5), 0))
        row = tk.Frame(fixed, bg=CARD)
        row.pack(fill="x", padx=P(10), pady=P(6))
        Btn(row, self.ui, "导入文件", self.import_file, pt=9).pack(side="left")
        Btn(row, self.ui, "粘贴", self.paste_lines, pt=9).pack(side="left", padx=(P(5), 0))
        Btn(row, self.ui, "清空", self.clear_lines, pt=9).pack(side="left", padx=(P(5), 0))

        # ===== 左：输出位置 =====
        tk.Frame(fixed, bg=DIVIDER, height=1, highlightthickness=0,
                 bd=0).pack(fill="x", padx=P(10), pady=(0, P(8)))
        self._label(fixed, "输出位置", bold=True, anchor="w").pack(fill="x", padx=P(10))
        drow = tk.Frame(fixed, bg=CARD)
        drow.pack(fill="x", padx=P(10), pady=(P(6), 0))
        self.gen_dir_var = tk.StringVar(
            value=self.cfg["gen_dir"] or default_out_dir())
        ttk.Entry(drow, textvariable=self.gen_dir_var, font=(FONT, 9)).pack(
            side="left", fill="x", expand=True, padx=(0, P(5)))
        Btn(drow, self.ui, "浏览", self.choose_dir, pt=9).pack(side="left")

        orow = tk.Frame(fixed, bg=CARD)
        orow.pack(fill="x", padx=P(10), pady=(P(8), 0))
        self._label(orow, "命名", muted=True, side="left")
        self.gen_name_var = tk.StringVar(value=self.cfg["gen_name"])
        ttk.Combobox(orow, textvariable=self.gen_name_var, state="readonly",
                     values=["内容命名", "序号命名"], width=9,
                     font=(FONT, 9)).pack(side="left", padx=P(5))
        self._label(orow, "前缀", muted=True).pack(side="left", padx=(P(8), 0))
        self.gen_prefix_var = tk.StringVar(value=self.cfg["gen_prefix"])
        ttk.Entry(orow, textvariable=self.gen_prefix_var, width=7,
                  font=(FONT, 9)).pack(side="left", padx=(P(4), 0))

        nrow = tk.Frame(fixed, bg=CARD)
        nrow.pack(fill="x", padx=P(10), pady=(P(8), P(12)))
        self._label(nrow, "起始序号", muted=True, side="left")
        self.gen_start_var = tk.StringVar(value=self.cfg["gen_start"])
        ttk.Entry(nrow, textvariable=self.gen_start_var, width=6,
                  font=(FONT, 9)).pack(side="left", padx=(P(5), 0))
        tk.Label(nrow, text="PNG · H 级纠错", bg=CARD, fg=MUTED,
                 font=(FONT, 9), highlightthickness=0).pack(side="right")

        # 输入区最后打包，占满剩余空间并可自由伸缩
        tw = tk.Frame(left, bg=CARD)
        tw.pack(side="top", fill="both", expand=True, padx=P(10))
        sb = SlimScrollbar(tw, orient="vertical", width=P(12))
        sb.pack(side="right", fill="y")
        self.gen_text = tk.Text(tw, wrap="none", undo=True, width=26, height=8,
                                font=(FONT, 10), bg="#FFFFFF", fg=TEXT,
                                insertbackground=TEXT, relief="flat", bd=0,
                                highlightthickness=1,
                                highlightbackground=BORDER,
                                highlightcolor=ACCENT, yscrollcommand=sb.set)
        self.gen_text.pack(side="left", fill="both", expand=True)
        self.gen_text.bind("<KeyRelease>", lambda _e: self.update_gen_count())
        sb.configure(command=self.gen_text.yview)

        # ===== 右：结果 =====
        rhead = tk.Frame(right, bg=CARD)
        rhead.pack(fill="x", padx=P(10), pady=(P(10), P(6)))
        self._label(rhead, "生成结果", bold=True, side="left")
        self.gen_status_var = tk.StringVar(value="就绪")
        tk.Label(rhead, textvariable=self.gen_status_var, bg=CARD,
                 fg=STATUS_FG, font=(FONT, 9), anchor="e",
                 highlightthickness=0).pack(side="right", fill="x", expand=True)
        self.gen_tree = self._make_tree(
            right, ("idx", "content", "status", "file"),
            ("#", "内容", "状态", "输出文件"), (36, 190, 90, 170))
        row = tk.Frame(right, bg=CARD)
        row.pack(fill="x", padx=P(10), pady=P(10))
        self.gen_start_btn = Btn(row, self.ui, "开始生成", self.start_gen,
                                 kind="primary")
        self.gen_start_btn.pack(side="left")
        self.gen_cancel_btn = Btn(row, self.ui, "取消", self.cancel_job)
        self.gen_cancel_btn.pack(side="left", padx=(P(6), 0))
        Btn(row, self.ui, "打开目录", self.open_out_dir).pack(side="left", padx=(P(6), 0))
        self.gen_cancel_btn.set_enabled(False)

    def _build_dec(self, parent):
        P = self.P
        panel = self._panel(parent)
        # 左边不留外边距：识别页白框左边缘与「文本 → 二维码」页签、
        # 生成页左卡片对齐；右侧仍保留原留白。
        panel.pack(fill="both", expand=True, padx=(0, P(8)), pady=P(8))

        bar = tk.Frame(panel, bg=CARD)
        bar.pack(fill="x", padx=P(10), pady=(P(10), P(6)))
        Btn(bar, self.ui, "添加图片", self.add_images, pt=9).pack(side="left")
        Btn(bar, self.ui, "添加文件夹", self.add_folder, pt=9).pack(side="left", padx=(P(5), 0))
        Btn(bar, self.ui, "剪贴板粘贴", self.paste_clip_image,
            pt=9).pack(side="left", padx=(P(5), 0))
        Btn(bar, self.ui, "清空", self.clear_paths, pt=9).pack(side="left", padx=(P(5), 0))
        self.dec_rec_var = tk.BooleanVar(value=self.cfg["dec_rec"])
        ttk.Checkbutton(bar, text="包含子文件夹", variable=self.dec_rec_var,
                        style="Tick.TCheckbutton").pack(side="left", padx=(P(12), 0))
        self.dec_count_var = tk.StringVar(value="共 0 张图片")
        tk.Label(bar, textvariable=self.dec_count_var, bg=CARD, fg=MUTED,
                 font=(FONT, 9), highlightthickness=0).pack(side="right")

        head = tk.Frame(panel, bg=CARD)
        head.pack(fill="x", padx=P(10), pady=(0, P(6)))
        self._label(head, "识别结果", bold=True, side="left")
        self.dec_status_var = tk.StringVar(value="就绪")
        tk.Label(head, textvariable=self.dec_status_var, bg=CARD,
                 fg=STATUS_FG, font=(FONT, 9), anchor="e",
                 highlightthickness=0).pack(side="right", fill="x", expand=True)
        self.dec_tree = self._make_tree(
            panel, ("idx", "file", "status", "result"),
            ("#", "文件名", "状态", "识别结果"), (36, 180, 100, 330))
        self.dec_tree.bind("<Double-Button-1>", self.copy_dec_row)
        row = tk.Frame(panel, bg=CARD)
        row.pack(fill="x", padx=P(10), pady=P(10))
        self.dec_start_btn = Btn(row, self.ui, "开始识别", self.start_dec,
                                 kind="primary")
        self.dec_start_btn.pack(side="left")
        self.dec_cancel_btn = Btn(row, self.ui, "取消", self.cancel_job)
        self.dec_cancel_btn.pack(side="left", padx=(P(6), 0))
        Btn(row, self.ui, "复制结果", self.copy_dec_results).pack(side="left", padx=(P(6), 0))
        Btn(row, self.ui, "导出结果", self.export_dec).pack(side="left", padx=(P(6), 0))
        self.dec_cancel_btn.set_enabled(False)

    # ------------------------------------------------------------------
    # 通用状态
    # ------------------------------------------------------------------
    def _status(self, kind, text):
        (self.gen_status_var if kind == "gen" else self.dec_status_var).set(text)

    def _progress(self, kind, done, total):
        self._status(kind, f"处理中 {done}/{total}")

    def _set_running(self, kind, on):
        self._running = on
        self._kind = kind if on else ""
        if on:
            self._cancel = False
        self.gen_start_btn.set_enabled(not on)
        self.dec_start_btn.set_enabled(not on)
        self.gen_cancel_btn.set_enabled(on and kind == "gen")
        self.dec_cancel_btn.set_enabled(on and kind == "dec")

    def _finish(self, kind, cancelled=False):
        if self._job is not None:
            try:
                self.win.after_cancel(self._job)
            except Exception:
                pass
            self._job = None
        rows = self.gen_rows if kind == "gen" else self.dec_rows
        total = len(self._gen_tasks) if kind == "gen" else len(self.dec_paths)
        ok = sum(1 for r in rows if r["tag"] == "ok")
        bad = len(rows) - ok
        if cancelled:
            msg = f"已取消：完成 {len(rows)}/{total} 项"
        else:
            msg = f"完成：成功 {ok} 项，失败 {bad} 项"
            if kind == "gen":
                msg += f" → {self._gen_dir}"
        self._set_running(kind, False)
        self._status(kind, msg)

    def cancel_job(self):
        if not self._running:
            return
        self._cancel = True
        self._status(self._kind, "正在取消…")

    # ------------------------------------------------------------------
    # 上次设置
    # ------------------------------------------------------------------
    def _cur_tab(self):
        try:
            return max(0, min(1, self.nb.index(self.nb.select())))
        except (tk.TclError, AttributeError):
            return 0

    def _collect_settings(self):
        return {
            "version": 1,
            "gen_dir": self.gen_dir_var.get(),
            "gen_name": self.gen_name_var.get(),
            "gen_prefix": self.gen_prefix_var.get(),
            "gen_start": self.gen_start_var.get(),
            "dec_rec": bool(self.dec_rec_var.get()),
            "export_ext": self._last_export,
            "tab": self._cur_tab(),
        }

    def _schedule_save(self, *_args):
        """设置变化后合并 400ms 内的多次改动，避免逐字写盘。"""
        if not self._save_ready:
            return
        if self._save_job is not None:
            try:
                self.win.after_cancel(self._save_job)
            except tk.TclError:
                pass
        self._save_job = self.win.after(400, self._save_now)

    def _save_now(self):
        self._save_job = None
        try:
            save_settings(self._collect_settings())
        except Exception:
            pass

    def close(self):
        """关闭唯一主窗口 = 退出程序。"""
        self._cancel = True
        self._save_ready = False
        if self._save_job is not None:
            try:
                self.win.after_cancel(self._save_job)
            except tk.TclError:
                pass
            self._save_job = None
        self._save_now()
        if self._job is not None:
            try:
                self.win.after_cancel(self._job)
            except Exception:
                pass
            self._job = None
        self._running = False
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # 页签一：文本 → 二维码
    # ------------------------------------------------------------------
    def gen_lines(self):
        return [ln.strip() for ln in
                self.gen_text.get("1.0", "end").splitlines() if ln.strip()]

    def update_gen_count(self):
        self.gen_count_var.set(f"共 {len(self.gen_lines())} 条")

    def insert_lines(self, lines):
        if not lines:
            return 0
        cur = self.gen_text.get("1.0", "end")
        if cur.strip() and not cur.endswith("\n"):
            self.gen_text.insert("end", "\n")
        self.gen_text.insert("end", "\n".join(lines) + "\n")
        self.gen_text.see("end")
        self.update_gen_count()
        return len(lines)

    def _import_paths(self, paths):
        """导入多个清单文件，返回 (成功路径列表, 总条数)。

        单个文件失败不影响其余文件，失败原因汇总成一次弹窗。
        """
        oks, total, errors = [], 0, []
        for path in paths:
            try:
                total += self.insert_lines(parse_input_file(path))
                oks.append(path)
            except Exception as e:
                errors.append(f"{os.path.basename(path)}：{e}")
        if errors:
            detail = "\n".join(errors[:8])
            if len(errors) > 8:
                detail += f"\n…另有 {len(errors) - 8} 个文件失败"
            messagebox.showerror(
                "导入失败" if not oks else "部分文件导入失败",
                f"成功 {len(oks)} 个文件，失败 {len(errors)} 个：\n{detail}",
                parent=self.win)
        return oks, total

    def import_file(self):
        if self._running:
            return
        paths = filedialog.askopenfilenames(
            parent=self.win, title="导入文件（可多选）",
            filetypes=TEXT_FILETYPES)
        if not paths:
            return
        oks, total = self._import_paths(paths)
        if not oks:
            self._status("gen", "导入失败")
            return
        detail = (os.path.basename(oks[0]) if len(oks) == 1
                  else f"{len(oks)} 个文件")
        self._status("gen", f"已导入 {total} 条：{detail}")

    def paste_lines(self):
        if self._running:
            return
        try:
            text = self.win.clipboard_get()
        except tk.TclError:
            text = ""
        if not text.strip():
            messagebox.showwarning("提示", "剪贴板中没有文字", parent=self.win)
            return
        self.insert_lines([ln.strip() for ln in text.splitlines() if ln.strip()])

    def clear_lines(self):
        if self._running:
            return
        self.gen_text.delete("1.0", "end")
        self.update_gen_count()

    def choose_dir(self):
        if self._running:
            return
        d = filedialog.askdirectory(parent=self.win, title="选择输出目录",
                                    initialdir=self.gen_dir_var.get())
        if d:
            self.gen_dir_var.set(d)

    def open_out_dir(self):
        d = self.gen_dir_var.get().strip()
        if not os.path.isdir(d):
            messagebox.showwarning("提示", "输出目录还不存在，请先生成二维码",
                                   parent=self.win)
            return
        try:
            os.startfile(d)          # Windows 资源管理器
        except Exception:
            webbrowser.open(d)

    def _unique_name(self, i, text):
        prefix = self.gen_prefix_var.get().strip()
        if self.gen_name_var.get() == "内容命名":
            base = safe_filename(text)
        else:
            base = f"{self._gen_start + i:03d}"
        name = f"{prefix}{base}.png"
        low, n = name.lower(), 2
        while low in self._gen_used:
            name = f"{prefix}{base}_{n}.png"
            low, n = name.lower(), n + 1
        self._gen_used.add(low)
        return name

    def start_gen(self):
        if self._running:
            return
        lines = self.gen_lines()
        if not lines:
            messagebox.showwarning("提示", "请先输入或导入要生成的内容（每行一条）",
                                   parent=self.win)
            return
        outdir = self.gen_dir_var.get().strip()
        if not outdir:
            messagebox.showwarning("提示", "请先选择输出目录", parent=self.win)
            return
        try:
            os.makedirs(outdir, exist_ok=True)
        except OSError as e:
            messagebox.showerror("输出目录不可用", str(e), parent=self.win)
            return
        try:
            start = max(0, int(self.gen_start_var.get().strip()))
        except ValueError:
            start = 1

        self._gen_dir = outdir
        self._gen_start = start
        self._gen_tasks = lines
        self._gen_index = 0
        self._gen_used = {f.lower() for f in os.listdir(outdir)}  # 不覆盖已有文件
        self.gen_rows = []
        self.gen_tree.delete(*self.gen_tree.get_children())
        self._set_running("gen", True)
        self.update_gen_count()
        self._gen_step()

    def _gen_step(self):
        if self._cancel:
            self._finish("gen", cancelled=True)
            return
        total = len(self._gen_tasks)
        for _ in range(self.CHUNK_GEN):
            if self._gen_index >= total:
                break
            i = self._gen_index
            text = self._gen_tasks[i]
            path, tag = "", "err"
            try:
                img = make_qr_image(text)
                path = os.path.join(self._gen_dir, self._unique_name(i, text))
                img.save(path, "PNG")
                status, tag = "成功", "ok"
            except Exception as e:
                status, path = f"失败：{e}", ""
            self.gen_rows.append({"idx": i + 1, "content": text,
                                  "status": status, "file": path, "tag": tag})
            self.gen_tree.insert("", "end",
                                 values=(i + 1, text, status, os.path.basename(path)),
                                 tags=(tag,))
            self._gen_index += 1
        self.gen_tree.yview_moveto(1)
        self._progress("gen", self._gen_index, total)
        if self._gen_index >= total:
            self._finish("gen")
        else:
            self._job = self.win.after(1, self._gen_step)

    # ------------------------------------------------------------------
    # 页签二：二维码 → 文本
    # ------------------------------------------------------------------
    def add_images(self):
        if self._running:
            return
        paths = filedialog.askopenfilenames(parent=self.win,
                                            title="选择二维码图片（可多选）",
                                            filetypes=IMG_FILETYPES)
        if paths:
            self.add_paths(paths, switch=False)

    def add_folder(self):
        if self._running:
            return
        d = filedialog.askdirectory(parent=self.win, title="选择图片文件夹")
        if d:
            self.add_paths([d], switch=False)

    def paste_clip_image(self):
        """把剪贴板里的图片直接加入待识别列表（只存内存，不生成临时文件）。

        支持截图 / 浏览器「复制图片」（CF_DIB、PNG）以及资源管理器里复制的
        图片文件（CF_HDROP）；文件列表仍走原有的 add_paths 过滤与递归逻辑。
        """
        if self._running:
            return
        try:
            data = ImageGrab.grabclipboard()
        except Exception as e:
            messagebox.showwarning("提示", f"读取剪贴板失败：{e}",
                                   parent=self.win)
            return
        if isinstance(data, list):
            added = self.add_paths([p for p in data if p], switch=False)
            if not added:
                messagebox.showwarning("提示", "复制的文件里没有可用图片",
                                       parent=self.win)
            return
        if not isinstance(data, Image.Image):
            messagebox.showwarning("提示", "剪贴板里没有图片，请先截图或复制图片",
                                   parent=self.win)
            return
        try:
            img = data.convert("RGB")
            img.load()
        except Exception as e:
            messagebox.showwarning("提示", f"剪贴板图片无法读取：{e}",
                                   parent=self.win)
            return
        self._clip_seq += 1
        virtual = os.path.abspath(f"剪贴板图片_{self._clip_seq:02d}.png")
        key = os.path.normcase(virtual)
        if key in self._dec_keys:
            return
        self._dec_keys.add(key)
        self.dec_paths.append(virtual)
        self._clip_images[virtual] = img
        self.refresh_dec_list()
        self._status("dec", f"已粘贴剪贴板图片，共 {len(self.dec_paths)} 张")

    def _add_one(self, path):
        if not path.lower().endswith(IMAGE_EXTS):
            return 0
        key = os.path.normcase(os.path.abspath(path))
        if key in self._dec_keys:
            return 0
        self._dec_keys.add(key)
        self.dec_paths.append(path)
        return 1

    def add_paths(self, paths, switch=True):
        """加入图片（可传文件、文件夹混合）；返回新增数量。"""
        if self._running:
            return 0
        if switch:
            self.nb.select(self.dec_frame)
        added = 0
        for p in paths:
            if os.path.isdir(p):
                if self.dec_rec_var.get():
                    for root, _dirs, files in os.walk(p):
                        for f in sorted(files):
                            added += self._add_one(os.path.join(root, f))
                else:
                    try:
                        names = sorted(os.listdir(p))
                    except OSError:
                        names = []
                    for f in names:
                        added += self._add_one(os.path.join(p, f))
            else:
                added += self._add_one(p)
        self.refresh_dec_list()
        if added:
            self._status("dec", f"新增 {added} 张图片，共 {len(self.dec_paths)} 张")
        return added

    def refresh_dec_list(self):
        self.dec_tree.delete(*self.dec_tree.get_children())
        for i, p in enumerate(self.dec_paths, 1):
            self.dec_tree.insert("", "end",
                                 values=(i, os.path.basename(p), "待识别", ""),
                                 tags=("wait",))
        self.dec_count_var.set(f"共 {len(self.dec_paths)} 张图片")

    def clear_paths(self):
        if self._running:
            return
        self.dec_paths.clear()
        self._dec_keys.clear()
        self._clip_images.clear()
        self.dec_rows = []
        self.refresh_dec_list()
        self._status("dec", "就绪")

    def start_dec(self):
        if self._running:
            return
        if not self.dec_paths:
            messagebox.showwarning("提示", "请先添加二维码图片或文件夹",
                                   parent=self.win)
            return
        if zbar_decode is None:
            messagebox.showerror("错误", "缺少 pyzbar 库，请安装：pip install pyzbar",
                                 parent=self.win)
            return
        self.dec_rows = []
        self.dec_tree.delete(*self.dec_tree.get_children())
        self._dec_index = 0
        self._set_running("dec", True)
        self._dec_step()

    def _dec_step(self):
        if self._cancel:
            self._finish("dec", cancelled=True)
            return
        total = len(self.dec_paths)
        for _ in range(self.CHUNK_DEC):
            if self._dec_index >= total:
                break
            i = self._dec_index
            path = self.dec_paths[i]
            name = os.path.basename(path)
            texts, err = [], ""
            try:
                clip = self._clip_images.get(path)
                if clip is not None:
                    img = clip.convert("RGB")
                else:
                    with Image.open(path) as im:
                        img = im.convert("RGB")
                texts = decode_qr_image(img)
            except Exception as e:
                err = str(e)
            if texts:
                result = " | ".join(texts)
                status = "成功" if len(texts) == 1 else f"成功（{len(texts)} 个）"
                tag = "ok"
            else:
                result = ""
                status = f"失败：{err}" if err else "未识别到二维码"
                tag = "err"
            self.dec_rows.append({"idx": i + 1, "file": name, "path": path,
                                  "status": status, "result": result, "tag": tag})
            self.dec_tree.insert("", "end", values=(i + 1, name, status, result),
                                 tags=(tag,))
            self._dec_index += 1
        self.dec_tree.yview_moveto(1)
        self._progress("dec", self._dec_index, total)
        if self._dec_index >= total:
            self._finish("dec")
        else:
            self._job = self.win.after(1, self._dec_step)

    def copy_dec_row(self, event):
        """双击结果表格某一行：只把这一行的识别内容复制到剪贴板。"""
        tv = self.dec_tree
        iid = tv.identify_row(event.y)
        if not iid:
            return
        i = tv.index(iid)
        values = tv.item(iid, "values")
        # 只认识别成功的行；「待识别 / 未识别到二维码 / 失败」不覆盖剪贴板。
        if (i >= len(self.dec_rows) or len(values) < 3
                or not str(values[2]).startswith("成功")):
            self._status("dec", f"第 {i + 1} 行没有识别结果")
            return
        text = self.dec_rows[i]["result"]
        if not text:
            self._status("dec", f"第 {i + 1} 行没有识别结果")
            return
        # 用 dec_rows 里的原文，不读表格文本，避免特殊字符被 Tcl 列表转义。
        self.win.clipboard_clear()
        self.win.clipboard_append(text)
        short = text if len(text) <= 24 else text[:24] + "…"
        self._status("dec", f"已复制第 {i + 1} 行：{short}")

    def copy_dec_results(self):
        texts = [r["result"] for r in self.dec_rows if r["result"]]
        if not texts:
            messagebox.showwarning("提示", "还没有可复制的识别结果", parent=self.win)
            return
        self.win.clipboard_clear()
        self.win.clipboard_append("\n".join(texts))
        self._status("dec", f"已复制 {len(texts)} 条识别结果")

    def export_dec(self):
        self.export_rows(
            "批量识别结果", ("序号", "文件名", "状态", "识别结果"),
            [(r["idx"], r["file"], r["status"], r["result"])
             for r in self.dec_rows], "dec")

    # ------------------------------------------------------------------
    # 导出 / 拖拽
    # ------------------------------------------------------------------
    def export_rows(self, title, header, rows, kind, text_col=-1):
        """表格格式（CSV/Excel）写四列；Word/TXT 只写正文列，一行一条。"""
        if not rows:
            messagebox.showwarning("提示", "还没有可导出的结果", parent=self.win)
            return
        # -typevariable 让原生保存对话框把「保存类型」的下拉选择写进变量，
        # 避免对话框没自动补扩展名时，选了 Word/Excel 却兜底存成 CSV。
        type_var = tk.StringVar(
            value=EXPORT_LABEL_BY_EXT.get(self._last_export,
                                          EXPORT_TYPES[0][0]))
        path = filedialog.asksaveasfilename(
            parent=self.win, title="导出结果", initialfile=title,
            filetypes=[(label, "*" + ext) for label, ext in EXPORT_TYPES],
            typevariable=type_var)
        if not path:
            return
        chosen = EXPORT_EXT_BY_LABEL.get(type_var.get())
        ext = chosen or os.path.splitext(path)[1].lower()
        if ext not in EXPORT_LABEL_BY_EXT:
            ext = ".csv"
        # 文件名扩展名始终与实际写出的格式一致
        path = os.path.splitext(path)[0] + ext
        # Word / TXT 是纯文本清单：只保留识别内容，一行一条（跳过未识别的）
        plain = (plain_result_lines(rows, text_col)
                 if ext in (".docx", ".txt") else None)
        if plain is not None and not plain:
            messagebox.showwarning("提示", "没有可导出的识别内容", parent=self.win)
            return
        try:
            if ext == ".xlsx":
                write_xlsx(path, header, rows)
            elif ext == ".docx":
                write_docx_lines(path, plain)
            else:
                with open(path, "w",
                          encoding="utf-8-sig" if ext == ".csv" else "utf-8",
                          newline="") as f:
                    if ext == ".csv":
                        writer = csv.writer(f)
                        writer.writerow(header)
                        writer.writerows(rows)
                    else:
                        f.write("\n".join(plain) + "\n")
        except (OSError, ValueError) as e:
            messagebox.showerror("导出失败", str(e), parent=self.win)
            return
        self._last_export = ext
        self._schedule_save()
        fmt = f"{EXPORT_LABEL_BY_EXT[ext]}（{ext}）"
        if plain is None:
            count, note = f"{len(rows)} 条记录", "含四列表格"
        else:
            count = f"{len(plain)} 条识别内容"
            note = "一行一条，未识别的已跳过"
        self._status(kind, f"已导出 {count}（{fmt}）：{path}")
        messagebox.showinfo("导出完成",
                            f"已导出 {count}\n格式：{fmt}\n{note}\n{path}",
                            parent=self.win)

    def on_drop(self, event):
        if self._running:
            messagebox.showinfo("提示", "任务进行中，请等待完成或先取消",
                                parent=self.win)
            return
        paths = parse_drop_paths(self.win, event.data)
        docs = [p for p in paths if os.path.splitext(p)[1].lower() in LIST_EXTS]
        if docs:
            self.nb.select(self.gen_frame)
            oks, total = self._import_paths(docs)
            self._status("gen", f"已导入 {total} 条（{len(oks)}/{len(docs)} 个清单文件）")
        rest = [p for p in paths if p not in docs]
        if rest:
            self.add_paths(rest, switch=True)


def main():
    # 高 DPI 感知（必须在创建窗口前设置，文字和控件才会清晰）
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    # 使用 TkinterDnD.Tk 代替 tk.Tk 以支持拖拽 (如果可用)
    if TkinterDnD:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()

    root.withdraw()   # 构建期间隐藏，避免窗口闪现
    BatchWindow(root)
    root.deiconify()
    root.lift()
    root.focus_force()
    root.mainloop()


if __name__ == "__main__":
    main()
