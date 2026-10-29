# 项目长期要点（闲鱼自动发货）

## 关键约定
- 发货模式：每个商品的 `cards` 是**一整段文本**，发货时原样整段发出，**不消耗、不删除**（旧的"一行一卡"数组会自动 join）。
- 商品/发货内容存在 `products.json`，全局设置（选择器、触发词等）在 `config.json`；管理页改完需在该账号「停止」后「启动」生效（旧 `启动自动发货.bat`/`停止自动发货.bat` 已于 2026-10-29 删除，启动停止统一走商品管理页按钮或 `python auto_delivery.py run [--account 账号]`）。
- 管理页：`商品管理.bat` → http://127.0.0.1:8765；点顶部标题直接回列表（不弹确认）；批量导入功能已按用户要求删除。
- 登录态：`browser_data/`（config.json 的 `user_data_dir`），一个目录 = 一个闲鱼账号，同时只能被一个程序实例占用。
- `my_user_id` 优先用于识别"自己发的消息"，留空则自动读 cookie 的 unb。
- 去重：`data/delivered.json` 按「买家昵称｜商品名(规格)」记录；`data/used_cards.log` 只是发货流水。

## 换账号流程（手动）
1. 停程序：在商品管理页对该账号点「■ 停止」/「全部停止」，或关掉控制台+浏览器窗口。
2. 隔离登录态：改名 `browser_data` → `browser_data_旧号`（保留旧号），或把 `config.json` 的 `user_data_dir` 改成新名字（如 `browser_data2`）；彻底清掉就删目录。
3. 在商品管理页点对应账号「▶ 启动」，10 分钟内手机扫码登录新号（或先跑 `python auto_delivery.py login`）。
4. 核对：日志首行「本机用户ID(unb)」应是新号；`products.json` 的认单关键词要能匹配新号在售商品，否则会"未匹配到商品，跳过"。
5. 换回旧号：把 `user_data_dir` 改回旧目录即可。
- 多账号并行（2026-10-29 起支持）：每个账号是一个沙盒——登录档案、`delivered.<账号>.json`、`used_cards.<账号>.log`、`logs/run_<账号>.log` 各自独立；实例内 `cfg["accounts"]` 只含自己（`sandbox_for`），不会改「当前账号」。商品/发货内容所有账号共用一份 products.json（用户明确选择）。运行实例记账 `data/.running/<账号>.json`（pid+dir+时间），同一账号/同一档案目录重复启动会被拦截；管理页每个账号可单独启动/停止，也可全部启停。服务版本 4（前后端握手 PAGE_VERSION/APP_VERSION 保持一致）。
