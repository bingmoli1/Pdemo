"""
Cookie管理器 - 高级版
支持：
1. 手动输入Cookie
2. 浏览器Cookie导入
3. 自定义Headers
4. Session会话保持
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import os
import requests
from datetime import datetime
import threading

class AdvancedCookieManager:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title("Cookie管理器 - 高级版")
        self.window.geometry("800x700")
        
        # 配置文件路径
        self.config_file = "advanced_cookies.json"
        
        # Session对象，保持会话
        self.session = requests.Session()
        
        self.setup_ui()
        self.load_all_cookies()
        
    def setup_ui(self):
        """设置用户界面"""
        # 顶部框架 - URL和Headers
        top_frame = tk.Frame(self.window)
        top_frame.pack(fill=tk.X, padx=20, pady=10)
        
        # URL输入
        tk.Label(top_frame, text="网站URL:", font=("Arial", 10)).grid(row=0, column=0, sticky=tk.W)
        self.url_entry = tk.Entry(top_frame, width=40, font=("Arial", 10))
        self.url_entry.grid(row=0, column=1, padx=5, pady=5)
        self.url_entry.insert(0, "https://")
        
        # Headers输入
        tk.Label(top_frame, text="Custom Headers (JSON):", font=("Arial", 10)).grid(row=0, column=2, sticky=tk.W)
        self.headers_entry = tk.Entry(top_frame, width=30, font=("Arial", 10))
        self.headers_entry.grid(row=0, column=3, padx=5, pady=5)
        self.headers_entry.insert(0, '{"User-Agent": "Mozilla/5.0"}')
        
        # 获取Cookie按钮组
        btn_frame = tk.Frame(top_frame)
        btn_frame.grid(row=0, column=4, padx=5)
        
        tk.Button(btn_frame, text="🔍 获取Cookie", command=self.fetch_cookie, 
                 bg="#4CAF50", fg="white", width=12).pack(side=tk.TOP, pady=2)
        tk.Button(btn_frame, text="📝 手动输入", command=self.manual_input, 
                 bg="#2196F3", fg="white", width=12).pack(side=tk.TOP, pady=2)
        tk.Button(btn_frame, text="📂 导入Cookie", command=self.import_cookie, 
                 bg="#FF9800", fg="white", width=12).pack(side=tk.TOP, pady=2)
        
        # 中间框架 - Cookie列表
        middle_frame = tk.Frame(self.window)
        middle_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Treeview显示Cookie列表
        columns = ("name", "value", "domain", "added_time")
        self.cookie_tree = ttk.Treeview(middle_frame, columns=columns, show="headings", height=12)
        
        self.cookie_tree.heading("name", text="Cookie名")
        self.cookie_tree.heading("value", text="Cookie值")
        self.cookie_tree.heading("domain", text="域名")
        self.cookie_tree.heading("added_time", text="添加时间")
        
        self.cookie_tree.column("name", width=120)
        self.cookie_tree.column("value", width=250)
        self.cookie_tree.column("domain", width=120)
        self.cookie_tree.column("added_time", width=120)
        
        scrollbar = ttk.Scrollbar(middle_frame, orient=tk.VERTICAL, command=self.cookie_tree.yview)
        self.cookie_tree.configure(yscrollcommand=scrollbar.set)
        
        self.cookie_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 右侧框架 - 详细信息
        right_frame = tk.Frame(self.window)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=10)
        
        tk.Label(right_frame, text="Cookie详情:", font=("Arial", 10, "bold")).pack(anchor=tk.W)
        
        self.detail_text = tk.Text(right_frame, height=15, width=30)
        self.detail_text.pack(fill=tk.BOTH, expand=True)
        
        # 底部框架 - 操作按钮
        bottom_frame = tk.Frame(self.window, pady=10)
        bottom_frame.pack(fill=tk.X, padx=20)
        
        tk.Button(bottom_frame, text="💾 保存", command=self.save_all_cookies, 
                 bg="#2196F3", fg="white", width=12).pack(side=tk.LEFT, padx=5)
        tk.Button(bottom_frame, text="📂 加载", command=self.load_all_cookies, 
                 bg="#FF9800", fg="white", width=12).pack(side=tk.LEFT, padx=5)
        tk.Button(bottom_frame, text="🚀 登录测试", command=self.login_test, 
                 bg="#9C27B0", fg="white", width=12).pack(side=tk.LEFT, padx=5)
        tk.Button(bottom_frame, text="🗑️ 清空", command=self.clear_all, 
                 bg="#F44336", fg="white", width=12).pack(side=tk.LEFT, padx=5)
        tk.Button(bottom_frame, text="📤 导出", command=self.export_cookies, 
                 bg="#607D8B", fg="white", width=12).pack(side=tk.LEFT, padx=5)
        
        # 状态栏
        self.status_label = tk.Label(self.window, text="就绪 | 高级版Cookie管理器", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)
        
        # 绑定选择事件
        self.cookie_tree.bind("<<TreeviewSelect>>", self.show_detail)
        
    def manual_input(self):
        """手动输入Cookie"""
        input_window = tk.Toplevel(self.window)
        input_window.title("手动输入Cookie")
        input_window.geometry("400x300")
        
        tk.Label(input_window, text="Cookie格式 (JSON):").pack(pady=5)
        
        text_area = tk.Text(input_window, height=10, width=50)
        text_area.pack(pady=5, padx=5, fill=tk.BOTH, expand=True)
        
        def save_manual():
            content = text_area.get(1.0, tk.END).strip()
            try:
                cookies = json.loads(content)
                if isinstance(cookies, dict):
                    self.add_cookies_to_tree(cookies)
                    messagebox.showinfo("成功", "Cookie已添加")
                    input_window.destroy()
                else:
                    messagebox.showwarning("警告", "请输入有效的JSON对象")
            except Exception as e:
                messagebox.showerror("错误", f"JSON格式错误: {str(e)}")
        
        tk.Button(input_window, text="保存", command=save_manual, bg="#4CAF50", fg="white").pack(pady=10)
        
    def import_cookie(self):
        """导入Cookie文件"""
        file_path = filedialog.askopenfilename(
            filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")],
            title="导入Cookie"
        )
        
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    cookies_data = json.load(f)
                    
                if isinstance(cookies_data, list):
                    # 如果是列表格式
                    for cookie in cookies_data:
                        if "name" in cookie and "value" in cookie:
                            self.add_cookies_to_tree({cookie["name"]: cookie["value"]}, cookie.get("domain", ""))
                elif isinstance(cookies_data, dict):
                    # 如果是字典格式
                    self.add_cookies_to_tree(cookies_data)
                    
                messagebox.showinfo("成功", f"已从 {file_path} 导入Cookie")
                
            except Exception as e:
                messagebox.showerror("错误", f"导入失败: {str(e)}")
                
    def add_cookies_to_tree(self, cookies, domain=""):
        """将Cookie添加到树形视图"""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        for name, value in cookies.items():
            # 检查是否已存在
            exists = False
            for item in self.cookie_tree.get_children():
                if self.cookie_tree.item(item, "values")[0] == name:
                    exists = True
                    break
                    
            if not exists:
                self.cookie_tree.insert("", tk.END, values=(name, value, domain or "N/A", current_time))
                
    def fetch_cookie(self):
        """获取网站Cookie"""
        url = self.url_entry.get().strip()
        if not url or url == "https://":
            messagebox.showwarning("警告", "请输入有效的网站URL")
            return
            
        # 解析Headers
        headers = {}
        headers_text = self.headers_entry.get().strip()
        if headers_text:
            try:
                headers = json.loads(headers_text)
            except:
                messagebox.showwarning("警告", "Headers JSON格式错误，使用默认Headers")
                
        if not headers:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            
        self.status_label.config(text=f"正在获取 {url} 的Cookie...")
        
        def fetch_thread():
            try:
                # 使用Session保持会话
                response = self.session.get(url, headers=headers, timeout=10)
                cookies = response.cookies.get_dict()
                
                if cookies:
                    self.add_cookies_to_tree(cookies, url)
                    self.status_label.config(text=f"成功获取 {len(cookies)} 个Cookie")
                    messagebox.showinfo("成功", f"获取到 {len(cookies)} 个Cookie")
                else:
                    self.status_label.config(text="未获取到Cookie")
                    messagebox.showinfo("提示", "未获取到Cookie，该网站可能不需要Cookie或有反爬机制")
                    
            except Exception as e:
                self.status_label.config(text="获取Cookie失败")
                messagebox.showerror("错误", f"获取Cookie失败: {str(e)}")
                
        threading.Thread(target=fetch_thread, daemon=True).start()
        
    def show_detail(self, event):
        """显示Cookie详情"""
        item = self.cookie_tree.selection()
        if item:
            values = self.cookie_tree.item(item, "values")
            if values:
                self.detail_text.delete(1.0, tk.END)
                detail = f"""Cookie名: {values[0]}
