'use strict';

/* 多账号切换器 —— 后台逻辑：Cookie 快照、清除、恢复与账号数据管理 */

const STORE_KEY = 'accountsSwitcher';

// 常见公共后缀：避免把 co.uk / com.cn 之类当作可登录的域名层级
const PUBLIC_SUFFIXES = new Set([
  'co.uk', 'org.uk', 'ac.uk', 'gov.uk', 'com.cn', 'net.cn', 'org.cn', 'gov.cn', 'edu.cn',
  'com.au', 'net.au', 'org.au', 'co.jp', 'ne.jp', 'or.jp', 'co.kr', 'ne.kr', 'or.kr',
  'com.br', 'com.tw', 'com.hk', 'com.sg', 'com.mx', 'com.ar', 'co.nz', 'co.in', 'com.tr',
  'com.pl', 'com.ua', 'co.za', 'com.vn', 'com.my', 'com.ph', 'com.pk', 'com.bd'
]);

function defaultData() {
  return { sites: {}, settings: {} };
}

function isValidHost(hostname) {
  if (!hostname) return false;
  const h = hostname.toLowerCase();
  return !/^(chrome|edge|about|file|chrome-extension|moz-extension):?$/i.test(h) &&
    !h.startsWith('chrome://') && !h.startsWith('edge://') && h !== 'newtab';
}

/** 归组键：同一网站（主域 eTLD+1）下所有子域、所有页面共用一份账号列表 */
function siteKeyFor(hostname) {
  const host = (hostname || '').toLowerCase().replace(/^\./, '');
  if (!host) return host;
  // IP、localhost、单段主机名各自独立
  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(host) || !host.includes('.')) return host;
  const parts = host.split('.').filter(Boolean);
  const lastTwo = parts.slice(-2).join('.');
  if (PUBLIC_SUFFIXES.has(lastTwo) && parts.length >= 3) return parts.slice(-3).join('.');
  return lastTwo;
}

/** 兼容旧版：把按精确主机名保存的账号合并到主域归组键下 */
async function migrateSiteKeys(data) {
  let changed = false;
  for (const key of Object.keys(data.sites)) {
    const sk = siteKeyFor(key);
    if (sk === key) continue;
    const from = data.sites[key];
    if (!data.sites[sk]) {
      data.sites[sk] = from;
    } else {
      const to = data.sites[sk];
      if (!Array.isArray(to.accounts)) to.accounts = [];
      const ids = new Set(to.accounts.map(a => a.id));
      for (const a of (from.accounts || [])) if (!ids.has(a.id)) to.accounts.push(a);
      if (!to.currentId && from.currentId) to.currentId = from.currentId;
    }
    delete data.sites[key];
    changed = true;
  }
  if (changed) await saveData(data);
}

/** 由 hostname 推出需要处理的域名层级，例如 a.www.example.com -> [a.www.example.com, www.example.com, example.com] */
function domainsFor(hostname) {
  const host = (hostname || '').toLowerCase().replace(/^\./, '');
  const parts = host.split('.').filter(Boolean);
  if (parts.length <= 1) return [host]; // localhost / IP
  const out = [];
  const lastTwo = parts.slice(-2).join('.');
  for (let i = 0; i < parts.length; i++) {
    const d = parts.slice(i).join('.');
    if (d === lastTwo && PUBLIC_SUFFIXES.has(lastTwo)) break;
    out.push(d);
    if (i === 0 && parts.length === 2) break;
  }
  return out;
}

function uniqueCookies(list) {
  const seen = new Set();
  const out = [];
  for (const c of list) {
    const key = `${c.domain}|${c.name}|${c.path}`;
    if (!seen.has(key)) { seen.add(key); out.push(c); }
  }
  return out;
}

/**
 * 判断某个 Cookie 是否属于当前网站：
 * 只有「同一主域及其子域」才算，其他网站一律排除。
 * 例如在 www.bilibili.com 上，只接受 bilibili.com / *.bilibili.com。
 */
function belongsToSite(cookieDomain, siteKey) {
  const host = (cookieDomain || '').replace(/^\./, '').toLowerCase();
  if (!host || !siteKey) return false;
  if (host === siteKey) return true;
  if (siteKeyFor(host) === siteKey) return true;      // 同主域的其他子域
  return host.endsWith('.' + siteKey);                // 兜底：更深的子域
}

/** 汇总 Cookie 覆盖到的域名，用于界面提示「本次只保存了哪些站点」 */
function domainsOf(cookies) {
  const set = new Set();
  for (const c of cookies || []) {
    const d = (c.domain || '').replace(/^\./, '').toLowerCase();
    if (d) set.add(d);
  }
  return Array.from(set).sort();
}

