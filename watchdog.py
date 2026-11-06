# -*- coding: utf-8 -*-
"""自动交付守卫(Python版, 无编码问题): 监控迭代跑满后执行最终分析"""
import os
import sys
import time
import json
import subprocess

PROG = r'C:\Users\LZY20\Desktop\量化回测\iteration\progress.json'
QUANT_DIR = r'C:\Users\LZY20\Desktop\harness\quant'

print('[watchdog] 开始监控迭代进度...', flush=True)
while True:
    time.sleep(20)
    try:
        with open(PROG, encoding='utf-8') as f:
            p = json.load(f)
        if p.get('elapsed_sec', 0) >= p.get('total_sec', 0):
            break
    except Exception:
        continue

print('[watchdog] 迭代已跑满, 等 10 秒让最终文件落盘...', flush=True)
time.sleep(10)
print('[watchdog] 执行最终分析...', flush=True)
r = subprocess.run([sys.executable, 'final_analysis.py'], cwd=QUANT_DIR,
                   capture_output=True, text=True, encoding='utf-8')
out = r.stdout + r.stderr
with open(r'C:\Users\LZY20\Desktop\量化回测\iteration\交付报告.txt', 'w', encoding='utf-8') as f:
    f.write(out)
print('[watchdog] 交付报告已生成: 桌面\\量化回测\\iteration\\交付报告.txt', flush=True)
