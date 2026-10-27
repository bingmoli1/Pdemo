# -*- coding: utf-8 -*-
"""自动发货主逻辑：
1) 每隔 N 秒轮询闲鱼网页版"消息"页的会话列表；
2) 某个会话的最后一条消息命中触发词（默认只有"买家已付款"系统消息）→ 点进会话，从右侧聊天面板匹配商品；
3) 把该商品配置的"发货内容"整段（可多行）发给买家；内容不消耗、不删除，可反复使用；
4) 按（买家+商品）去重，同一单只发一次；WebSocket 帧监听作为辅助提醒。
"""
import json
import random
import re
import time
from pathlib import Path

from stores import content_of, load_settings_and_products, log_used_card

BASE = Path(__file__).resolve().parent
LOGS_DIR = BASE / "logs"


class AutoDeliverer:
    def __init__(self, session, cfg: dict, selectors: dict, delivered, log):
        self.session = session
        self.page = session.page
        self.cfg = cfg
        self.selectors = selectors
        self.delivered = delivered
        self.log = log
        self.self_id = ""
        self._ws_unknown = 0
        self._warned_unverified = set()
        self._skip_no_product = set()
        self._browser_closed = False

    # ---------------- 启动 ----------------
    def _on_ctx_close(self, *args):
        self._browser_closed = True

    def start(self):
        self.session.ensure_login()
        self.session.open_im()
        self.self_id = self.session.self_user_id()
        self.log.info(f"本机用户ID(unb) = {self.self_id or '未知'}")
        if self.cfg.get("listen_ws_frames", True):
            self.attach_ws()
        try:
            self.session.ctx.on("close", self._on_ctx_close)
        except Exception:
            pass
        interval = int(self.cfg.get("poll_interval_seconds", 15))
        self.log.info(
            f"开始监听：每 {interval}s 轮询一次 | dry_run={self.cfg.get('dry_run', True)} | "
            "关闭浏览器窗口即停止程序，按 Ctrl+C 停止。"
        )
        while True:
            if self._browser_closed:
                self.log.info("浏览器已关闭，自动发货程序退出。")
                return
            try:
                self.poll_once()
            except Exception as e:
                if self._browser_closed or "closed" in str(e).lower():
                    self.log.info("浏览器已关闭，自动发货程序退出。")
                    return
                self.log.error(f"轮询异常: {e}")
            time.sleep(interval + random.uniform(0, 3))

    # ---------------- 选择器工具 ----------------
    def find_first(self, names):
        for sel in names:
            try:
                loc = self.page.locator(sel)
                if loc.count() > 0:
                    return loc
            except Exception:
                continue
        return None

    def get_rows(self):
        rows = self.find_first(self.selectors.get("conversation_items", []))
        if rows is None:
            self.log.warning(
                "未找到会话列表！请在浏览器里停留在「消息」页；若仍找不到，运行 "
                "python auto_delivery.py inspect 按报告修改 config.json 的 selectors.conversation_items"
            )
        return rows

    # ---------------- 轮询 ----------------
    def poll_once(self):
        rows = self.get_rows()
        if rows is None:
            return
        n = min(rows.count(), int(self.cfg.get("max_rows_per_poll", 30)))
        for i in range(n):
            try:
                row = rows.nth(i)
                text = row.inner_text(timeout=1500)
            except Exception:
                continue
            try:
                self.handle_row(text, row)
            except Exception as e:
                self.log.error(f"处理会话失败: {e}")

    def handle_row(self, text: str, row, source: str = "dom"):
        trig = self.trigger_in(text)
        if not trig:
            return
        buyer = self.first_line(text)
        if buyer in self.cfg.get("ignore_buyers", []) or buyer in self._skip_no_product:
            return
        # 会话行里没有商品标题，需要点进会话，从右侧聊天面板读商品信息
        self.log.info(f"[{source}] 命中触发词[{trig}]（买家:{buyer}），点进会话核对商品…")
        try:
            row.click()
            self.page.wait_for_timeout(1500)
        except Exception as e:
            self.log.warning(f"[{source}] 点进会话失败: {e}")
            return
        panel_text = self.read_chat_text()
        product = self.match_product(panel_text)
        if not product:
            self._skip_no_product.add(buyer)
            self.log.info(
                f"[{source}] 买家[{buyer}]的会话里未匹配到任何商品，跳过"
                "（如属误判请检查 config.json 对应商品的 match_keywords）"
            )
            return
        cards, variant = self.resolve_variant(product, panel_text)
        variant_note = f" 规格[{variant}]" if variant else ""
        key = f"{buyer}｜{product.get('name', '')}{('(' + variant + ')') if variant else ''}"[:80]
        if not self.delivered.is_new(key):
            return
        self.log.info(
            f"[{source}] 发现待发货订单：触发词[{trig}] 商品[{product.get('name')}]{variant_note} 会话[{key[:40]}]"
        )
        if self.cfg.get("verify_system_notice", False):
            # 防冒充：确认存在"系统样式"的买家已付款通知（防止买家手动打字骗卡密）
            if not self.verify_system_notice():
                if key not in self._warned_unverified:
                    self._warned_unverified.add(key)
                    self.log.warning(
                        f"[{source}] 会话[{key[:40]}]出现触发词[{trig}]，但聊天里未找到系统付款通知，已跳过。"
                        "（verify_system_notice=true；若确为系统消息仍被跳过，请运行 inspect 校准 "
                        "config.json 的 selectors.system_notice_selectors）"
                    )
                return
        self.deliver(product, key, row=None, source=source, context_text=text, buyer=buyer, cards=cards, variant=variant)

    # ---------------- 匹配 ----------------
    def trigger_in(self, text: str):
        for k in self.cfg.get("trigger_keywords", []):
            if k and k in text:
                return k
        return None

    def match_product(self, text: str):
        """在所有启用的商品里找关键词重合最多的：
        先比命中关键词个数，再比命中关键词总字数（更长更具体者优先）。"""
        best, best_score = None, None
        for p in self.cfg.get("products", []):
            if not p.get("enabled", True):
                continue
            hits = [k for k in p.get("match_keywords", []) if k and k in text]
            if not hits:
                continue
            score = (len(hits), sum(len(k) for k in hits))
            if best_score is None or score > best_score:
                best, best_score = p, score
        return best

    @staticmethod
    def first_line(text: str) -> str:
        """会话行第一行 = 买家昵称。"""
        for l in text.splitlines():
            l = l.strip()
            if l:
                return l
        return text.strip()[:20]

    def read_chat_text(self) -> str:
        """当前打开会话的右侧聊天面板文本（含商品卡片：标题/价格等）。"""
        for sel in self.selectors.get("chat_panel", []):
            try:
                loc = self.page.locator(sel)
                if loc.count() > 0:
                    return loc.first.inner_text(timeout=2000)
            except Exception:
                continue
        try:
            return self.page.locator("body").inner_text(timeout=2000)
        except Exception:
            return ""

    def resolve_variant(self, product: dict, panel_text: str):
        """多规格路由：product 配了 variant_rules 时，按"关键词在面板文字中最后出现的
        位置"认买家选的规格（订单里的"已选：白色"在标题之后，位置更靠后），
        返回 (该规格的发货内容, 规格名)；没配规则或没认出来则用商品默认发货内容。"""
        rules = product.get("variant_rules") or []
        if not rules:
            return product.setdefault("cards", ""), None
        matches = []
        for rule in rules:
            pos = -1
            for kw in rule.get("keywords", []):
                if kw:
                    pos = max(pos, panel_text.rfind(kw))
            if pos >= 0:
                matches.append((pos, rule))
        matches.sort(key=lambda x: -x[0])
        gap = int(self.cfg.get("variant_gap_chars", 4))
        # 只有"最后出现位置"明显领先（如订单里"已选：白色"在标题之后）才认定规格；
        # 多个规格挤在标题里分不清时，宁可走默认也不猜，避免发错货
        if matches and (len(matches) == 1 or matches[0][0] - matches[1][0] > gap):
            rule = matches[0][1]
            variant = rule.get("name") or "、".join(rule.get("keywords", []))
            self.log.info(f"识别到买家选择的规格：{variant}")
            return rule.setdefault("cards", ""), variant
        if matches:
            self.log.info(f"商品[{product.get('name')}]多个规格关键词位置接近、无法确定买家所选规格，使用默认发货内容")
        else:
            self.log.info(f"商品[{product.get('name')}]配置了规格规则，但未在聊天面板认出所选规格，使用默认发货内容")
        return product.setdefault("cards", ""), None

    def verify_system_notice(self) -> bool:
        """verify_system_notice=true 时使用：当前聊天里必须能按 system_notice_selectors
        找到"系统样式"的买家已付款通知，才允许发货。"""
        for sel in self.selectors.get("system_notice_selectors", []):
            try:
                if self.page.locator(sel).count() > 0:
                    return True
            except Exception:
                continue
        return False

    # ---------------- 发货 ----------------
    def deliver(self, product: dict, key: str, row=None, source: str = "dom", context_text: str = "",
                buyer: str = "", cards=None, variant: str = None):
        name = product.get("name", "?")
        if self.cfg.get("dry_run", True):
            self.delivered.mark(key, {"product": name, "card": "(dry-run)", "source": source})
            self.log.info(
                f"[dry_run] 命中发货条件：商品={name} 会话={key[:40]}（不发送、不消耗卡密；"
                "确认流程无误后，把 config.json 里 dry_run 改为 false 即正式发货）"
            )
            return

        if cards is None:
            cards = product.get("cards", "")
        content = content_of(cards)  # 发货内容 = 框里的全部内容，整段发送
        if not content:
            spec = f"（规格[{variant}]）" if variant else ""
            self.log.error(f"❗ 商品[{name}]{spec}发货内容为空，请在商品管理页填写后重试！")
            if buyer:
                self._skip_no_product.add(buyer)  # 本轮运行内不再反复尝试
            return
        preview = " / ".join(content.split("\n"))[:30]
        self.log.info(f"发货中：商品={name} 内容[{preview}…] 共{len(content)}字 来源={source}")

        ok = False
        try:
            if row is not None:
                row.click()
                self.page.wait_for_timeout(1500)
            reply = product.get("reply_text", "") or "{card}"
            reply = reply.replace("\\n", "\n")   # 话术里手写的 \n 也当成换行
            if "{card}" in reply:
                text = reply.replace("{card}", content)
            else:
                text = f"{reply}\n{content}" if reply.strip() else content
            ok = self.send_message(text)
        finally:
            if ok:
                # 内容不消耗、不删除：同一商品每次发货都发同一整段内容
                log_used_card(name, content)
                self.delivered.mark(key, {"product": name, "card": content[:200], "source": source})
                self.log.info(f"✅ 发货成功：商品={name} 会话={key[:40]}（内容已保留，可继续使用）")
            else:
                self.log.error("❌ 发送失败，稍后会自动重试")

    @staticmethod
    def _squash(s: str) -> str:
        """去掉所有空白，用来核对"内容是否都进到输入框里了"。"""
        return re.sub(r"\s+", "", s or "")

    def _input_text(self, inp) -> str:
        try:
            return inp.inner_text(timeout=1500) or ""
        except Exception:
            try:
                return inp.input_value(timeout=1000) or ""
            except Exception:
                return ""

    def _clear_input(self, inp):
        try:
            inp.click(timeout=2000)
        except Exception:
            pass
        try:
            self.page.keyboard.press("Control+A")
            self.page.keyboard.press("Delete")
        except Exception:
            pass

    def _type_multiline(self, inp, text: str):
        """逐行输入：行间用 Shift+Enter 换行（不会误触发送）。"""
        try:
            inp.click()
        except Exception:
            pass
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if i:
                self.page.keyboard.press("Shift+Enter")
            if line:
                self.page.keyboard.type(line, delay=12)

    def send_message(self, text: str) -> bool:
        delay = self.cfg.get("send_delay_seconds", [2, 6])
        try:
            time.sleep(random.uniform(float(delay[0]), float(delay[1])))
        except Exception:
            time.sleep(3)
        inp = self.find_first(self.selectors.get("chat_input", []))
        if inp is None:
            self.log.error("找不到聊天输入框，请运行 inspect 校准 selectors.json 的 chat_input")
            return False
        want = self._squash(text)
        filled = False
        # 先试一次性填入（最快）；填进去的内容不完整（多行被吞）时，改用逐行输入
        try:
            self._clear_input(inp)
            inp.fill(text)
            filled = self._squash(self._input_text(inp)) == want
        except Exception:
            filled = False
        if not filled:
            try:
                self._clear_input(inp)
                self._type_multiline(inp, text)
                filled = self._squash(self._input_text(inp)) == want
            except Exception as e:
                self.log.error(f"输入消息失败: {e}")
                return False
        if not filled:
            got = self._input_text(inp)
            self.log.warning(
                f"输入框内容与预期不完全一致（预期{len(want)}字，实际{len(self._squash(got))}字），仍尝试发送"
            )
        sent = False
        for t in self.selectors.get("send_button_text", ["发送"]):
            try:
                btn = self.page.get_by_role("button", name=t)
                if btn.count() > 0:
                    btn.first.click()
                    sent = True
                    break
            except Exception:
                continue
        if not sent:
            try:
                self.page.keyboard.press("Enter")
                sent = True
            except Exception:
                pass
        self.page.wait_for_timeout(800)
        # 发送后输入框若还有残留（发送没成功），不影响下一次，下次会先清空
        return sent

    def find_row_by_text(self, text: str):
        rows = self.get_rows()
        if rows is None:
            return None
        probe = re.sub(r"\s+", "", text)[:10]
        if not probe:
            return None
        n = min(rows.count(), int(self.cfg.get("max_rows_per_poll", 30)))
        for i in range(n):
            try:
                t = re.sub(r"\s+", "", rows.nth(i).inner_text(timeout=1000))
                if probe in t:
                    return rows.nth(i)
            except Exception:
                continue
        return None

    # ---------------- WebSocket 帧监听（辅助） ----------------
    def attach_ws(self):
        def on_ws(ws):
            try:
                ws.on("framereceived", self.on_frame)
            except Exception:
                pass
        self.page.on("websocket", on_ws)
        self.log.info("已附加 WebSocket 帧监听（未知帧会抽样记录到 logs/ws_frames.log，便于后续扩展解析）")

    def on_frame(self, payload):
        if not isinstance(payload, str):
            return
        try:
            obj = json.loads(payload)
        except Exception:
            return
        try:
            events = self.extract_chat_events(obj)
        except Exception:
            events = []
        if not events and self._ws_unknown < 80:
            self._ws_unknown += 1
            LOGS_DIR.mkdir(exist_ok=True)
            with (LOGS_DIR / "ws_frames.log").open("a", encoding="utf-8") as f:
                f.write(payload[:2000] + "\n----\n")
        for ev in events:
            try:
                self.handle_ws_event(ev)
            except Exception as e:
                self.log.debug(f"ws 事件处理异常: {e}")

    @staticmethod
    def extract_chat_events(obj, depth=0, out=None):
        """在 ws 帧的 JSON 里递归找“聊天消息”形状的节点（闲鱼协议常变，只做启发式解析）。"""
        if out is None:
            out = []
        if depth > 12:
            return out
        if isinstance(obj, dict):
            c = obj.get("content")
            if isinstance(c, (str, dict)):
                text = ""
                if isinstance(c, dict):
                    text = str(c.get("text") or "")
                else:
                    s = c.strip()
                    try:
                        cj = json.loads(s)
                        text = str(cj.get("text")) if isinstance(cj, dict) and cj.get("text") else s
                    except Exception:
                        text = s
                if text:
                    ev = {"text": text, "sender": "", "chat": ""}
                    for k in ("senderUserId", "fromUser", "userId"):
                        if k in obj:
                            ev["sender"] = str(obj.get(k))
                            break
                    for k in ("cid", "chatId", "sessionId", "sid"):
                        if k in obj:
                            ev["chat"] = str(obj.get(k))
                            break
                    out.append(ev)
            for v in obj.values():
                AutoDeliverer.extract_chat_events(v, depth + 1, out)
        elif isinstance(obj, list):
            for v in obj:
                AutoDeliverer.extract_chat_events(v, depth + 1, out)
        return out

    def handle_ws_event(self, ev: dict):
        text = (ev.get("text") or "").strip()
        if not text or len(text) > 300:
            return
        if self.self_id and str(ev.get("sender", "")) == self.self_id:
            return  # 忽略自己发的消息
        if not self.trigger_in(text):
            return
        row = self.find_row_by_text(text)
        if row is None:
            self.log.warning(f"[ws] 检测到买家消息但未定位到会话（DOM 轮询会兜底处理）：{text[:40]!r}")
            return
        row_text = row.inner_text(timeout=1500)
        self.handle_row(row_text, row, source="ws")