/** 抓取当前网站的全部 Cookie 快照（严格限定在同一主域内） */
async function captureCookies(hostname) {
  const siteKey = siteKeyFor(hostname);
  const domains = domainsFor(hostname);
  const found = [];
  for (const d of domains) {
    for (const variant of [d, '.' + d]) {
      try {
        const list = await chrome.cookies.getAll({ domain: variant });
        found.push(...list);
      } catch (_) { /* 忽略单个域名查询失败 */ }
    }
  }
  const now = Date.now() / 1000;
  return uniqueCookies(found)
    // 硬隔离：不属于当前网站的 Cookie 一律丢弃，绝不混入其他站点
    .filter(c => belongsToSite(c.domain, siteKey))
    // 丢弃已过期的 Cookie，避免恢复时报错
    .filter(c => typeof c.expirationDate !== 'number' || c.expirationDate > now)
    .map(c => ({
      name: c.name,
      value: c.value,
      domain: c.domain,
      path: c.path,
      secure: !!c.secure,
      httpOnly: !!c.httpOnly,
      sameSite: c.sameSite || 'lax',
      expirationDate: c.expirationDate,
      partitionKey: c.partitionKey,
      hostOnly: c.hostOnly
    }));
}

function cookieUrl(cookie) {
  const host = (cookie.domain || '').replace(/^\./, '');
  const scheme = cookie.secure ? 'https:' : 'http:';
  return `${scheme}//${host}${cookie.path || '/'}`;
}

/* ---------------- 网站设置（localStorage / sessionStorage） ---------------- */

/** 读取标签页当前地址 */
async function getTabUrl(tabId) {
  try {
    const tab = await chrome.tabs.get(tabId);
    return (tab && tab.url) || '';
  } catch (_) { return ''; }
}

/**
 * 抓取当前标签页的网站设置（localStorage / sessionStorage）。
 * 主题、布局偏好这类纯前端设置通常只存在这里。
 */
async function captureWebStorage(tabId) {
  if (tabId == null) return null;
  const url = await getTabUrl(tabId);
  if (!/^https?:/i.test(url)) return null;
  let origin = '';
  try { origin = new URL(url).origin; } catch (_) { return null; }
  try {
    const res = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => {
        const dump = store => {
          const out = {};
          for (let i = 0; i < store.length; i++) {
            const k = store.key(i);
            out[k] = store.getItem(k);
          }
          return out;
        };
        try { return { local: dump(localStorage), session: dump(sessionStorage) }; } catch (_) { return null; }
      }
    });
    const data = res && res[0] && res[0].result;
    if (!data) return null;
    return { origin, local: data.local || {}, session: data.session || {} };
  } catch (_) { return null; }
}

/** 统计设置项数量，用于界面展示 */
function storageKeyCount(snapshot) {
  if (!snapshot) return 0;
  return Object.keys(snapshot.local || {}).length + Object.keys(snapshot.session || {}).length;
}

/* ---------------- 昵称 / 头像（保存账号时自动抓取） ---------------- */

