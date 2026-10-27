"""
浏览器Cookie导入工具
支持从Chrome、Firefox等浏览器导入Cookie
"""

import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
import sqlite3
from datetime import datetime

class BrowserCookieImporter:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title("浏览器Cookie导入工具")
        self.window.geometry("500x400")
        
        self.setup_ui()
        
    def setup_ui(self):
        """设置界面"""
        tk.Label(self.window, text="浏览器Cookie导入工具", font=("Arial", 16, "bold")).pack(pady=20)
        
        # 浏览器选择
        browser_frame = tk.Frame(self.window)
        browser_frame.pack(pady=10)
        
        tk.Label(browser_frame, text="选择浏览器:").pack(side=tk.LEFT)
        
        self.browser_var = tk.StringVar(value="chrome")
        browser_combo = ttk.Combobox(browser_frame, textvariable=self.browser_var, 
                                    values=["chrome", "firefox", "edge"], width=15)
        browser_combo.pack(side=tk.LEFT, padx=5)
        
        # 导入按钮
        import_btn = tk.Button(self.window, text="📥 导入Cookie", command=self.import_browser_cookie,
                              bg="#4CAF50", fg="white", width=20, height=2)
        import_btn.pack(pady=20)
        
        # 显示区域
        tk.Label(self.window, text="导入结果:").pack()
        
        self.result_text = tk.Text(self.window, height=10, width=50)
        self.result_text.pack(pady=10)
        
    def import_browser_cookie(self):
        """导入浏览器Cookie"""
        browser = self.browser_var.get()
        self.result_text.delete(1.0, tk.END)
        
        try:
            if browser == "chrome":
                cookies = self.import_chrome_cookie()
            elif browser == "firefox":
                cookies = self.import_firefox_cookie()
            elif browser == "edge":
                cookies = self.import_edge_cookie()
            else:
                messagebox.showerror("错误", "不支持的浏览器")
                return
                
            if cookies:
                self.result_text.insert(1.0, f"成功导入 {len(cookies)} 个Cookie:\n\n")
                for name, value in cookies.items():
                    self.result_text.insert(1.0, f"{name}: {value}\n")
                    
                # 保存到文件
                self.save_cookies(cookies)
                messagebox.showinfo("成功", f"已导入 {len(cookies)} 个Cookie")
            else:
                self.result_text.insert(1.0, "未找到Cookie数据")
                messagebox.showinfo("提示", "未找到Cookie数据")
                
        except Exception as e:
            self.result_text.insert(1.0, f"导入失败: {str(e)}")
            messagebox.showerror("错误", f"导入失败: {str(e)}")
            
    def import_chrome_cookie(self):
        """导入Chrome Cookie"""
        # Chrome Cookie数据库路径
        chrome_paths = [
            os.path.expanduser(r"\AppData\Local\Google\Chrome\User Data\Default\Cookies"),
            os.path.expanduser(r"\AppData\Local\Google\Chrome\User Data\Profile 1\Cookies"),
        ]
        
        for path in chrome_paths:
            if os.path.exists(path):
                try:
                    # Chrome Cookie使用SQLite存储
                    conn = sqlite3.connect(path)
                    cursor = conn.cursor()
                    cursor.execute("SELECT name, value FROM cookies")
                    cookies = {}
                    for name, value in cursor.fetchall():
                        cookies[name] = value
                    conn.close()
                    return cookies
                except:
                    continue
                    
        return {}
        
    def import_firefox_cookie(self):
        """导入Firefox Cookie"""
        # Firefox Cookie数据库路径
        firefox_path = os.path.expanduser(r"\AppData\Roaming\Mozilla\Firefox\Profiles\*.default\cookies.sqlite")
        
        import glob
        paths = glob.glob(firefox_path)
        
        for path in paths:
            if os.path.exists(path):
                try:
                    conn = sqlite3.connect(path)
                    cursor = conn.cursor()
                    cursor.execute("SELECT name, value FROM cookies")
                    cookies = {}
                    for name, value in cursor.fetchall():
                        cookies[name] = value
                    conn.close()
                    return cookies
                except:
                    continue
                    
        return {}
        
    def import_edge_cookie(self):
        """导入Edge Cookie"""
        # Edge Cookie数据库路径
        edge_paths = [
            os.path.expanduser(r"\AppData\Local\Microsoft\Edge\User Data\Default\Cookies"),
            os.path.expanduser(r"\AppData\Local\Microsoft\Edge\User Data\Profile 1\Cookies"),
        ]
        
        for path in edge_paths:
            if os.path.exists(path):
                try:
                    conn = sqlite3.connect(path)
                    cursor = conn.cursor()
                    cursor.execute("SELECT name, value FROM cookies")
                    cookies = {}
                    for name, value in cursor.fetchall():
                        cookies[name] = value
                    conn.close()
                    return cookies
                except:
                    continue
                    
        return {}
        
    def save_cookies(self, cookies):
        """保存Cookie到文件"""
        file_path = "browser_cookies.json"
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(cookies, f, indent=2, ensure_ascii=False)
            
    def run(self):
        self.window.mainloop()

if __name__ == "__main__":
    app = BrowserCookieImporter()
    app.run()