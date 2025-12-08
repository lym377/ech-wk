#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ECH Workers 客户端 - 跨平台版本 (Python + PyQt5)
支持 Windows 和 macOS
"""

import sys
import json
import os
import subprocess
import threading
from pathlib import Path

# Windows 特殊处理
if sys.platform == 'win32':
    # 隐藏控制台窗口
    try:
        from ctypes import windll
        # 获取控制台窗口句柄并隐藏
        hwnd = windll.kernel32.GetConsoleWindow()
        if hwnd:
            windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE = 0
    except:
        pass
    
    # 高 DPI 支持
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except:
        try:
            windll.user32.SetProcessDPIAware()
        except:
            pass

# 检查 PyQt5
try:
    from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                                  QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                                  QComboBox, QTextEdit, QCheckBox, QGroupBox, 
                                  QMessageBox, QInputDialog)
    from PyQt5.QtCore import Qt, QThread, pyqtSignal
    HAS_PYQT = True
    
    # 高 DPI 支持 - 必须在创建 QApplication 之前设置
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
except ImportError:
    HAS_PYQT = False
    print("错误: 未安装 PyQt5")
    print("安装命令: pip3 install PyQt5")
    sys.exit(1)

APP_VERSION = "1.0"
APP_TITLE = f"ECH Workers 客户端 v{APP_VERSION}"

# 复用原有的 ConfigManager, ProcessManager, AutoStartManager
# 从原文件导入这些类（简化版本）
class ConfigManager:
    """配置管理器"""
    
    def __init__(self):
        # 跨平台配置文件路径
        if sys.platform == 'win32':
            # Windows: %APPDATA%\ECHWorkersClient
            self.config_dir = Path(os.getenv('APPDATA', Path.home())) / "ECHWorkersClient"
        else:
            # macOS/Linux: ~/Library/Application Support/ECHWorkersClient 或 ~/.config/ECHWorkersClient
            if sys.platform == 'darwin':
                self.config_dir = Path.home() / "Library" / "Application Support" / "ECHWorkersClient"
            else:
                self.config_dir = Path.home() / ".config" / "ECHWorkersClient"
        
        self.config_file = self.config_dir / "config.json"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.servers = []
        self.current_server_id = None
        
    def load_config(self):
        """加载配置"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.servers = data.get('servers', [])
                    self.current_server_id = data.get('current_server_id')
            except Exception as e:
                print(f"加载配置失败: {e}")
                self.servers = []
                self.current_server_id = None
        
        if not self.servers:
            self.add_default_server()
    
    def save_config(self):
        """保存配置"""
        try:
            data = {
                'servers': self.servers,
                'current_server_id': self.current_server_id
            }
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"保存配置失败: {e}")
    
    def add_default_server(self):
        """添加默认服务器"""
        import uuid
        default_server = {
            'id': str(uuid.uuid4()),
            'name': '默认服务器',
            'server': 'example.com:443',
            'listen': '127.0.0.1:30000',
            'token': '',
            'ip': 'saas.sin.fan',
            'dns': 'dns.alidns.com/dns-query',
            'ech': 'cloudflare-ech.com'
        }
        self.servers.append(default_server)
        self.current_server_id = default_server['id']
        self.save_config()
    
    def get_current_server(self):
        """获取当前服务器配置"""
        if self.current_server_id:
            for server in self.servers:
                if server['id'] == self.current_server_id:
                    return server
        return self.servers[0] if self.servers else None
    
    def update_server(self, server_data):
        """更新服务器配置"""
        for i, server in enumerate(self.servers):
            if server['id'] == server_data['id']:
                self.servers[i] = server_data
                break
    
    def add_server(self, server_data):
        """添加服务器"""
        import uuid
        if 'id' not in server_data:
            server_data['id'] = str(uuid.uuid4())
        self.servers.append(server_data)
        self.current_server_id = server_data['id']
    
    def delete_server(self, server_id):
        """删除服务器"""
        self.servers = [s for s in self.servers if s['id'] != server_id]
        if self.current_server_id == server_id:
            self.current_server_id = self.servers[0]['id'] if self.servers else None