Cookie值: {values[1]}
域名: {values[2]}
添加时间: {values[3]}"""
                self.detail_text.insert(1.0, detail)
                
    def login_test(self):
        """使用Cookie登录测试"""
        url = self.url_entry.get().strip()
        if not url or url == "https://":
            messagebox.showwarning("警告", "请输入网站URL")
            return
            
        # 构建Cookie字典
        cookies = {}
        for item in self.cookie_tree.get_children():
            values = self.cookie_tree.item(item, "values")
            if values:
                cookies[values[0]] = values[1]
                
        if not cookies:
            messagebox.showwarning("警告", "没有Cookie数据")
            return
            
        self.status_label.config(text="正在测试登录...")
        
        def test_thread():
            try:
                headers = {}
                headers_text = self.headers_entry.get().strip()
                if headers_text:
                    try:
                        headers = json.loads(headers_text)
                    except:
                        pass
                        
                if not headers:
                    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                    
                response = self.session.get(url, cookies=cookies, headers=headers, timeout=10)
                
                self.window.after(0, lambda: self.status_label.config(text=f"测试完成，状态码: {response.status_code}"))
                
                if response.status_code == 200:
                    self.window.after(0, lambda: messagebox.showinfo("成功", f"登录测试成功！\n状态码: {response.status_code}\n页面长度: {len(response.text)} 字符"))
                else:
                    self.window.after(0, lambda: messagebox.showwarning("警告", f"登录测试失败，状态码: {response.status_code}"))
                    
            except Exception as e:
                self.window.after(0, lambda: self.status_label.config(text="测试失败"))
                self.window.after(0, lambda: messagebox.showerror("错误", f"测试失败: {str(e)}"))
                
        threading.Thread(target=test_thread, daemon=True).start()
        
    def save_all_cookies(self):
        """保存所有Cookie"""
        cookies_data = []
        
        for item in self.cookie_tree.get_children():
            values = self.cookie_tree.item(item, "values")
            if values:
                cookies_data.append({
                    "name": values[0],
                    "value": values[1],
                    "domain": values[2],
                    "added_time": values[3]
                })
                
        if not cookies_data:
            messagebox.showwarning("警告", "没有Cookie数据可保存")
            return
            
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(cookies_data, f, indent=2, ensure_ascii=False)
                
            messagebox.showinfo("成功", f"已保存 {len(cookies_data)} 个Cookie")
            self.status_label.config(text=f"Cookie已保存 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {str(e)}")
            
    def load_all_cookies(self):
        """加载所有Cookie"""
        if not os.path.exists(self.config_file):
            messagebox.showwarning("警告", f"配置文件 {self.config_file} 不存在")
            return
            
        try:
            # 清空当前列表
            for item in self.cookie_tree.get_children():
                self.cookie_tree.delete(item)
                
            with open(self.config_file, 'r', encoding='utf-8') as f:
                cookies_data = json.load(f)
                
            for cookie in cookies_data:
                self.cookie_tree.insert("", tk.END, values=(
                    cookie["name"],
                    cookie["value"],
                    cookie["domain"],
                    cookie["added_time"]
                ))
                
            messagebox.showinfo("成功", f"已加载 {len(cookies_data)} 个Cookie")
            self.status_label.config(text="Cookie已从文件加载")
            
        except Exception as e:
            messagebox.showerror("错误", f"加载失败: {str(e)}")
            
    def clear_all(self):
        """清空所有Cookie"""
        confirm = messagebox.askyesno("确认", "确定要清空所有Cookie吗？")
        if confirm:
            for item in self.cookie_tree.get_children():
                self.cookie_tree.delete(item)
            self.status_label.config(text="已清空所有Cookie")
            
    def export_cookies(self):
        """导出Cookie"""
        if not self.cookie_tree.get_children():
            messagebox.showwarning("警告", "没有Cookie数据可导出")
            return
            
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")],
            title="导出Cookie"
        )
        
        if file_path:
            try:
                cookies_data = []
                for item in self.cookie_tree.get_children():
                    values = self.cookie_tree.item(item, "values")
                    if values:
                        cookies_data.append({
                            "name": values[0],
                            "value": values[1],
                            "domain": values[2],
                            "added_time": values[3]
                        })
                        
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(cookies_data, f, indent=2, ensure_ascii=False)
                    
                messagebox.showinfo("成功", f"Cookie已导出到 {file_path}")
                
            except Exception as e:
                messagebox.showerror("错误", f"导出失败: {str(e)}")
                
    def run(self):
        """运行程序"""
        self.window.mainloop()

if __name__ == "__main__":
    app = AdvancedCookieManager()
    app.run()