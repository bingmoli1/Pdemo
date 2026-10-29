# Windows 定时关机工具

tkinter 小工具：分钟倒计时关机、指定时间关机、取消关机，任务持久化，重启程序自动恢复倒计时。

## 直接运行

```bash
python main.py
```

## 打包成 exe

```bash
pip install pyinstaller
pyinstaller -F -w --name "定时关机" --distpath . main.py
```

说明：

- `-F`：打包成单文件 exe
- `-w`：无控制台黑窗
- `--name "定时关机"`：生成的程序名为 `定时关机.exe`
- `--distpath .`：exe 直接输出到项目根目录（不生成 dist 文件夹）
- 可加 `--noconfirm`：覆盖旧文件时不再询问

打包会产生 `build\` 中间目录和 `定时关机.spec`，exe 正常运行不依赖它们，可随意删除。
重复打包时 PyInstaller 会复用缓存，速度更快；如打包异常可先删除 `build\` 目录再重新打包。

## 运行环境要求（分发到新电脑前必看）

`定时关机.exe` 是单文件自包含程序，拷过去双击即可，无需安装 Python 或 VC++ 运行库，也不需要管理员权限。

| 系统 | 能否运行 | 说明 |
| --- | --- | --- |
| Windows 11 x64 | ✅ | 正常 |
| Windows 10 x64（1809 及以上） | ✅ | 正常，UCRT 随系统提供 |
| Windows 10/11 ARM64 | ⚠️ | 靠系统 x64 模拟运行，一般可用，未实测 |
| Windows 8.1 / 8 | ❌ | 打包用的是 Python 3.14，官方只支持 Win10+ |
| Windows 7 | ❌ | 缺 `api-ms-win-core-path-l1-1-0.dll`，且 Python 3.14 不支持 |
| 32 位 Windows | ❌ | exe 为 64 位（x64） |

若必须支持 Windows 7，需用 Python 3.8 重新打包；支持 Windows 8.1 需用 Python 3.12（`main.py` 代码本身兼容这两版）。

新电脑上首次运行可能遇到：

- SmartScreen 提示"Windows 已保护你的电脑" → 点"更多信息" → "仍要运行"（exe 未做代码签名）。
- 杀软/公司 AppLocker 拦截 → 需加白名单（pyinstaller 单文件程序易被误报）。
- 单文件运行时会把自身解压到 `%TEMP%\_MEIxxxx`，该目录必须可写（一般账号都满足）。

## 开机自启

把 `定时关机.exe` 的快捷方式放到启动文件夹（Win+R 输入 `shell:startup` 打开）。
