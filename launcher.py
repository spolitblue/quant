# -*- coding: utf-8 -*-
"""
操作台启动器: 启动 Flask 服务(独立窗口) + 自动打开浏览器
双击 桌面\启动量化操作台.bat 即调用本脚本
"""
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import time
import subprocess
import webbrowser
import urllib.request

QUANT = r'C:\Users\LZY20\Desktop\harness\quant'
URL = 'http://127.0.0.1:8321'


def service_up():
    try:
        urllib.request.urlopen(URL, timeout=2)
        return True
    except Exception:
        return False


def main():
    if service_up():
        print('操作台已在运行, 直接打开浏览器...')
    else:
        print('正在启动操作台服务(独立窗口)...')
        subprocess.Popen([sys.executable, 'app.py'], cwd=QUANT,
                         creationflags=subprocess.CREATE_NEW_CONSOLE)
        for _ in range(30):
            time.sleep(1)
            if service_up():
                break
        if not service_up():
            print('警告: 服务启动较慢, 请稍等后手动刷新浏览器')
    webbrowser.open(URL)
    print('已打开: http://127.0.0.1:8321')
    print('提示: 关掉「量化操作台服务」黑窗口 = 关闭系统')


if __name__ == '__main__':
    main()
