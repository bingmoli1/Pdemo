# 多账号切换器 —— 项目长期记忆

## 工作约定（用户明确要求，必须遵守）
- **每次改动都要提升 `manifest.json` 的 `version`**（当前递增到 1.0.x 补丁位），并重新打包 `多账号切换器-扩展.zip`。
- 每次改完要给出「重新加载扩展」的提示（chrome://extensions → 重新加载）。
- 版本号在 popup 标题旁显示（`#ver`，取自 `chrome.runtime.getManifest().version`），用于确认是否加载成功。
- 交付物：`D:/Pdemo/多账号/多账号切换器-扩展.zip`（源码同目录）。
- 验证方式：`node --check` + 用 Node vm 模拟 chrome API 的测试脚本（/tmp/test_*.js）回归。

## 架构要点
- MV3 扩展，service worker = `background.js`，UI = `popup.html/css/js`。
- 账号按主域（eTLD+1）归组：`siteKeyFor()`，数据存 `chrome.storage.local` 的 `accountsSwitcher`。
- Cookie 范围硬隔离：`belongsToSite()` 只接受同主域及子域，保存/清除都不碰其他站点。
- 网站设置：`captureWebStorage/restoreWebStorage/applyWebStorage` 处理 localStorage/sessionStorage（按源隔离）。
- 切换行为：只写入 Cookie +（同源时）设置，然后只刷新当前标签页，**不做任何跳转**（`chrome.tabs.update` 已全部移除）。

## 已知限制
- 网站「退出登录」会注销服务端会话，写回旧 Cookie 也登不上；正确用法是用本扩展点卡片切换。
- 停在登录页（如 passport.bilibili.com）切换后不会自动回主站。
- 备份 JSON 含 localStorage，可能包含 token，敏感度等同账号密码。
