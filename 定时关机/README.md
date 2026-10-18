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

## 开机自启

把 `定时关机.exe` 的快捷方式放到启动文件夹（Win+R 输入 `shell:startup` 打开）。