/** 把远程图片压成小尺寸 data URL，避免头像链接过期或需要登录 */
async function imageToDataUrl(url) {
  if (!url) return '';
  // 页面本身就是内联图片（小图标、canvas 转出的头像），直接沿用
  if (/^data:image\//i.test(url)) return url.length <= 120000 ? url : '';
  if (!/^https?:/i.test(url)) return '';
  try {
    const res = await fetch(url, { credentials: 'include' });
    if (!res || !res.ok) return '';
    const blob = await res.blob();
    if (!blob || !/^image\//.test(blob.type || '')) return '';
    if (blob.size > 4 * 1024 * 1024) return '';
    const size = 96;
    const bmp = await createImageBitmap(blob);
    const scale = Math.min(1, size / Math.max(bmp.width || 1, bmp.height || 1));
    const w = Math.max(1, Math.round((bmp.width || size) * scale));
    const h = Math.max(1, Math.round((bmp.height || size) * scale));
    const canvas = new OffscreenCanvas(w, h);
    const c = canvas.getContext('2d');
    c.drawImage(bmp, 0, 0, w, h);
    // 用 webp 保留透明背景，否则透明头像转 JPEG 会变成黑底
    const type = 'image/webp';
    const out = await canvas.convertToBlob({ type, quality: 0.86 });
    const buf = await out.arrayBuffer();
    const bytes = new Uint8Array(buf);
    let bin = '';
    for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    return 'data:' + type + ';base64,' + btoa(bin);
  } catch (_) {
    return '';
  }
}

/** 部分站点有公开的用户信息接口，优先用它，准确率最高 */
async function captureProfileByApi(siteKey) {
  if (!/^(.*\.)?bilibili\.com$/.test(siteKey)) return null;
  try {
    const res = await fetch('https://api.bilibili.com/x/web-interface/nav', { credentials: 'include' });
    if (!res || !res.ok) return null;
    const json = await res.json();
    const d = json && json.code === 0 && json.data;
    if (!d || !d.isLogin) return null;
    return { name: (d.uname || '').trim(), avatarUrl: d.face || '' };
  } catch (_) {
    return null;
  }
}

/** 通用兜底：从页面 DOM 里找头像和昵称（任意网站，靠结构启发式判断） */
async function captureProfileByDom(tabId) {
  if (tabId == null) return null;
  try {
    const res = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => {
        const out = { name: '', avatarUrl: '', altName: '' };
        const abs = u => {
          try { return new URL(String(u || '').trim(), location.href).href; } catch (_) { return ''; }
        };
        const attr = (el, k) => {
          try { return String((el && el.getAttribute && el.getAttribute(k)) || ''); } catch (_) { return ''; }
        };
        const clsOf = el => {
          let s = '';
          try { s += String(el.className || ''); } catch (_) {}
          try { if (el.id) s += ' ' + el.id; } catch (_) {}
          return s;
        };
        const altOf = el => {
          let v = attr(el, 'alt');
          if (!v) { try { v = String(el.alt || ''); } catch (_) {} }
          return v.trim();
        };
        // 判断「这个元素是否跟账号相关」的全部文本信号
        const signals = el => {
          let s = clsOf(el);
          try { if (el.parentElement) s += ' ' + clsOf(el.parentElement); } catch (_) {}
          return s + ' ' + altOf(el) + ' ' + attr(el, 'title') + ' ' +
            attr(el, 'aria-label') + ' ' + attr(el, 'data-testid');
        };
        // 懒加载：真实地址常在 data-* 或 srcset 里，img.src 只是占位图
        const realSrc = img => {
          for (const a of ['data-src', 'data-original', 'data-lazy-src', 'data-avatar', 'data-url', 'data-thumb']) {
            const v = attr(img, a);
            if (v) { const u = abs(v); if (u) return u; }
          }
          const ss = attr(img, 'srcset');
          if (ss) {
            const first = ss.split(',')[0].trim().split(/\s+/)[0];
            if (first) { const u = abs(first); if (u) return u; }
          }
          let cur = '';
          try { cur = img.currentSrc || img.src || ''; } catch (_) {}
          return abs(cur);
        };
        const isPlaceholder = u => !u || /^data:image\/(gif|svg)/i.test(u) ||
          /blank|placeholder|default[-_]?avatar|avatar[-_]?default|noavatar|spacer|grey\.gif|transparent|loading\.(gif|png)|pixel\.(gif|png)/i.test(u);

        const vh = window.innerHeight || 900;
        const vw = window.innerWidth || 1280;
        const inTop = rect => !rect || !rect.height || rect.top < vh * 0.78;
        // 站内用户主页链接：头像或昵称常常就包在里面
        const userHref = h => /(\/u\/|\/user|\/profile|\/member|\/space|\/people|\/@[^/]+)/i.test(String(h || ''));
        const AVATAR_SIG = /avatar|head|face|portrait|userpic|touxiang|profile[-_]?(pic|img|photo)/i;
        // 站点 logo / 图标 / 广告图，绝不能当头像
        const NOISE_SIG = /logo|brand|favicon|sprite|banner|cover|qrcode|qr[-_]?code|badge|verified|vip[-_]?icon|emoji|sticker/i;

        /* ---------- 1. 找最像头像的元素 ---------- */
        let bestUrl = '';
        let bestEl = null;
        let bestScore = 0;
        const consider = (url, el, score) => {
          if (!url || isPlaceholder(url)) return;
          if (score > bestScore) { bestScore = score; bestUrl = url; bestEl = el; }
        };
        // 往上几层找「用户主页链接 / header / 账户按钮」作为辅助证据
        const contextScore = el => {
          let s = 0;
          let p = null;
          try { p = el.parentElement; } catch (_) {}
          for (let d = 0; d < 4 && p; d++) {
            const tag = String(p.tagName || '').toUpperCase();
            if (tag === 'A' && userHref(attr(p, 'href'))) { s += 4; break; }
            if (tag === 'HEADER' || tag === 'NAV') { s += 2; break; }
            if (tag === 'BUTTON') { s += 1; break; }
            try { p = p.parentElement; } catch (_) { break; }
          }
          return s;
        };

        try {
          for (const img of Array.from(document.images || [])) {
            let rect = null;
            try { rect = img.getBoundingClientRect(); } catch (_) {}
            const rw = rect ? Math.round(rect.width) || 0 : 0;
            const rh = rect ? Math.round(rect.height) || 0 : 0;
            const w = Math.max(img.naturalWidth || 0, rw);
            const h = Math.max(img.naturalHeight || 0, rh);
            if (w < 22 || h < 22) continue;
            if (w > 480 || h > 480) continue;            // 大图是封面/横幅
            if (!inTop(rect)) continue;                  // 头像基本都在页面上部
            if (attr(img, 'aria-hidden') === 'true') continue;   // 装饰图
            const sig = signals(img);
            const related = AVATAR_SIG.test(sig) || /user|member|account|nick|个人|我的/i.test(sig);
            let score = 0;
            if (AVATAR_SIG.test(sig)) score += 6;
            if (/头像|avatar|用户|profile/i.test(altOf(img))) score += 3;
            const ar = Math.abs(w - h) / Math.max(w, h, 1);
            if (ar <= 0.12) score += 3; else if (ar <= 0.3) score += 1;
            if (w >= 28 && w <= 160) score += 2;
            if (rect) {
              if (rect.top < 120) score += 3;
              if (rect.left < vw * 0.45) score += 1;
            }
            score += contextScore(img);
            if (!related) score -= 4;                    // 完全不沾账号的图，降权
            if (NOISE_SIG.test(sig)) score -= 8;         // logo / banner 之类直接压掉
            consider(realSrc(img), img, score);
          }
        } catch (_) {}

        // 有些站点的头像是 CSS 背景图
        try {
          const nodes = document.querySelectorAll(
            'header *, nav *, [class*="user" i], [class*="avatar" i], [class*="profile" i], [class*="member" i]');
          let guard = 0;
          for (const el of Array.from(nodes)) {
            if (++guard > 500) break;
            let bg = '';
            try { bg = (window.getComputedStyle(el).backgroundImage) || ''; } catch (_) {}
            const m = /url\(["']?([^"')]+)["']?\)/i.exec(bg);
            if (!m) continue;
            let rect = null;
            try { rect = el.getBoundingClientRect(); } catch (_) {}
            const w = rect ? Math.round(rect.width) || 0 : 0;
            const h = rect ? Math.round(rect.height) || 0 : 0;
            if (w < 22 || h < 22) continue;
            if (Math.abs(w - h) > Math.max(w, h) * 0.35) continue;
            if (!inTop(rect)) continue;
            const sig = signals(el);
            let score = 2;
            if (AVATAR_SIG.test(sig)) score += 6;
            if (w >= 28 && w <= 160) score += 2;
            score += contextScore(el);
            if (NOISE_SIG.test(sig)) score -= 8;
            consider(abs(m[1]), el, score);
          }
        } catch (_) {}
        // 分数太低说明只是「长得像方形的小图」，宁可不存也不要存错（比如站点 logo）
        if (bestScore < 6) { bestUrl = ''; bestEl = null; }

        /* ---------- 2. 找昵称 ---------- */
        // 纯功能文案，绝不可能是昵称
        const BAD = /^(登录|登录\/注册|注册|立即登录|退出|退出登录|注销|切换账号|设置|个人中心|我的主页|我的|会员中心|会员|消息|通知|动态|收藏|历史|投稿|关注|粉丝|更多|编辑|账号|帐号|首页|搜索|下载|上传|客服|帮助|反馈|菜单|关闭|取消|确定|保存|删除|新建|创建|复制|分享|开始使用|免费注册|立即注册|登录后查看)$/i;
        const textOf = el => {
          let t = '';
          try { t = (el.innerText != null ? el.innerText : el.textContent) || ''; } catch (_) { t = ''; }
          return String(t).replace(/\s+/g, ' ').trim();
        };
        const isName = t => {
          if (!t || t.length > 24) return false;
          if (BAD.test(t)) return false;
          if (/^(log ?in|sign ?in|sign ?up|sign ?out|login|logout|register|password)$/i.test(t)) return false;
          if (/^https?:/i.test(t) || /^www\./i.test(t)) return false;
          if (/^\d{1,2}$/.test(t)) return false;
          if (/\s\d{1,3}$/.test(t)) return false;        // 「关注 12」这类计数
          // 至少要有可见的文字字符（中文/英文/日韩/拉丁扩展），排除纯符号
          if (!/[0-9A-Za-z\u00C0-\u024F\u3040-\u30FF\u3400-\u9FFF\uAC00-\uD7AF]/.test(t)) return false;
          if (/头像|avatar|photo|picture|image|icon|logo|二维码|qr ?code/i.test(t)) return false;
          return true;
        };
        // 头像旁边最近的文本：最常见的结构就是「头像 + 昵称」并排
        const neighborName = el => {
          let node = el;
          for (let depth = 0; depth < 4 && node; depth++) {
            let parent = null;
            try { parent = node.parentElement; } catch (_) {}
            if (!parent) break;
            let kids = [];
            try { kids = Array.from(parent.children || []); } catch (_) {}
            // 先挑 class 明显是昵称的兄弟
            for (const k of kids) {
              if (k === node) continue;
              if (!/nick|uname|user[-_]?name|display[-_]?name|screen[-_]?name|account[-_]?name|member[-_]?name|handle/i.test(clsOf(k))) continue;
              const t = textOf(k);
              if (isName(t)) return t;
            }
            // 再退一步：兄弟里的叶子文本
            for (const k of kids) {
              if (k === node) continue;
              const tag = String(k.tagName || '').toUpperCase();
              if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'SVG' || tag === 'IMG') continue;
              let childCount = 0;
              try { childCount = (k.children || []).length; } catch (_) {}
              if (childCount > 1) continue;
              const t = textOf(k);
              if (isName(t)) return t;
            }
            node = parent;
          }
          return '';
        };
        // 全局按关键词找，分组递进：越靠前的组越可信
        const scanName = () => {
          const GROUPS = [
            ['[class*="nick" i]', '[id*="nick" i]', '[data-nickname]', '[data-nick]', '[class*="uname" i]'],
            ['[class*="username" i]', '[class*="user-name" i]', '[class*="userName"]', '[class*="display-name" i]',
             '[class*="screen-name" i]', '[class*="account-name" i]', '[class*="profile-name" i]',
             '[class*="member-name" i]', '[class*="userNick" i]'],
            ['[class*="handle" i]', '[class*="profile" i] [class*="name" i]', '[class*="user" i] [class*="name" i]',
             '[class*="name" i]', '[id*="name" i]', '[data-testid*="user" i]', '[rel*="nick" i]'],
            ['[aria-label*="用户" i]', '[title*="用户" i]', '[aria-label*="profile" i]', '[aria-label*="account" i]']
          ];
          for (const g of GROUPS) {
            let best = '';
            let bestS = 0;
            for (const sel of g) {
              let list = [];
              try { list = Array.from(document.querySelectorAll(sel)).slice(0, 12); } catch (_) {}
              for (const n of list) {
                const tag = String(n.tagName || '').toUpperCase();
                if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'BUTTON' ||
                    tag === 'SELECT' || tag === 'OPTION') continue;
                const t = textOf(n);
                if (!isName(t)) continue;
                let childCount = 0;
                try { childCount = (n.children || []).length; } catch (_) {}
                if (childCount > 2) continue;
                let rect = null;
                try { rect = n.getBoundingClientRect(); } catch (_) {}
                if (rect && rect.height && rect.top > vh * 0.5) continue;
                let s = 1;
                if (rect && rect.top < 160) s += 2;
                if (/nick|uname|user[-_]?name|display[-_]?name|screen[-_]?name|account[-_]?name|member[-_]?name/i.test(clsOf(n))) s += 2;
                if (s > bestS) { bestS = s; best = t; }
              }
            }
            if (best) return best;
          }
          return '';
        };
        // 指向用户主页的链接，文字通常就是昵称
        const linkName = () => {
          try {
            const links = Array.from(document.querySelectorAll('a[href]')).slice(0, 400);
            for (const a of links) {
              const href = attr(a, 'href');
              if (!/(\/u\/|\/user|\/profile|\/member|\/space|\/people|\/@)/i.test(href)) continue;
              let rect = null;
              try { rect = a.getBoundingClientRect(); } catch (_) {}
              if (rect && rect.height && rect.top > vh * 0.4) continue;
              let childCount = 0;
              try { childCount = (a.children || []).length; } catch (_) {}
              if (childCount > 2) continue;
              const t = textOf(a);
              if (isName(t)) return t;
            }
          } catch (_) {}
          return '';
        };

        if (bestUrl) {
          out.avatarUrl = bestUrl;
          const alt = altOf(bestEl) || attr(bestEl, 'title');
          if (alt && alt.length <= 24 && !/头像|avatar|photo|picture|image|icon|logo|用户|profile|user/i.test(alt)) {
            out.altName = alt;
          }
        }
        let name = '';
        if (bestEl) name = neighborName(bestEl);
        if (!name) name = out.altName;
        if (!name) name = scanName();
        if (!name) name = linkName();
        out.name = name;
        return out;
      }
    });
    return (res && res[0] && res[0].result) || null;
  } catch (_) {
    return null;
  }
}