class ProcessThread(QThread):
    """进程线程"""
    log_output = pyqtSignal(str)
    process_finished = pyqtSignal()
    
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.process = None
        self.is_running = False
    
    def run(self):
        """运行进程"""
        exe_path = self._find_executable()
        if not exe_path:
            script_dir = Path(__file__).parent.absolute()
            self.log_output.emit("错误: 找不到 ech-workers 可执行文件!\n")
            self.log_output.emit(f"请确保 ech-workers 可执行文件在以下位置之一:\n")
            self.log_output.emit(f"  - {script_dir}/ech-workers\n")
            self.log_output.emit(f"  - {script_dir}/ech-workers.exe\n")
            self.log_output.emit(f"  - {Path.cwd()}/ech-workers\n")
            self.log_output.emit(f"  - 或者在系统 PATH 中\n")
            self.log_output.emit(f"\n注意: ech-workers 必须是编译后的可执行文件，不是源文件。\n")
            self.process_finished.emit()
            return
        
        cmd = [exe_path]
        if self.config.get('server'):
            cmd.extend(['-f', self.config['server']])
        if self.config.get('listen'):
            cmd.extend(['-l', self.config['listen']])
        if self.config.get('token'):
            cmd.extend(['-token', self.config['token']])
        if self.config.get('ip'):
            cmd.extend(['-ip', self.config['ip']])
        if self.config.get('dns') and self.config['dns'] != 'dns.alidns.com/dns-query':
            cmd.extend(['-dns', self.config['dns']])
        if self.config.get('ech') and self.config['ech'] != 'cloudflare-ech.com':
            cmd.extend(['-ech', self.config['ech']])
        
        try:
            # Windows 上需要指定 UTF-8 编码，因为 Go 程序输出 UTF-8
            # 同时隐藏子进程的控制台窗口
            popen_kwargs = {
                'stdout': subprocess.PIPE,
                'stderr': subprocess.STDOUT,
                'bufsize': 1
            }
            
            # Windows: 使用 CREATE_NO_WINDOW 隐藏控制台
            if sys.platform == 'win32':
                CREATE_NO_WINDOW = 0x08000000
                popen_kwargs['creationflags'] = CREATE_NO_WINDOW
            
            self.process = subprocess.Popen(cmd, **popen_kwargs)
            self.is_running = True
            
            # 使用 UTF-8 解码，忽略无法解码的字符
            while self.is_running:
                line = self.process.stdout.readline()
                if not line:
                    break
                try:
                    # 尝试 UTF-8 解码
                    decoded_line = line.decode('utf-8', errors='replace')
                except:
                    # 如果失败，尝试系统默认编码
                    try:
                        decoded_line = line.decode(errors='replace')
                    except:
                        decoded_line = str(line)
                if decoded_line:
                    self.log_output.emit(decoded_line)
            
            self.process.wait()
            self.is_running = False
            self.process_finished.emit()
        except Exception as e:
            self.log_output.emit(f"错误: 启动失败 - {str(e)}\n")
            self.process_finished.emit()
    
    def stop(self):
        """停止进程"""
        self.is_running = False
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=3)
            except:
                self.process.kill()
    
    def _find_executable(self):
        """查找可执行文件（跨平台）"""
        # 脚本所在目录
        script_dir = Path(__file__).parent.absolute()
        # 当前工作目录
        current_dir = Path.cwd()
        
        # Windows 和 Unix 的可执行文件扩展名
        exe_ext = '.exe' if sys.platform == 'win32' else ''
        
        # 可能的可执行文件路径（按优先级）
        possible_paths = [
            script_dir / f'ech-workers{exe_ext}',
            current_dir / f'ech-workers{exe_ext}',
            # Windows 特定路径
            script_dir / 'ech-workers.exe' if sys.platform == 'win32' else None,
            current_dir / 'ech-workers.exe' if sys.platform == 'win32' else None,
            # Unix 路径（无扩展名）
            script_dir / 'ech-workers' if sys.platform != 'win32' else None,
            current_dir / 'ech-workers' if sys.platform != 'win32' else None,
        ]
        
        # 过滤掉 None 值
        possible_paths = [p for p in possible_paths if p is not None]
        
        for path in possible_paths:
            if path.exists():
                # Windows: 检查文件是否存在即可（.exe 文件）
                # Unix: 检查文件权限
                if sys.platform == 'win32':
                    # Windows 上，.exe 文件可以直接运行
                    if path.suffix.lower() == '.exe':
                        return str(path)
                    # 或者检查文件是否可执行
                    try:
                        with open(path, 'rb') as f:
                            header = f.read(2)
                            # PE 文件头
                            if header == b'MZ':
                                return str(path)
                    except:
                        pass
                else:
                    # Unix/Linux/macOS: 检查执行权限
                    if os.access(path, os.X_OK):
                        return str(path)
                    # 或者检查是否是二进制文件
                    try:
                        with open(path, 'rb') as f:
                            header = f.read(4)
                            # ELF 或 Mach-O
                            if (header.startswith(b'\x7fELF') or 
                                header.startswith(b'\xfe\xed\xfa') or
                                header.startswith(b'#!')):
                                # 尝试添加执行权限
                                try:
                                    os.chmod(path, 0o755)
                                except:
                                    pass
                                return str(path)
                    except:
                        pass
        
        # 尝试从 PATH 中查找
        import shutil
        exe = shutil.which('ech-workers')
        if exe:
            return exe
        
        # 如果都找不到，返回 None
        return None


