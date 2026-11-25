'use strict';

const $ = id => document.getElementById(id);

const state = {
  tabId: null,
  hostname: '',
  siteKey: '',
  currentId: null,
  accounts: [],
  editingId: null,
  busy: false
};

let toastTimer = null;

function send(msg) {
  return new Promise(resolve => {
    chrome.runtime.sendMessage(Object.assign({ tabId: state.tabId }, msg), res => {
      if (chrome.runtime.lastError) {
        resolve({ ok: false, error: chrome.runtime.lastError.message });
      } else {
        resolve(res || { ok: false, error: '后台无响应' });
      }
    });
  });
}

function toast(text) {
  const el = $('toast');
  el.textContent = text;
  el.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add('hidden'), 2600);
}

/** 自定义确认弹窗，返回 Promise<boolean>；避免浏览器原生 confirm 的丑陋样式 */
function showConfirm({ title, desc, okText = '确定', danger = false }) {
  return new Promise(resolve => {
    const modal = $('modal');
    $('modalTitle').textContent = title;
    $('modalDesc').textContent = desc || '';
    $('modalOk').textContent = okText;
    $('modalOk').className = 'btn ' + (danger ? 'btn-danger' : 'btn-primary');
    $('modalIcon').className = 'modal-icon' + (danger ? '' : ' safe');
    $('modalIcon').textContent = danger ? '!' : 'i';
    modal.classList.remove('hidden');

    const cleanup = () => {
      modal.classList.add('hidden');
      document.removeEventListener('keydown', onKey);
      $('modalOk').onclick = null;
      $('modalCancel').onclick = null;
      modal.querySelector('.modal-mask').onclick = null;
    };
    const done = ok => { cleanup(); resolve(ok); };
    const onKey = e => { if (e.key === 'Escape') done(false); };

    $('modalOk').onclick = () => done(true);
    $('modalCancel').onclick = () => done(false);
    modal.querySelector('.modal-mask').onclick = () => done(false);
    document.addEventListener('keydown', onKey);
    setTimeout(() => $('modalCancel').focus(), 0);
  });
}

function showNotice(text) {
  const el = $('notice');
  el.textContent = text;
  el.classList.remove('hidden');
}

