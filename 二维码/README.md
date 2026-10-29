把快捷方式放在启动文件夹自启动

打包

> 当前构建配置（`二维码工具.spec`）已锁定为：**不压缩（upx=False）、不排除任何模块**，重新打包会得到与现版 `二维码工具.exe`（约 22.5 MB）功能等价的产物。

方式一：直接用命令行（与 `二维码工具.spec` 等价）
```bash
pyinstaller --noconfirm --noupx -F -w --name "二维码工具" --icon qr_icon.ico --distpath . --collect-all pyzbar qr_gui.pyw
```

方式二：用已固化的 spec 文件（推荐，配置写在 `.spec` 里）
```bash
pyinstaller --noconfirm --distpath . 二维码工具.spec
```

说明：
- `-F` 单文件、`-w` 窗口模式、`--icon qr_icon.ico` 内嵌图标、`--collect-all pyzbar` 收集解码所需的 zbar DLL。
- `--noupx` 对应 `.spec` 中的 `upx=False`，确保不被意外压缩（功能不变，体积保持原始大小）。
- 依赖：Python 环境中需安装 `qrcode`、`pyzbar`、`Pillow(PIL)`、`tkinterdnd2`、`PyInstaller`。
- 产物 `二维码工具.exe` 为自包含单文件，复制到任意 Windows 64 位电脑双击即可运行，无需安装运行库。

 