/** 综合抓取：接口优先，DOM 补缺，头像转成 data URL */
async function captureProfile(hostname, tabId) {
  const siteKey = siteKeyFor(hostname);
  const api = await captureProfileByApi(siteKey);
  let name = (api && api.name) || '';
  let avatarUrl = (api && api.avatarUrl) || '';
  if (!name || !avatarUrl) {
    let dom = await captureProfileByDom(tabId);
    if (dom) {
      if (!name) name = dom.name || dom.altName || '';
      if (!avatarUrl) avatarUrl = dom.avatarUrl || '';
    }
    // 单页应用刚渲染完时头部可能还没出来，稍等再抓一次
    if (!avatarUrl || !name) {
      await new Promise(r => setTimeout(r, 300));
      dom = await captureProfileByDom(tabId);
      if (dom) {
        if (!name) name = dom.name || dom.altName || '';
        if (!avatarUrl) avatarUrl = dom.avatarUrl || '';
      }
    }
  }
  name = String(name || '').replace(/\s+/g, ' ').trim().slice(0, 24);
  const avatar = avatarUrl ? (await imageToDataUrl(avatarUrl)) || avatarUrl : '';
  return { name, avatar };
}

/**
 * 把设置写回当前标签页。
 * localStorage 按源隔离，所以只有当前页面的源与快照一致时才能写。
 */