class MainWindow(QMainWindow):
    """主窗口"""
    
    def __init__(self):
        super().__init__()
        self.config_manager = ConfigManager()
        self.config_manager.load_config()
        self.process_thread = None
        self.is_autostart = '-autostart' in sys.argv
        
        self.init_ui()
        self.init_server_combo()  # 初始化下拉框
        self.load_server_config()
        
        if self.is_autostart:
            self.hide()
            QApplication.processEvents()
            self.auto_start()
    
    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle(APP_TITLE)
        self.setGeometry(100, 100, 900, 750)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # 服务器管理
        server_group = QGroupBox("服务器管理")
        server_layout = QHBoxLayout()
        server_layout.addWidget(QLabel("选择服务器:"))
        self.server_combo = QComboBox()
        self.server_combo.currentIndexChanged.connect(self.on_server_changed)
        server_layout.addWidget(self.server_combo)
        server_layout.addWidget(QPushButton("新增", clicked=self.add_server))
        server_layout.addWidget(QPushButton("保存", clicked=self.save_server))
        server_layout.addWidget(QPushButton("重命名", clicked=self.rename_server))
        server_layout.addWidget(QPushButton("删除", clicked=self.delete_server))
        server_group.setLayout(server_layout)
        layout.addWidget(server_group)
        
        # 核心配置
        core_group = QGroupBox("核心配置")
        core_layout = QVBoxLayout()
        self.server_edit = QLineEdit()
        core_layout.addWidget(self.create_label_edit("服务地址:", self.server_edit))
        self.listen_edit = QLineEdit()
        core_layout.addWidget(self.create_label_edit("监听地址:", self.listen_edit))
        core_group.setLayout(core_layout)
        layout.addWidget(core_group)
        
        # 高级选项
        advanced_group = QGroupBox("高级选项 (可选)")
        advanced_layout = QVBoxLayout()
        self.token_edit = QLineEdit()
        advanced_layout.addWidget(self.create_label_edit("身份令牌:", self.token_edit))
        row1 = QHBoxLayout()
        self.ip_edit = QLineEdit()
        row1.addWidget(self.create_label_edit("优选IP或域名:", self.ip_edit))
        self.dns_edit = QLineEdit()
        row1.addWidget(self.create_label_edit("DOH服务器:", self.dns_edit))
        advanced_layout.addLayout(row1)
        self.ech_edit = QLineEdit()
        advanced_layout.addWidget(self.create_label_edit("ECH域名:", self.ech_edit))
        advanced_group.setLayout(advanced_layout)
        layout.addWidget(advanced_group)
        
        # 控制按钮
        control_group = QGroupBox("控制")
        control_layout = QHBoxLayout()
        self.start_btn = QPushButton("启动代理")
        self.start_btn.clicked.connect(self.start_process)
        self.stop_btn = QPushButton("停止")
        self.stop_btn.clicked.connect(self.stop_process)
        self.stop_btn.setEnabled(False)
        self.proxy_btn = QPushButton("设置系统代理")
        self.proxy_btn.clicked.connect(self.toggle_system_proxy)
        self.proxy_btn.setEnabled(False)  # 只有启动后才能设置
        self.auto_start_check = QCheckBox("开机启动")
        self.auto_start_check.stateChanged.connect(self.on_auto_start_changed)
        control_layout.addWidget(self.start_btn)
        control_layout.addWidget(self.stop_btn)
        control_layout.addWidget(self.proxy_btn)
        control_layout.addWidget(self.auto_start_check)
        control_layout.addStretch()
        control_layout.addWidget(QPushButton("清空日志", clicked=self.clear_log))
        control_group.setLayout(control_layout)
        layout.addWidget(control_group)
        
        # 系统代理状态
        self.system_proxy_enabled = False
        
        # 日志
        log_group = QGroupBox("运行日志")
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QApplication.font())
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
    
    def create_label_edit(self, label_text, edit_widget):
        """创建标签和输入框"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.addWidget(QLabel(label_text))
        layout.addWidget(edit_widget)
        return widget
    
    def init_server_combo(self):
        """初始化服务器下拉框（首次加载）"""
        # 暂时断开信号，避免触发 on_server_changed
        try:
            self.server_combo.currentIndexChanged.disconnect()
        except:
            pass
        
        self.server_combo.clear()
        sorted_servers = sorted(self.config_manager.servers, key=lambda x: x['name'])
        for server in sorted_servers:
            self.server_combo.addItem(server['name'], server['id'])
        
        # 选中当前服务器
        current = self.config_manager.get_current_server()
        if current:
            for i in range(self.server_combo.count()):
                if self.server_combo.itemData(i) == current['id']:
                    self.server_combo.setCurrentIndex(i)
                    break
        
        # 重新连接信号
        self.server_combo.currentIndexChanged.connect(self.on_server_changed)
    
    def load_server_config(self):
        """加载服务器配置"""
        # 只更新界面，不刷新 combo（避免递归）
        server = self.config_manager.get_current_server()
        if server:
            self.server_edit.setText(server.get('server', ''))
            self.listen_edit.setText(server.get('listen', ''))
            self.token_edit.setText(server.get('token', ''))
            self.ip_edit.setText(server.get('ip', ''))
            self.dns_edit.setText(server.get('dns', ''))
            self.ech_edit.setText(server.get('ech', ''))
    
    def refresh_server_combo(self):
        """刷新服务器下拉框"""
        # 暂时断开信号连接，避免递归
        self.server_combo.currentIndexChanged.disconnect()
        self.server_combo.clear()
        sorted_servers = sorted(self.config_manager.servers, key=lambda x: x['name'])
        for server in sorted_servers:
            self.server_combo.addItem(server['name'], server['id'])
        
        current = self.config_manager.get_current_server()
        if current:
            for i in range(self.server_combo.count()):
                if self.server_combo.itemData(i) == current['id']:
                    self.server_combo.setCurrentIndex(i)
                    break
        
        # 重新连接信号
        self.server_combo.currentIndexChanged.connect(self.on_server_changed)
    
    def get_control_values(self):
        """获取界面输入值"""
        server = self.config_manager.get_current_server()
        if server:
            server = server.copy()
            server['server'] = self.server_edit.text()
            server['listen'] = self.listen_edit.text()
            server['token'] = self.token_edit.text()
            server['ip'] = self.ip_edit.text()
            server['dns'] = self.dns_edit.text()
            server['ech'] = self.ech_edit.text()
        return server
    
    def on_server_changed(self):
        """服务器选择改变"""
        if self.process_thread and self.process_thread.is_running:
            # 暂时断开信号，恢复选择
            self.server_combo.currentIndexChanged.disconnect()
            current = self.config_manager.get_current_server()
            if current:
                for i in range(self.server_combo.count()):
                    if self.server_combo.itemData(i) == current['id']:
                        self.server_combo.setCurrentIndex(i)
                        break
            self.server_combo.currentIndexChanged.connect(self.on_server_changed)
            QMessageBox.warning(self, "提示", "请先停止当前连接后再切换服务器")
            return
        
        index = self.server_combo.currentIndex()
        if index >= 0:
            server_id = self.server_combo.itemData(index)
            if server_id and server_id != self.config_manager.current_server_id:
                self.config_manager.current_server_id = server_id
                # 暂时断开信号，避免递归
                self.server_combo.currentIndexChanged.disconnect()
                self.load_server_config()
                self.server_combo.currentIndexChanged.connect(self.on_server_changed)
                self.config_manager.save_config()
    
    def add_server(self):
        """添加服务器"""
        name, ok = QInputDialog.getText(self, "新增服务器", "请输入服务器名称:", text="新服务器")
        if ok and name.strip():
            name = name.strip()
            if any(s['name'] == name for s in self.config_manager.servers):
                QMessageBox.warning(self, "提示", "服务器名称已存在")
                return
            
            current = self.get_control_values()
            new_server = current.copy() if current else {}
            self.config_manager.add_server(new_server)
            new_server['name'] = name
            self.config_manager.update_server(new_server)
            self.config_manager.save_config()
            self.refresh_server_combo()
            self.load_server_config()
            self.append_log(f"[系统] 已添加新服务器: {name}\n")
    
    def save_server(self):
        """保存服务器配置"""
        server = self.get_control_values()
        if server:
            self.config_manager.update_server(server)
            self.config_manager.save_config()
            self.append_log(f"[系统] 服务器 \"{server['name']}\" 配置已保存\n")
    
    def delete_server(self):
        """删除服务器"""
        if len(self.config_manager.servers) <= 1:
            QMessageBox.warning(self, "提示", "至少需要保留一个服务器配置")
            return
        
        server = self.config_manager.get_current_server()
        if server:
            reply = QMessageBox.question(self, "确认删除", f"确定要删除服务器 \"{server['name']}\" 吗？",
                                       QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                name = server['name']
                self.config_manager.delete_server(server['id'])
                self.config_manager.save_config()
                self.refresh_server_combo()
                self.load_server_config()
                self.append_log(f"[系统] 已删除服务器: {name}\n")
    
    def rename_server(self):
        """重命名服务器"""
        server = self.config_manager.get_current_server()
        if server:
            new_name, ok = QInputDialog.getText(self, "重命名服务器", "请输入新的服务器名称:", text=server['name'])
            if ok and new_name.strip():
                new_name = new_name.strip()
                if any(s['name'] == new_name and s['id'] != server['id'] for s in self.config_manager.servers):
                    QMessageBox.warning(self, "提示", "服务器名称已存在")
                    return
                
                old_name = server['name']
                server['name'] = new_name
                self.config_manager.update_server(server)
                self.config_manager.save_config()
                self.refresh_server_combo()
                self.append_log(f"[系统] 服务器已重命名: {old_name} -> {new_name}\n")
    
    def start_process(self):
        """启动进程"""
        server = self.get_control_values()
        
        if not server.get('server'):
            QMessageBox.warning(self, "提示", "请输入服务地址")
            return
        
        if not server.get('listen'):
            QMessageBox.warning(self, "提示", "请输入监听地址")
            return
        
        self.config_manager.update_server(server)
        self.config_manager.save_config()
        
        self.process_thread = ProcessThread(server)
        self.process_thread.log_output.connect(self.append_log)
        self.process_thread.process_finished.connect(self.on_process_finished)
        self.process_thread.start()
        
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.proxy_btn.setEnabled(True)  # 启动后可以设置系统代理
        self.server_edit.setEnabled(False)
        self.listen_edit.setEnabled(False)
        self.server_combo.setEnabled(False)
        self.append_log(f"[系统] 已启动服务器: {server['name']}\n")
    
    def stop_process(self):
        """停止进程"""
        if self.process_thread:
            self.process_thread.stop()
            self.process_thread.wait()
        self.on_process_finished()
    
    def on_process_finished(self):
        """进程结束"""
        # 停止时自动清理系统代理
        if self.system_proxy_enabled:
            self._set_system_proxy(False)
            self.system_proxy_enabled = False
            self.proxy_btn.setText("设置系统代理")
            self.append_log("[系统] 已自动清理系统代理\n")
        
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.proxy_btn.setEnabled(False)  # 停止后禁用系统代理按钮
        self.server_edit.setEnabled(True)
        self.listen_edit.setEnabled(True)
        self.server_combo.setEnabled(True)
        self.append_log("[系统] 进程已停止。\n")
    
    def on_auto_start_changed(self):
        """开机启动改变"""
        enabled = self.auto_start_check.isChecked()
        if self._set_auto_start(enabled):
            self.append_log(f"[系统] {'已设置' if enabled else '已取消'}开机启动\n")
        else:
            self.auto_start_check.setChecked(not enabled)
            QMessageBox.warning(self, "错误", "设置开机启动失败")
    
    def _set_auto_start(self, enabled):
        """设置开机启动（跨平台）"""
        try:
            if sys.platform == 'win32':
                # Windows: 使用注册表
                import winreg
                key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
                app_name = "ECHWorkersClient"
                
                if enabled:
                    # 获取当前脚本路径
                    script_path = Path(__file__).absolute()
                    python_path = sys.executable
                    # 创建启动命令
                    cmd = f'"{python_path}" "{script_path}"'
                    
                    try:
                        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
                        winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
                        winreg.CloseKey(key)
                        return True
                    except Exception as e:
                        print(f"设置开机启动失败: {e}")
                        return False
                else:
                    try:
                        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
                        winreg.DeleteValue(key, app_name)
                        winreg.CloseKey(key)
                        return True
                    except FileNotFoundError:
                        # 如果值不存在，也算成功
                        return True
                    except Exception as e:
                        print(f"删除开机启动失败: {e}")
                        return False
            else:
                # macOS/Linux: 使用 LaunchAgents 或 systemd
                if sys.platform == 'darwin':
                    # macOS
                    plist_path = Path.home() / "Library" / "LaunchAgents" / "com.echworkers.client.plist"
                    if enabled:
                        script_path = Path(__file__).absolute()
                        python_path = sys.executable
                        plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.echworkers.client</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>{script_path}</string>
        <string>-autostart</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>"""
                        try:
                            plist_path.parent.mkdir(parents=True, exist_ok=True)
                            with open(plist_path, 'w') as f:
                                f.write(plist_content)
                            return True
                        except Exception as e:
                            print(f"创建启动项失败: {e}")
                            return False
                    else:
                        try:
                            if plist_path.exists():
                                plist_path.unlink()
                            return True
                        except Exception as e:
                            print(f"删除启动项失败: {e}")
                            return False
                else:
                    # Linux: 使用 systemd user service（简化实现）
                    return False  # Linux 暂不支持
        except Exception as e:
            print(f"设置开机启动失败: {e}")
            return False
    
    def _is_auto_start_enabled(self):
        """检查是否已启用开机启动"""
        try:
            if sys.platform == 'win32':
                import winreg
                key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
                app_name = "ECHWorkersClient"
                try:
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
                    winreg.QueryValueEx(key, app_name)
                    winreg.CloseKey(key)
                    return True
                except FileNotFoundError:
                    return False
            elif sys.platform == 'darwin':
                plist_path = Path.home() / "Library" / "LaunchAgents" / "com.echworkers.client.plist"
                return plist_path.exists()
            else:
                return False
        except:
            return False
    
    def clear_log(self):
        """清空日志"""
        self.log_text.clear()
    
    def append_log(self, text):
        """追加日志"""
        self.log_text.append(text)
        # 限制日志长度
        if self.log_text.document().blockCount() > 1000:
            cursor = self.log_text.textCursor()
            cursor.movePosition(cursor.Start)
            cursor.movePosition(cursor.Down, cursor.MoveAnchor, 100)
            cursor.movePosition(cursor.Start, cursor.KeepAnchor)
            cursor.removeSelectedText()
    
    def update_auto_start_checkbox(self):
        """更新开机启动复选框状态"""
        self.auto_start_check.setChecked(self._is_auto_start_enabled())
    
    def toggle_system_proxy(self):
        """切换系统代理"""
        if self.system_proxy_enabled:
            # 关闭系统代理
            if self._set_system_proxy(False):
                self.system_proxy_enabled = False
                self.proxy_btn.setText("设置系统代理")
                self.append_log("[系统] 已关闭系统代理\n")
            else:
                QMessageBox.warning(self, "错误", "关闭系统代理失败")
        else:
            # 开启系统代理
            if self._set_system_proxy(True):
                self.system_proxy_enabled = True
                self.proxy_btn.setText("关闭系统代理")
                self.append_log("[系统] 已设置系统代理\n")
            else:
                QMessageBox.warning(self, "错误", "设置系统代理失败")
    
    def _set_system_proxy(self, enabled):
        """设置系统代理（跨平台）"""
        try:
            # 获取当前监听地址
            listen = self.listen_edit.text()
            if not listen and enabled:
                return False
            
            if sys.platform == 'win32':
                return self._set_windows_proxy(enabled, listen)
            elif sys.platform == 'darwin':
                return self._set_macos_proxy(enabled, listen)
            else:
                self.append_log("[系统] Linux 暂不支持自动设置系统代理\n")
                return False
        except Exception as e:
            self.append_log(f"[系统] 设置系统代理失败: {e}\n")
            return False
    
    def _set_windows_proxy(self, enabled, listen):
        """设置 Windows 系统代理"""
        try:
            import winreg
            
            # Internet Settings 注册表路径
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
            
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            
            if enabled:
                # 设置代理服务器地址 (SOCKS5 代理需要使用 socks=地址)
                # Windows IE/Edge 不直接支持 SOCKS5，这里设置为 HTTP 代理格式
                # 用户可能需要使用支持 SOCKS5 的浏览器或工具
                proxy_server = f"socks={listen}"
                winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, proxy_server)
                winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
                # 设置不使用代理的地址
                winreg.SetValueEx(key, "ProxyOverride", 0, winreg.REG_SZ, "localhost;127.*;10.*;172.16.*;172.17.*;172.18.*;172.19.*;172.20.*;172.21.*;172.22.*;172.23.*;172.24.*;172.25.*;172.26.*;172.27.*;172.28.*;172.29.*;172.30.*;172.31.*;192.168.*;<local>")
            else:
                # 关闭代理
                winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
            
            winreg.CloseKey(key)
            
            # 通知系统代理设置已更改
            try:
                from ctypes import windll
                INTERNET_OPTION_SETTINGS_CHANGED = 39
                INTERNET_OPTION_REFRESH = 37
                windll.wininet.InternetSetOptionW(0, INTERNET_OPTION_SETTINGS_CHANGED, 0, 0)
                windll.wininet.InternetSetOptionW(0, INTERNET_OPTION_REFRESH, 0, 0)
            except:
                pass
            
            return True
        except Exception as e:
            self.append_log(f"[系统] Windows 代理设置失败: {e}\n")
            return False
    
    def _set_macos_proxy(self, enabled, listen):
        """设置 macOS 系统代理"""
        try:
            # 解析监听地址
            if ':' in listen:
                host, port = listen.rsplit(':', 1)
            else:
                host, port = '127.0.0.1', listen
            
            # 获取当前网络服务名称
            result = subprocess.run(
                ['networksetup', '-listallnetworkservices'],
                capture_output=True, text=True
            )
            
            # 解析网络服务列表（跳过第一行说明）
            services = [line.strip() for line in result.stdout.strip().split('\n')[1:] 
                       if line.strip() and not line.startswith('*')]
            
            for service in services:
                try:
                    if enabled:
                        # 设置 SOCKS 代理
                        subprocess.run(
                            ['networksetup', '-setsocksfirewallproxy', service, host, port],
                            capture_output=True, check=True
                        )
                        subprocess.run(
                            ['networksetup', '-setsocksfirewallproxystate', service, 'on'],
                            capture_output=True, check=True
                        )
                    else:
                        # 关闭 SOCKS 代理
                        subprocess.run(
                            ['networksetup', '-setsocksfirewallproxystate', service, 'off'],
                            capture_output=True, check=True
                        )
                except subprocess.CalledProcessError:
                    # 某些网络服务可能不支持代理设置，忽略错误
                    pass
            
            return True
        except Exception as e:
            self.append_log(f"[系统] macOS 代理设置失败: {e}\n")
            return False
    
    def closeEvent(self, event):
        """窗口关闭事件"""
        # 关闭前清理系统代理
        if self.system_proxy_enabled:
            self._set_system_proxy(False)
            self.append_log("[系统] 程序关闭，已清理系统代理\n")
        
        # 停止进程
        if self.process_thread and self.process_thread.is_running:
            self.process_thread.stop()
            self.process_thread.wait()
        
        event.accept()
    
    def auto_start(self):
        """自动启动"""
        if not (self.process_thread and self.process_thread.is_running):
            server = self.get_control_values()
            if server and server.get('server') and server.get('listen'):
                self.start_process()
                self.append_log("[系统] 开机自动启动代理\n")


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