function timeAgo(ts) {
  if (!ts) return '';
  const diff = Date.now() - ts;
  if (diff < 60000) return '刚刚更新';
  if (diff < 3600000) return Math.floor(diff / 60000) + ' 分钟前更新';
  if (diff < 86400000) return Math.floor(diff / 3600000) + ' 小时前更新';
  return new Date(ts).toLocaleDateString('zh-CN') + ' 更新';
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function render() {
  const list = $('accountList');
  list.innerHTML = '';
  $('count').textContent = String(state.accounts.length);
  $('empty').classList.toggle('hidden', state.accounts.length > 0);
  $('addBtn').disabled = state.busy || !state.hostname;
  $('resetBtn').disabled = state.busy || !state.hostname;

  for (const acc of state.accounts) {
    const card = el('div', 'card' + (acc.id === state.currentId ? ' is-current' : '') + ' clickable');
    card.dataset.id = acc.id;
    card.title = '点此卡片切换到该账号 · 点「更新」保存当前登录态';

    if (state.editingId === acc.id) {
      const box = el('div', 'edit-box');
      const nameInput = el('input');
      nameInput.type = 'text';
      nameInput.value = acc.name;
      nameInput.placeholder = '账号名称';
      nameInput.dataset.field = 'name';
      const noteInput = el('input');
      noteInput.type = 'text';
      noteInput.value = acc.note || '';
      noteInput.placeholder = '备注（可选）';
      noteInput.dataset.field = 'note';
      const actions = el('div', 'edit-actions');
      const save = el('button', 'act primary', '保存');
      save.dataset.action = 'saveEdit';
      const cancel = el('button', 'act', '取消');
      cancel.dataset.action = 'cancelEdit';
      actions.append(save, cancel);
      box.append(nameInput, noteInput, actions);
      card.append(box);
      list.append(card);
      continue;
    }

    const avatar = el('div', 'avatar');
    const initial = (acc.name || '?').trim().charAt(0).toUpperCase();
    if (acc.avatar) {
      const img = document.createElement('img');
      img.src = acc.avatar;
      img.alt = '';
      img.addEventListener('error', () => {
        avatar.textContent = initial;
      });
      avatar.append(img);
    } else {
      avatar.textContent = initial;
    }
    const info = el('div', 'info');
    const nameLine = el('div', 'name');
    nameLine.append(document.createTextNode(acc.name));
    if (acc.id === state.currentId) nameLine.append(el('span', 'badge', '当前'));
    info.append(nameLine);
    const metaBits = [acc.cookieCount + ' 项 Cookie'];
    if (acc.domains && acc.domains.length) metaBits[0] += `（${scopeText(acc.domains)}）`;
    if (acc.storageCount) metaBits.push(`${acc.storageCount} 项设置`);
    if (acc.note) metaBits.push(acc.note);
    metaBits.push(timeAgo(acc.updatedAt));
    info.append(el('div', 'meta', metaBits.join(' · ')));

    const actions = el('div', 'actions');
    // 「更新」：把当前网页的登录态采集并覆盖保存进该账号
    const mainBtn = el('button', 'act primary', '更新');
    mainBtn.dataset.action = 'overwrite';
    const editBtn = el('button', 'act icon', '✎');
    editBtn.dataset.action = 'edit';
    editBtn.title = '编辑名称/备注';
    const delBtn = el('button', 'act icon danger', '×');
    delBtn.dataset.action = 'delete';
    delBtn.title = '删除账号';
    if (state.busy) {
      mainBtn.disabled = editBtn.disabled = delBtn.disabled = true;
    }
    actions.append(mainBtn, editBtn, delBtn);

    card.append(avatar, info, actions);
    list.append(card);
  }
}

async function refresh() {
  const res = await send({ type: 'getSiteData', hostname: state.hostname });
  if (res.ok) {
    state.currentId = res.currentId;
    state.siteKey = res.siteKey;
    state.accounts = res.accounts;
  } else {
    showNotice(res.error || '读取账号失败');
  }
  render();
}

/** 把域名列表折成一句简短说明，例如「bilibili.com 等 3 个域名」 */
function scopeText(domains) {
  const list = domains || [];
  if (!list.length) return '';
  if (list.length === 1) return list[0];
  return `${list[0]} 等 ${list.length} 个域名`;
}

async function init() {
  try {
    $('ver').textContent = 'v' + chrome.runtime.getManifest().version;
  } catch (_) { /* ignore */ }

  let tab = null;
  try {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    tab = tabs && tabs[0];
  } catch (_) { /* ignore */ }

  let hostname = '';
  try { hostname = new URL(tab && tab.url || '').hostname; } catch (_) { /* ignore */ }
  state.hostname = hostname;
  state.tabId = tab && tab.id != null ? tab.id : null;

  const url = (tab && tab.url) || '';
  if (!hostname || !/^https?:$/.test(new URL(url).protocol)) {
    showNotice('请在普通的 http(s) 网站上使用；浏览器内置页面（chrome://、扩展商店等）无法读取 Cookie。');
    $('addBtn').disabled = true;
    render();
    return;
  }

  await refresh();
}

async function applyAccount(id) {
  const account = state.accounts.find(a => a.id === id);
  if (!account) return;
  state.busy = true; render();
  const res = await send({ type: 'switchAccount', hostname: state.hostname, accountId: id });
  state.busy = false;
  if (res.ok) {
    const fail = res.failed && res.failed.length ? `，${res.failed.length} 项写入失败` : '';
    const storage = res.storage === 'restored'
      ? `，设置已恢复（${res.storageCount} 项）`
      : (res.storage === 'skipped' ? '，设置未同步（当前页面与该账号保存时不同页）' : (res.storage === 'failed' ? '，设置恢复失败' : ''));
    toast(`已切换到「${account.name}」，生效 ${res.actual}/${res.total} 项${fail}${storage}`);
  } else toast(res.error || '切换失败');
  await refresh();
}

$('accountList').addEventListener('click', async e => {
  if (state.busy) return;
  const card = e.target.closest('.card');
  if (!card) return;
  const btn = e.target.closest('button[data-action]');
  // 点卡片其余区域 = 切换到这个账号的信息；编辑态下不触发
  if (!btn) {
    if (state.editingId === card.dataset.id) return;
    await applyAccount(card.dataset.id);
    return;
  }
  const id = card && card.dataset.id;
  const action = btn.dataset.action;
  const account = state.accounts.find(a => a.id === id);

  if (action === 'overwrite') {
    state.busy = true; render();
    const res = await send({ type: 'overwriteAccount', hostname: state.hostname, accountId: id });
    state.busy = false;
    toast(res.ok ? '保存成功' : (res.error || '更新失败'));
    await refresh();
  } else if (action === 'edit') {
    state.editingId = id;
    render();
    const input = document.querySelector('.card .edit-box input[data-field="name"]');
    if (input) { input.focus(); input.select(); }
  } else if (action === 'saveEdit') {
    const box = card.querySelector('.edit-box');
    const name = box.querySelector('[data-field="name"]').value.trim();
    const note = box.querySelector('[data-field="note"]').value.trim();
    const res = await send({ type: 'renameAccount', hostname: state.hostname, accountId: id, name, note });
    state.editingId = null;
    toast(res.ok ? '已保存' : (res.error || '保存失败'));
    await refresh();
  } else if (action === 'cancelEdit') {
    state.editingId = null;
    render();
  } else if (action === 'delete') {
    const ok = await showConfirm({
      title: `删除「${account.name}」？`,
      desc: '删除后无法恢复，浏览器登录状态不受影响。',
      okText: '删除',
      danger: true
    });
    if (!ok) return;
    state.busy = true; render();
    const res = await send({ type: 'deleteAccount', hostname: state.hostname, accountId: id });
    state.busy = false;
    toast(res.ok
      ? `已删除「${account.name}」，登录状态未受影响`
      : (res.error || '删除失败'));
    await refresh();
  }
});

$('resetBtn').addEventListener('click', async () => {
  if (!state.hostname || state.busy) return;
  state.busy = true; render();
  const res = await send({ type: 'resetSite', hostname: state.hostname });
  state.busy = false;
  if (res.ok) {
    const bits = [];
    if (res.cookieCount) bits.push(`${res.cookieCount} 项 Cookie`);
    if (res.storageCleared) bits.push('本地设置');
    toast(bits.length ? `已清除 ${bits.join('、')}，现在可以登录新账号` : '已清除，现在可以登录新账号');
  } else {
    toast(res.error || '清除失败');
  }
  await refresh();
});

$('addBtn').addEventListener('click', async () => {
  if (!state.hostname || state.busy) return;
  state.busy = true; render();
  const res = await send({
    type: 'addAccount',
    hostname: state.hostname
  });
  state.busy = false;
  if (res.ok) toast(`已保存新账号：仅 ${scopeText(res.domains)}，共 ${res.cookieCount} 项 Cookie`
    + (res.storageCount ? `，${res.storageCount} 项网站设置` : ''));
  else toast(res.error || '保存失败');
  await refresh();
});

async function doExport(scope) {
  if (scope === 'site' && !state.accounts.length) {
    toast(`当前网站（${state.siteKey || state.hostname}）还没有账号可导出`);
    return;
  }
  const res = await send({ type: 'exportData', scope });
  if (!res.ok) { toast(res.error || '导出失败'); return; }
  const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  const d = new Date();
  const stamp = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`;
  a.href = url;
  a.download = `${res.fileName || '多账号备份'}_${stamp}.json`;
  a.click();
  URL.revokeObjectURL(url);
  const siteCount = Object.keys(res.data.sites || {}).length;
  toast(scope === 'site'
    ? `已导出本站备份（${res.siteKey}，${state.accounts.length} 个账号）`
    : `已导出全部备份（${siteCount} 个网站）`);
}

$('exportSiteBtn').addEventListener('click', () => doExport('site'));
$('exportBtn').addEventListener('click', () => doExport('all'));

$('importBtn').addEventListener('click', () => $('importFile').click());

$('importFile').addEventListener('change', async e => {
  const file = e.target.files && e.target.files[0];
  if (!file) return;
  try {
    const parsed = JSON.parse(await file.text());
    const res = await send({ type: 'importData', data: parsed });
    toast(res.ok
      ? `已导入 ${res.siteCount} 个网站、${res.accCount} 个账号`
      : (res.error || '导入失败'));
    if (res.ok) await refresh();
  } catch (_) {
    toast('文件不是有效的 JSON 备份');
  }
  e.target.value = '';
});

init();