async function restoreWebStorage(tabId, snapshot) {
  if (tabId == null || !snapshot || !snapshot.origin) return { ok: false, reason: 'no-data' };
  const url = await getTabUrl(tabId);
  let origin = '';
  try { origin = new URL(url).origin; } catch (_) { /* ignore */ }
  if (origin !== snapshot.origin) return { ok: false, reason: 'origin-mismatch' };
  try {
    const res = await chrome.scripting.executeScript({
      target: { tabId },
      func: snap => {
        const apply = (store, data) => {
          const keys = [];
          for (let i = 0; i < store.length; i++) keys.push(store.key(i));
          keys.forEach(k => store.removeItem(k));
          Object.keys(data || {}).forEach(k => store.setItem(k, data[k]));
        };
        try {
          apply(localStorage, snap.local);
          apply(sessionStorage, snap.session);
          return 1;
        } catch (_) { return 0; }
      },
      args: [snapshot]
    });
    return (res && res[0] && res[0].result) ? { ok: true } : { ok: false, reason: 'inject-failed' };
  } catch (_) {
    return { ok: false, reason: 'inject-failed' };
  }
}

/**
 * 恢复设置并让页面生效。
 * 只在当前页面应用，不跳转到其他网站/页面：
 * 同源就写入并刷新；不同源则跳过（返回 skipped），保持你当前所在的页面不动。
 */
