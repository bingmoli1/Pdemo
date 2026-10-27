"""
Cookie管理器 - 增强版
功能：
1. 获取网站Cookie
2. 保存/加载Cookie
3. 自动登录
4. 支持多网站Cookie管理
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import os
import requests
from datetime import datetime
import threading

class CookieManagerApp:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title("Cookie管理器 - 自动登录工具")
        self.window.geometry("700x600")
        
        # 配置文件路径
        self.config_file = "cookies_storage.json"
        
        # 创建样式
        self.setup_styles()
        self.setup_ui()
        self.load_all_cookies()
        
    def setup_styles(self):
        """设置UI样式"""
        style = ttk.Style()
        style.theme_use('clam')
        
    def setup_ui(self):
        """设置用户界面"""
        # 顶部框架 - URL输入
        top_frame = tk.Frame(self.window, pady=10)
        top_frame.pack(fill=tk.X, padx=20)
        
        tk.Label(top_frame, text="网站URL:", font=("Arial", 10)).grid(row=0, column=0, sticky=tk.W)
        self.url_entry = tk.Entry(top_frame, width=50, font=("Arial", 10))
        self.url_entry.grid(row=0, column=1, padx=5, pady=5)
        self.url_entry.insert(0, "https://")
        
        get_cookie_btn = tk.Button(top_frame, text="🔍 获取Cookie", command=self.fetch_cookie, 
                                  bg="#4CAF50", fg="white", font=("Arial", 10, "bold"), width=12)
        get_cookie_btn.grid(row=0, column=2, padx=5)
        
        # 中间框架 - Cookie列表
        middle_frame = tk.Frame(self.window)
        middle_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Treeview显示Cookie列表
        columns = ("name", "value", "domain", "added_time")
        self.cookie_tree = ttk.Treeview(middle_frame, columns=columns, show="headings", height=10)
        
        self.cookie_tree.heading("name", text="Cookie名")
        self.cookie_tree.heading("value", text="Cookie值")
        self.cookie_tree.heading("domain", text="域名")
        self.cookie_tree.heading("added_time", text="添加时间")
        
        self.cookie_tree.column("name", width=150)
        self.cookie_tree.column("value", width=200)
        self.cookie_tree.column("domain", width=150)
        self.cookie_tree.column("added_time", width=120)
        
        scrollbar = ttk.Scrollbar(middle_frame, orient=tk.VERTICAL, command=self.cookie_tree.yview)
        self.cookie_tree.configure(yscrollcommand=scrollbar.set)
        
        self.cookie_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 右键菜单
        self.context_menu = tk.Menu(self.window, tearoff=0)
        self.context_menu.add_command(label="复制Cookie值", command=self.copy_cookie_value)
        self.context_menu.add_command(label="删除Cookie", command=self.delete_cookie)
        self.cookie_tree.bind("<Button-3>", self.show_context_menu)
        
        # 底部框架 - 操作按钮
        bottom_frame = tk.Frame(self.window, pady=10)
        bottom_frame.pack(fill=tk.X, padx=20)
        
        save_all_btn = tk.Button(bottom_frame, text="💾 保存所有Cookie", command=self.save_all_cookies, 
                                bg="#2196F3", fg="white", width=15)
        save_all_btn.pack(side=tk.LEFT, padx=5)
        
        load_all_btn = tk.Button(bottom_frame, text="📂 加载所有Cookie", command=self.load_all_cookies, 
                                bg="#FF9800", fg="white", width=15)
        load_all_btn.pack(side=tk.LEFT, padx=5)
        
        login_btn = tk.Button(bottom_frame, text="🚀 使用Cookie登录", command=self.login_with_cookie, 
                             bg="#9C27B0", fg="white", width=15)
        login_btn.pack(side=tk.LEFT, padx=5)
        
        export_btn = tk.Button(bottom_frame, text="📤 导出Cookie", command=self.export_cookies, 
                              bg="#F44336", fg="white", width=15)
        export_btn.pack(side=tk.LEFT, padx=5)
        
        # 状态栏
        self.status_label = tk.Label(self.window, text="就绪 | 支持多网站Cookie管理", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)
        
        # 详细Cookie显示区域
        detail_frame = tk.Frame(self.window, pady=10)
        detail_frame.pack(fill=tk.BOTH, expand=True, padx=20)
        
        tk.Label(detail_frame, text="Cookie详情:", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky=tk.W)
        
        self.detail_text = tk.Text(detail_frame, height=8, width=80)
        self.detail_text.grid(row=1, column=0, columnspan=3, pady=5)
        
        # 绑定Treeview选择事件
        self.cookie_tree.bind("<<TreeviewSelect>>", self.show_cookie_detail)
        
    def show_context_menu(self, event):
        """显示右键菜单"""
        item = self.cookie_tree.selection()
        if item:
            self.context_menu.post(event.x_root, event.y_root)
            
    def copy_cookie_value(self):
        """复制Cookie值"""
        item = self.cookie_tree.selection()
        if item:
            values = self.cookie_tree.item(item, "values")
            if values:
                self.window.clipboard_clear()
                self.window.clipboard_append(values[1])
                messagebox.showinfo("成功", "Cookie值已复制到剪贴板")
                
    def delete_cookie(self):
        """删除选中的Cookie"""
        item = self.cookie_tree.selection()
        if item:
            confirm = messagebox.askyesno("确认", "确定要删除选中的Cookie吗？")
            if confirm:
                self.cookie_tree.delete(item)
                self.status_label.config(text="Cookie已删除")
                
    def show_cookie_detail(self, event):
        """显示选中Cookie的详细信息"""
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
                
    def fetch_cookie(self):
        """获取网站Cookie（在新线程中运行）"""
        url = self.url_entry.get().strip()
        if not url or url == "https://":
            messagebox.showwarning("警告", "请输入有效的网站URL")
            return
            
        self.status_label.config(text=f"正在获取 {url} 的Cookie...")
        get_cookie_btn = tk.Button(self.window, text="⏳ 获取中...", state=tk.DISABLED)
        
        def fetch_thread():
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                response = requests.get(url, headers=headers, timeout=10)
                cookies = response.cookies.get_dict()
                
                # 更新UI
                self.window.after(0, lambda: self.update_cookie_tree(cookies, url))
                self.window.after(0, lambda: self.status_label.config(text=f"成功获取 {len(cookies)} 个Cookie"))
                self.window.after(0, lambda: messagebox.showinfo("成功", f"获取到 {len(cookies)} 个Cookie"))
                
            except Exception as e:
                self.window.after(0, lambda: self.status_label.config(text="获取Cookie失败"))
                self.window.after(0, lambda: messagebox.showerror("错误", f"获取Cookie失败: {str(e)}"))
                
        threading.Thread(target=fetch_thread, daemon=True).start()
        
    def update_cookie_tree(self, cookies, domain):
        """更新Cookie列表"""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        for name, value in cookies.items():
            self.cookie_tree.insert("", tk.END, values=(name, value, domain, current_time))
            
    def save_all_cookies(self):
        """保存所有Cookie到文件"""
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
                
            messagebox.showinfo("成功", f"已保存 {len(cookies_data)} 个Cookie到 {self.config_file}")
            self.status_label.config(text=f"Cookie已保存 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {str(e)}")
            
    def load_all_cookies(self):
        """从文件加载所有Cookie"""
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
            
    def login_with_cookie(self):
        """使用Cookie登录"""
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
            
        self.status_label.config(text="正在使用Cookie登录...")
        
        def login_thread():
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                response = requests.get(url, cookies=cookies, headers=headers, timeout=10)
                
                self.window.after(0, lambda: self.status_label.config(text=f"登录完成，状态码: {response.status_code}"))
                
                if response.status_code == 200:
                    self.window.after(0, lambda: messagebox.showinfo("成功", f"Cookie登录成功！\n状态码: {response.status_code}\n页面长度: {len(response.text)} 字符"))
                else:
                    self.window.after(0, lambda: messagebox.showwarning("警告", f"登录失败，状态码: {response.status_code}"))
                    
            except Exception as e:
                self.window.after(0, lambda: self.status_label.config(text="登录失败"))
                self.window.after(0, lambda: messagebox.showerror("错误", f"登录失败: {str(e)}"))
                
        threading.Thread(target=login_thread, daemon=True).start()
        
    def export_cookies(self):
        """导出Cookie为JSON文件"""
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
    app = CookieManagerApp()
    app.run()