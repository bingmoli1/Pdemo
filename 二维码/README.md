把快捷方式放在启动文件夹自启动

打包
```bash
pyinstaller --noconfirm -F -w --name "二维码工具" --icon qr_icon.ico --distpath . --collect-all pyzbar qr_gui.pyw

```
 