async function applyWebStorage(tabId, snapshot) {
  if (tabId == null || !snapshot || !snapshot.origin) return 'none';
  const res = await restoreWebStorage(tabId, snapshot);
  if (res.ok) {
    await reloadCurrentTab(tabId);
    return 'restored';
  }
  if (res.reason === 'origin-mismatch') return 'skipped';
  return 'failed';
}

/** 清空当前标签页所在源的 localStorage / sessionStorage，只影响这一个源 */
async function clearWebStorage(tabId) {
  if (tabId == null) return { ok: false };
  const url = await getTabUrl(tabId);
  if (!/^https?:/i.test(url)) return { ok: false };
  let origin = '';
  try { origin = new URL(url).origin; } catch (_) { return { ok: false }; }
  try {
    const res = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => {
        try {
          localStorage.clear();
          sessionStorage.clear();
          return 1;
        } catch (_) { return 0; }
      }
    });
    return { ok: !!(res && res[0] && res[0].result), origin };
  } catch (_) {
    return { ok: false, origin };
  }
}

/** 删除当前网站（同一主域及子域）的 Cookie，绝不触碰其他网站 */
async function clearCookies(hostname) {  const siteKey = siteKeyFor(hostname);
  const domains = domainsFor(hostname);
  for (const d of domains) {
    for (const variant of [d, '.' + d]) {
      let list = [];
      try { list = await chrome.cookies.getAll({ domain: variant }); } catch (_) { continue; }
      for (const c of list) {
        if (!belongsToSite(c.domain, siteKey)) continue;
        const host = (c.domain || '').replace(/^\./, '');
        for (const scheme of ['https:', 'http:']) {
          try {
            await chrome.cookies.remove({ url: `${scheme}//${host}${c.path || '/'}`, name: c.name });
            break;
          } catch (_) { /* 换协议重试 */ }
        }
      }
    }
  }
}

/** 将快照写回浏览器 */
async function restoreCookies(cookies) {
  let ok = 0;
  const failed = [];
  for (const c of cookies || []) {
    const details = {
      url: cookieUrl(c),
      name: c.name,
      value: c.value,
      path: c.path || '/'
    };
    // hostOnly Cookie 不能显式带 domain，否则会被写成域 Cookie，站点可能识别不到
    if (c.domain && !c.hostOnly) details.domain = c.domain;
    if (typeof c.secure === 'boolean') details.secure = c.secure;
    if (typeof c.httpOnly === 'boolean') details.httpOnly = c.httpOnly;
    const sameSite = c.sameSite;
    // no_restriction 必须搭配 secure，否则 API 会拒绝
    if (['lax', 'strict'].includes(sameSite) || (sameSite === 'no_restriction' && c.secure)) {
      details.sameSite = sameSite;
    }
    if (typeof c.expirationDate === 'number' && c.expirationDate > Date.now() / 1000) {
      details.expirationDate = c.expirationDate;
    }
    if (c.partitionKey) details.partitionKey = c.partitionKey;
    try {
      await chrome.cookies.set(details);
      ok++;
    } catch (_) {
      try {
        delete details.partitionKey;
        delete details.sameSite;
        await chrome.cookies.set(details);
        ok++;
      } catch (__) { failed.push(c.name); }
    }
  }
  return { ok, failed };
}

