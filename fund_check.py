# -*- coding: utf-8 -*-
"""批量查看基金重仓股信号"""
import sys
sys.path.insert(0, r'C:\Users\LZY20\Desktop\harness\quant')
from daily_signal import signal_run

stocks = [('688017', '绿的谐波'), ('002472', '双环传动'), ('300024', '机器人'),
          ('688169', '石头科技'), ('603486', '科沃斯'), ('300124', '汇川技术')]

print('代码      名称      信号              现价      趋势   量比    止损参考')
print('-' * 78)
for code, name in stocks:
    try:
        r = signal_run(code)
        sig = r['signal'].replace('(空仓等信号)', '').strip()
        vol = r['vol_ratio'] if r['vol_ratio'] is not None else 0
        stop = r['stop_ref'] if r['stop_ref'] else '-'
        print(f'{code:<8} {name:<6} {sig:<16} {r["price"]:<8} {r["trend"]:<4} {vol:<6} {stop}')
    except Exception as e:
        print(f'{code:<8} {name:<6} 查询失败: {str(e)[:50]}')
