打包

双击 `build.bat` 即可；或在本目录打开 Git Bash 执行下面这条命令（全文只此一条）：

```bash
(taskkill /F /IM "二维码工具.exe" 2>/dev/null || true) && py -m pip install --disable-pip-version-check -q pyinstaller qrcode pyzbar pillow tkinterdnd2 && py -m PyInstaller --noconfirm --distpath . "二维码工具.spec"
```

- 整个项目文件夹拷到任意电脑、任意位置都能直接打包：`build.bat` 用 `%~dp0` 自定位，命令不含绝对路径；都用不带版本号的 `py` 并自动 `pip install` 依赖，换 Python 版本也能构建。
- 新电脑只需装一个较新的 Python 3（勾选 py launcher），首次联网装依赖约 10 MB；没装 Python 或缺依赖时脚本会给出提示。
- 必须走 `二维码工具.spec`（单文件 + `collect_all('pyzbar')`）。**不要**换成纯参数命令，漏掉 zbar 会让新机器上「二维码 → 文本」失效。
- 产物 `二维码工具.exe` 自包含：拷单个文件即可在 Win10/11 x64 运行，无需 Python / Office / VC++、不联网；首次运行可能被 SmartScreen 拦，选「仍要运行」。别只拷 `.lnk` 快捷方式。

功能

> 启动即进入批量转码主界面，关闭窗口即退出。

- **文本 → 二维码**：一行一条内容，可导入 / 拖入多个 TXT、CSV、TSV、Excel、Word 清单，或直接粘贴。可设输出目录（默认 `桌面/二维码批量输出`）、命名方式（默认「内容命名」）、前缀（默认空）、起始序号；生成 PNG，同名自动加后缀不覆盖。结果表格**双击一行复制该二维码图片**（可直接 Ctrl+V 到微信 / Word），也能在识别页「剪贴板粘贴」放回来识别。
- **清单解析**：Word 按每行一条（表格取每行首格）；Excel 读取所有非空单元格、按行优先、跳过表头（只读第一个工作表）；CSV / TSV 取每行第一个非空单元格；空行忽略。只用标准库，无需装 Office；旧版 `.xls` / `.doc` 需另存为新格式。
- **二维码 → 文本**：添加图片 / 文件夹 / 剪贴板粘贴 / 拖入；「包含子文件夹」默认勾选；一图多码全部读出。结果表格**双击一行单独复制该行识别内容**，也可一键复制全部，或导出 CSV / TXT / Excel / Word。Word / TXT 一行一条识别内容；CSV / Excel 为「序号 / 文件名 / 状态 / 识别结果」四列表格。
- **记住上次设置**：输出目录、命名、前缀、起始序号、递归、导出格式、页签存到 `%APPDATA%\二维码工具\settings.json`（纯文本 JSON，删掉即恢复默认）；不记输入内容和识别结果。
- 生成 / 识别可取消，进度由右上角「处理中 x/y」文字显示；两个页面不设进度条。

验证

双击 `二维码工具.exe` 检查启动；改动源码后按开头命令重新打包。