async function loadData() {
  const result = await chrome.storage.local.get(STORE_KEY);
  const data = result[STORE_KEY];
  if (!data || typeof data !== 'object') return defaultData();
  const normalized = {
    sites: data.sites && typeof data.sites === 'object' ? data.sites : {},
    settings: Object.assign(defaultData().settings, data.settings || {})
  };
  await migrateSiteKeys(normalized);
  return normalized;
}

async function saveData(data) {
  await chrome.storage.local.set({ [STORE_KEY]: data });
}

function getSite(data, siteKey) {
  if (!data.sites[siteKey]) {
    data.sites[siteKey] = { currentId: null, accounts: [] };
  }
  if (!Array.isArray(data.sites[siteKey].accounts)) data.sites[siteKey].accounts = [];
  return data.sites[siteKey];
}

function newId() {
  return 'acc_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8);
}

/** 只刷新发起操作的那个标签页，不动其他标签 */
async function reloadCurrentTab(tabId) {
  if (tabId == null) return;
  try {
    await chrome.tabs.reload(tabId);
  } catch (_) { /* 标签已关闭或无权限时忽略 */ }
}

async function handleMessage(msg) {
  const { type, hostname } = msg || {};
  const siteKey = siteKeyFor(hostname);
  const data = await loadData();

  switch (type) {
    case 'getSiteData': {
      if (!isValidHost(hostname)) return { ok: false, error: '当前页面不支持账号切换' };
      const site = data.sites[siteKey] || { currentId: null, accounts: [] };
      return {
        ok: true,
        hostname,
        siteKey,
        scope: siteKey,
        currentId: site.currentId || null,
        accounts: (site.accounts || []).map(a => ({
          id: a.id, name: a.name, note: a.note || '',
          avatar: a.avatar || '',
          updatedAt: a.updatedAt, cookieCount: (a.cookies || []).length,
          storageCount: storageKeyCount(a.webStorage),
          storageOrigin: (a.webStorage && a.webStorage.origin) || '',
          domains: domainsOf(a.cookies)
        })),
        settings: data.settings
      };
    }

    case 'addAccount': {
      const site = getSite(data, siteKey);
      const cookies = await captureCookies(hostname);
      if (cookies.length === 0) {
        return { ok: false, error: '未检测到 Cookie，请先在该网站登录账号再保存' };
      }
      const webStorage = await captureWebStorage(msg.tabId);
      const profile = await captureProfile(hostname, msg.tabId);
      const account = {
        id: newId(),
        name: msg.name || profile.name || `账号 ${site.accounts.length + 1}`,
        avatar: profile.avatar || '',
        note: msg.note || '',
        updatedAt: Date.now(),
        cookies,
        webStorage
      };
      site.accounts.push(account);
      site.currentId = account.id;
      await saveData(data);
      return {
        ok: true,
        accountId: account.id,
        cookieCount: cookies.length,
        storageCount: storageKeyCount(webStorage),
        domains: domainsOf(cookies)
      };
    }

    case 'overwriteAccount': {
      const site = getSite(data, siteKey);
      const account = site.accounts.find(a => a.id === msg.accountId);
      if (!account) return { ok: false, error: '账号不存在' };
      const cookies = await captureCookies(hostname);
      if (cookies.length === 0) {
        return { ok: false, error: '当前未检测到 Cookie，无法覆盖保存' };
      }
      account.cookies = cookies;
      account.webStorage = await captureWebStorage(msg.tabId);
      // 同步刷新昵称/头像：昵称仅在仍是默认「账号 N」时才覆盖，避免冲掉用户改过的名字
      const profile = await captureProfile(hostname, msg.tabId);
      if (profile.avatar) account.avatar = profile.avatar;
      if (profile.name && /^账号\s*\d+$/.test(account.name || '')) account.name = profile.name;
      account.updatedAt = Date.now();
      site.currentId = account.id;
      await saveData(data);
      return {
        ok: true,
        cookieCount: cookies.length,
        storageCount: storageKeyCount(account.webStorage),
        domains: domainsOf(cookies),
        name: account.name,
        avatar: account.avatar || ''
      };
    }

    case 'switchAccount': {
      const site = getSite(data, siteKey);
      const target = site.accounts.find(a => a.id === msg.accountId);
      if (!target) return { ok: false, error: '账号不存在' };
      const tabId = msg.tabId != null ? msg.tabId : null;

      await clearCookies(hostname);
      const result = await restoreCookies(target.cookies);
      // 回读一次，确认 Cookie 真正写进去了，而不是 API 静默失败
      const actualCookies = await captureCookies(hostname);
      site.currentId = target.id;
      target.updatedAt = Date.now();
      await saveData(data);

      // 主题/设置：只在这个页面应用（不跳转）；源不一致时跳过，仅刷新当前页让 Cookie 生效
      const storageState = await applyWebStorage(tabId, target.webStorage);
      if (storageState !== 'restored') {
        await reloadCurrentTab(tabId);
      }
      return {
        ok: true,
        restored: result.ok,
        actual: actualCookies.length,
        failed: result.failed,
        total: (target.cookies || []).length,
        storage: storageState,
        storageCount: storageKeyCount(target.webStorage)
      };
    }

    case 'renameAccount': {
      const site = getSite(data, siteKey);
      const account = site.accounts.find(a => a.id === msg.accountId);
      if (!account) return { ok: false, error: '账号不存在' };
      account.name = String(msg.name || '').trim() || account.name;
      account.note = String(msg.note || '').trim();
      await saveData(data);
      return { ok: true };
    }

    case 'deleteAccount': {
      const site = getSite(data, siteKey);
      const idx = site.accounts.findIndex(a => a.id === msg.accountId);
      if (idx < 0) return { ok: false, error: '账号不存在' };
      const wasCurrent = site.currentId === msg.accountId;
      site.accounts.splice(idx, 1);
      // 只删除插件里保存的这条账号记录，不动浏览器的 Cookie / 登录状态，也不刷新页面
      if (wasCurrent) site.currentId = null;
      await saveData(data);
      return { ok: true, wasCurrent };
    }

    case 'exportData': {
      // scope=site 只导出当前网站；默认导出全部网站
      if (msg.scope === 'site') {
        if (!isValidHost(hostname)) return { ok: false, error: '当前页面不支持导出' };
        const site = data.sites[siteKey];
        if (!site || !(site.accounts || []).length) {
          return { ok: false, error: `当前网站（${siteKey}）还没有保存账号` };
        }
        return {
          ok: true,
          scope: 'site',
          siteKey,
          fileName: `多账号备份_${siteKey}`,
          data: {
            app: 'accounts-switcher',
            scope: 'site',
            siteKey,
            exportedAt: Date.now(),
            sites: { [siteKey]: site }
          }
        };
      }
      return {
        ok: true,
        scope: 'all',
        fileName: '多账号备份_全部网站',
        data: {
          app: 'accounts-switcher',
          scope: 'all',
          exportedAt: Date.now(),
          sites: data.sites,
          settings: data.settings
        }
      };
    }

    case 'importData': {
      const incoming = msg.data;
      const incomingSites = incoming && incoming.sites;
      if (!incomingSites || typeof incomingSites !== 'object') {
        return { ok: false, error: '文件格式不正确' };
      }
      // 按网站合并：同 id 账号以导入数据为准，未冲突的本地账号保留
      let siteCount = 0;
      let accCount = 0;
      const keys = [];
      for (const [rawKey, value] of Object.entries(incomingSites)) {
        const list = value && Array.isArray(value.accounts) ? value.accounts : null;
        if (!list) continue;
        const sk = siteKeyFor(rawKey);
        const target = getSite(data, sk);
        const indexById = new Map(target.accounts.map((a, i) => [a.id, i]));
        for (const acc of list) {
          if (!acc || !acc.id || !Array.isArray(acc.cookies)) continue;
          const at = indexById.get(acc.id);
          if (at != null) target.accounts[at] = acc;
          else { target.accounts.push(acc); indexById.set(acc.id, target.accounts.length - 1); }
          accCount++;
        }
        if (!target.currentId && value.currentId) target.currentId = value.currentId;
        keys.push(sk);
        siteCount++;
      }
      if (siteCount === 0) return { ok: false, error: '备份里没有可导入的账号' };
      if (incoming.settings) data.settings = Object.assign(data.settings, incoming.settings);
      await saveData(data);
      return {
        ok: true,
        siteCount,
        accCount,
        siteKeys: Array.from(new Set(keys)),
        scope: incoming.scope === 'site' ? 'site' : 'all'
      };
    }

    case 'clearSite': {
      if (!data.sites[siteKey]) return { ok: true };
      delete data.sites[siteKey];
      await saveData(data);
      return { ok: true };
    }

    // 清空当前网站的登录态（Cookie + 本地存储），为登录新账号做准备；已保存的账号快照保留
    case 'resetSite': {
      const tabId = msg.tabId != null ? msg.tabId : null;
      const before = await captureCookies(hostname);
      await clearCookies(hostname);
      const storage = await clearWebStorage(tabId);
      const site = data.sites[siteKey];
      if (site) {
        site.currentId = null;
        await saveData(data);
      }
      await reloadCurrentTab(tabId);
      return {
        ok: true,
        cookieCount: before.length,
        storageCleared: !!storage.ok,
        origin: storage.origin || ''
      };
    }

    default:
      return { ok: false, error: '未知操作' };
  }
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  handleMessage(msg).then(sendResponse).catch(err => {
    sendResponse({ ok: false, error: String(err && err.message || err) });
  });
  return true; // 保持消息通道，异步响应
});
