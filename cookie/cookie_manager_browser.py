"""
Cookie管理器 - 浏览器自动化版
使用 Selenium 驱动真实浏览器获取Cookie，解决JS渲染和反爬问题
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import os
import threading
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

class BrowserCookieManager:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title("Cookie管理器 - 浏览器自动化版")
        self.window.geometry("850x700")
        
        # 配置文件路径
        self.config_file = "browser_cookies.json"
        
        # Chrome driver 路径 (如果有)
        self.chromedriver_path = None
        
        self.setup_ui()
        self.load_cookies()
        
    def setup_ui(self):
        """设置界面"""
        # 顶部框架
        top_frame = tk.Frame(self.window, pady=10)
        top_frame.pack(fill=tk.X, padx=20)
        
        tk.Label(top_frame, text="网站URL:", font=("Arial", 10)).grid(row=0, column=0, sticky=tk.W)
        self.url_entry = tk.Entry(top_frame, width=40, font=("Arial", 10))
        self.url_entry.grid(row=0, column=1, padx=5, pady=5)
        self.url_entry.insert(0, "https://")
        
        # 打开浏览器获取Cookie按钮
        open_btn = tk.Button(top_frame, text="🌐 打开浏览器获取Cookie", 
                            command=self.open_browser_get_cookie, bg="#4CAF50", fg="white",
                            font=("Arial", 10, "bold"), width=20)
        open_btn.grid(row=0, column=2, padx=5)
        
        # 提示标签
        hint_label = tk.Label(self.window, text="提示：点击按钮会打开浏览器窗口，请登录网站，然后返回此窗口点击保存", 
                              fg="blue", font=("Arial", 9))
        hint_label.pack(pady=5)
        
        # 手动导入Cookie按钮
        import_frame = tk.Frame(self.window)
        import_frame.pack(pady=5)
        
        tk.Button(import_frame, text="📥 从浏览器导入Cookie", command=self.import_from_browser, 
                 bg="#FF9800", fg="white", width=20).pack(side=tk.LEFT, padx=5)
        tk.Button(import_frame, text="📝 手动粘贴Cookie", command=self.manual_paste, 
                 bg="#2196F3", fg="white", width=20).pack(side=tk.LEFT, padx=5)
        
        # Cookie列表
        middle_frame = tk.Frame(self.window)
        middle_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        columns = ("name", "value", "domain")
        self.cookie_tree = ttk.Treeview(middle_frame, columns=columns, show="headings", height=15)
        
        self.cookie_tree.heading("name", text="Cookie名")
        self.cookie_tree.heading("value", text="Cookie值")
        self.cookie_tree.heading("domain", text="域名")
        
        self.cookie_tree.column("name", width=150)
        self.cookie_tree.column("value", width=350)
        self.cookie_tree.column("domain", width=150)
        
        scrollbar = ttk.Scrollbar(middle_frame, orient=tk.VERTICAL, command=self.cookie_tree.yview)
        self.cookie_tree.configure(yscrollcommand=scrollbar.set)
        
        self.cookie_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 底部按钮
        bottom_frame = tk.Frame(self.window, pady=10)
        bottom_frame.pack(fill=tk.X, padx=20)
        
        tk.Button(bottom_frame, text="💾 保存Cookie", command=self.save_cookies, 
                 bg="#2196F3", fg="white", width=12).pack(side=tk.LEFT, padx=5)
        tk.Button(bottom_frame, text="📂 加载Cookie", command=self.load_cookies, 
                 bg="#FF9800", fg="white", width=12).pack(side=tk.LEFT, padx=5)
        tk.Button(bottom_frame, text="🚀 使用Cookie登录", command=self.login_with_cookie, 
                 bg="#9C27B0", fg="white", width=14).pack(side=tk.LEFT, padx=5)
        tk.Button(bottom_frame, text="🗑️ 清空", command=self.clear_all, 
                 bg="#F44336", fg="white", width=12).pack(side=tk.LEFT, padx=5)
        
        # 状态栏
        self.status_label = tk.Label(self.window, text="就绪 | 浏览器自动化版", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)
        
        # 浏览器驱动状态
        self.driver = None
        
    def open_browser_get_cookie(self):
        """打开真实浏览器获取Cookie"""
        url = self.url_entry.get().strip()
        if not url or url == "https://":
            messagebox.showwarning("警告", "请输入网站URL")
            return
            
        # 打开浏览器
        try:
            options = Options()
            # 使用默认用户数据，可以保留已登录状态
            # 取消注释下面这行，使用Chrome现有的登录状态
            # options.add_argument(r"--user-data-dir=C:\Users\你的用户名\AppData\Local\Google\Chrome\User Data")
            
            # 获取浏览器当前Cookie按钮
            fetch_btn = tk.Button(self.window, text="🔄 从打开的浏览器获取Cookie", 
                                 command=self.fetch_from_open_browser, bg="#F44336", fg="white",
                                 width=20)
            fetch_btn.pack(pady=5)
            
            self.status_label.config(text="正在打开浏览器，请在浏览器中登录网站...")
            
            self.driver = webdriver.Chrome(options=options)
            self.driver.get(url)
            
            self.status_label.config(text="浏览器已打开，请登录网站，然后点击【从打开的浏览器获取Cookie】")
            messagebox.showinfo("提示", "浏览器已打开。\n请完成登录，然后回到程序点击【从打开的浏览器获取Cookie】按钮")
            
        except Exception as e:
            error_msg = f"无法打开浏览器: {str(e)}\n\n请确保已安装Chrome浏览器，并安装selenium: pip install selenium"
            self.status_label.config(text="打开浏览器失败")
            messagebox.showerror("错误", error_msg)
            
    def fetch_from_open_browser(self):
        """从已打开的浏览器获取Cookie"""
        if self.driver is None:
            messagebox.showwarning("警告", "浏览器未打开")
            return
            
        try:
            # 获取所有Cookie
            cookies = self.driver.get_cookies()
            current_url = self.driver.current_url
            
            if not cookies:
                messagebox.showinfo("提示", "未获取到Cookie，请先登录网站")
                return
                
            # 清空并添加新Cookie
            for item in self.cookie_tree.get_children():
                self.cookie_tree.delete(item)
                
            for cookie in cookies:
                domain = cookie.get('domain', current_url)
                self.cookie_tree.insert("", tk.END, values=(cookie['name'], cookie['value'], domain))
                
            self.status_label.config(text=f"成功获取 {len(cookies)} 个Cookie")
            messagebox.showinfo("成功", f"已从浏览器获取 {len(cookies)} 个Cookie")
            
        except Exception as e:
            messagebox.showerror("错误", f"获取Cookie失败: {str(e)}")
            
    def import_from_browser(self):
        """从浏览器导入Cookie"""
        # 从Chrome导入
        try:
            from selenium import webdriver
            options = Options()
            
            # 找到Chrome的Cookie数据库
            import sqlite3
            import os
            
            chrome_profile = os.path.expanduser(r"~\AppData\Local\Google\Chrome\User Data\Default")
            cookie_db = os.path.join(chrome_profile, "Network", "Cookies")
            
            if os.path.exists(cookie_db):
                # 复制数据库，因为可能被Chrome锁定
                import shutil
                temp_db = "temp_cookies.db"
                shutil.copy2(cookie_db, temp_db)
                
                conn = sqlite3.connect(temp_db)
                cursor = conn.cursor()
                cursor.execute("SELECT name, value, host_key FROM cookies")
                
                for item in self.cookie_tree.get_children():
                    self.cookie_tree.delete(item)
                    
                count = 0
                for name, value, domain in cursor.fetchall():
                    if value:  # 只导入有值的Cookie
                        self.cookie_tree.insert("", tk.END, values=(name, value, domain))
                        count += 1
                        
                conn.close()
                os.remove(temp_db)
                
                self.status_label.config(text=f"从Chrome导入 {count} 个Cookie")
                messagebox.showinfo("成功", f"从Chrome导入 {count} 个Cookie")
            else:
                messagebox.showinfo("提示", "未找到Chrome的Cookie数据库")
                
        except Exception as e:
            messagebox.showerror("错误", f"导入失败: {str(e)}\n\n提示：可能需要关闭Chrome浏览器，或Chrome版本过新已加密Cookie")
            
    def manual_paste(self):
        """手动粘贴Cookie"""
        input_window = tk.Toplevel(self.window)
        input_window.title("手动粘贴Cookie")
        input_window.geometry("500x400")
        
        tk.Label(input_window, text="从浏览器F12 - Application - Cookies 复制Cookie字符串\n格式如: name1=value1; name2=value2", 
                 font=("Arial", 9)).pack(pady=5)
        
        text_area = tk.Text(input_window, height=15, width=60)
        text_area.pack(pady=5, padx=5, fill=tk.BOTH, expand=True)
        
        def parse_cookies():
            content = text_area.get(1.0, tk.END).strip()
            if not content:
                messagebox.showwarning("警告", "请输入Cookie")
                return
                
            try:
                # 尝试解析JSON
                cookies = json.loads(content)
                if isinstance(cookies, dict):
                    for name, value in cookies.items():
                        self.cookie_tree.insert("", tk.END, values=(name, value, "manual"))
                    messagebox.showinfo("成功", f"导入 {len(cookies)} 个Cookie")
                    input_window.destroy()
                    return
            except:
                pass
                
            # 解析 name=value; 格式
            cookie_items = content.replace(";", "; ").split("; ")
            count = 0
            for item in cookie_items:
                item = item.strip()
                if "=" in item:
                    name, value = item.split("=", 1)
                    name = name.strip()
                    value = value.strip()
                    if name and value:
                        self.cookie_tree.insert("", tk.END, values=(name, value, "manual"))
                        count += 1
                        
            messagebox.showinfo("成功", f"导入 {count} 个Cookie")
            input_window.destroy()
            
        tk.Button(input_window, text="导入", command=parse_cookies, bg="#4CAF50", fg="white", width=15).pack(pady=10)
        
    def save_cookies(self):
        """保存Cookie"""
        cookies_data = []
        
        for item in self.cookie_tree.get_children():
            values = self.cookie_tree.item(item, "values")
            if values:
                cookies_data.append({
                    "name": values[0],
                    "value": values[1],
                    "domain": values[2]
                })
                
        if not cookies_data:
            messagebox.showwarning("警告", "没有Cookie数据")
            return
            
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(cookies_data, f, indent=2, ensure_ascii=False)
            
        messagebox.showinfo("成功", f"已保存 {len(cookies_data)} 个Cookie")
        
    def load_cookies(self):
        """加载Cookie"""
        if not os.path.exists(self.config_file):
            return
            
        try:
            for item in self.cookie_tree.get_children():
                self.cookie_tree.delete(item)
                
            with open(self.config_file, 'r', encoding='utf-8') as f:
                cookies_data = json.load(f)
                
            for cookie in cookies_data:
                self.cookie_tree.insert("", tk.END, values=(
                    cookie["name"], cookie["value"], cookie["domain"]
                ))
                
        except:
            pass
            
    def login_with_cookie(self):
        """使用Cookie登录"""
        url = self.url_entry.get().strip()
        if not url or url == "https://":
            messagebox.showwarning("警告", "请输入网站URL")
            return
            
        cookies = {}
        for item in self.cookie_tree.get_children():
            values = self.cookie_tree.item(item, "values")
            if values:
                cookies[values[0]] = values[1]
                
        if not cookies:
            messagebox.showwarning("警告", "没有Cookie数据")
            return
            
        self.status_label.config(text="正在使用Cookie登录...")
        
        def login_thread():
            try:
                # 使用requests尝试
                import requests
                session = requests.Session()
                session.cookies.update(cookies)
                response = session.get(url, timeout=10)
                
                if response.status_code == 200:
                    self.window.after(0, lambda: self.status_label.config(text=f"登录成功，状态码: {response.status_code}"))
                    self.window.after(0, lambda: messagebox.showinfo("成功", f"Cookie登录成功！\n状态码: {response.status_code}"))
                else:
                    self.window.after(0, lambda: self.status_label.config(text=f"登录返回状态码: {response.status_code}"))
                    self.window.after(0, lambda: messagebox.showinfo("提示", f"登录返回状态码: {response.status_code}\n可能网站需要浏览器环境"))
                    
            except Exception as e:
                self.window.after(0, lambda: self.status_label.config(text="登录失败"))
                self.window.after(0, lambda: messagebox.showerror("错误", f"登录失败: {str(e)}"))
                
        threading.Thread(target=login_thread, daemon=True).start()
        
    def clear_all(self):
        """清空所有Cookie"""
        confirm = messagebox.askyesno("确认", "确定清空所有Cookie吗？")
        if confirm:
            for item in self.cookie_tree.get_children():
                self.cookie_tree.delete(item)
                
    def run(self):
        self.window.mainloop()

if __name__ == "__main__":
    app = BrowserCookieManager()
    app.run()