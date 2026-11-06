# -*- coding: utf-8 -*-
"""
每日信号模块 — 用训练好的规则对最新行情算买卖信号
====================================================
用法:  python signal.py [股票代码] [快线] [慢线] [止损] [量过滤]
不传参数则自动读取 迭代系统 最新训练出的最优规则
(闭卷迭代跑完后, 自动使用闭卷考试及格的那套规则)

输出: 控制台 + 桌面\量化回测\每日信号_YYYYMMDD.txt
"""
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import os
import json
import datetime

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest import fetch

OUTDIR = r'C:\Users\LZY20\Desktop\量化回测'
SYMBOL = '601108'


def load_rule():
    """优先命令行参数, 其次读迭代系统最新最优规则, 最后用默认值"""
    if len(sys.argv) >= 6:
        return {'fast': int(sys.argv[2]), 'slow': int(sys.argv[3]),
                'stop_loss': float(sys.argv[4]), 'volume_filter': float(sys.argv[5])}
    fr = os.path.join(OUTDIR, 'iteration', 'final_report.txt')
    if os.path.exists(fr):
        try:
            with open(fr, encoding='utf-8') as f:
                d = json.load(f)
            b = d.get('best')
            if b:
                return {'fast': int(b['fast']), 'slow': int(b['slow']),
                        'stop_loss': float(b.get('stop_loss') or 0),
                        'volume_filter': float(b.get('volume_filter') or 0)}
        except Exception:
            pass
    # 兜底: 闭卷冒烟测出的稳健规则
    return {'fast': 14, 'slow': 23, 'stop_loss': 0.079, 'volume_filter': 0.0}


def signal_run(symbol=None, rule=None):
    """计算最新信号, 返回结构化结果"""
    symbol = symbol or SYMBOL
    rule = rule or load_rule()
    fast = int(rule['fast'])
    slow = int(rule['slow'])
    stop_loss = float(rule.get('stop_loss') or 0)
    vol_f = float(rule.get('volume_filter') or 0)

    df = fetch(symbol, '20221001', '20270101')
    d = df.copy()
    d['ma_f'] = d['close'].rolling(fast).mean()
    d['ma_s'] = d['close'].rolling(slow).mean()
    d['vol_ma'] = d['volume'].rolling(20).mean()

    last = d.iloc[-1]
    prev = d.iloc[-2]
    price = float(last['close'])
    maf = float(last['ma_f'])
    mas = float(last['ma_s'])
    vol = float(last['volume'])
    vol_ma = float(last['vol_ma'])

    golden = (prev['ma_f'] <= prev['ma_s']) and (maf > mas)   # 今日金叉
    death = (prev['ma_f'] >= prev['ma_s']) and (maf < mas)    # 今日死叉
    above = maf > mas
    vol_ok = vol_f == 0 or vol > vol_ma * vol_f

    if golden and vol_ok:
        sig = '📈 买入信号'
        why = f'快线MA{fast}今日上穿慢线MA{slow}(金叉)'
        if vol_f:
            why += f', 成交量达20日均量{vol_f:.1f}倍(放量确认)'
    elif death:
        sig = '📉 卖出信号'
        why = f'快线MA{fast}今日下穿慢线MA{slow}(死叉)'
    elif above:
        sig = '📊 持有/观望'
        why = '快线仍在慢线上方, 上升趋势未破坏'
    else:
        sig = '⏸️ 观望(空仓等信号)'
        why = '快线在慢线下方, 下跌趋势不进场'

    # 止损参考价(若已持仓): 近20日最高价 × (1-止损比例)
    stop_ref = None
    if stop_loss > 0:
        hi20 = d['high'].tail(20).max()
        stop_ref = float(hi20 * (1 - stop_loss))

    return {
        'symbol': symbol,
        'date': str(last.name.date()),
        'price': round(price, 2),
        'ma_fast': round(maf, 2),
        'ma_slow': round(mas, 2),
        'signal': sig,
        'reason': why,
        'rule': {'fast': fast, 'slow': slow, 'stop_loss': stop_loss, 'volume_filter': vol_f},
        'stop_ref': round(stop_ref, 2) if stop_ref else None,
        'trend': '上升' if above else '下降',
        'vol_ratio': round(vol / vol_ma, 2) if vol_ma > 0 else None,
    }


def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else SYMBOL
    r = signal_run(symbol)
    lines = [
        '=' * 46,
        f'  每日信号 · {r["symbol"]} · {r["date"]}',
        '=' * 46,
        f'  信号: {r["signal"]}',
        f'  理由: {r["reason"]}',
        '-' * 46,
        f'  现价: {r["price"]}   趋势: {r["trend"]}',
        f'  快线MA{r["rule"]["fast"]}: {r["ma_fast"]}   慢线MA{r["rule"]["slow"]}: {r["ma_slow"]}',
    ]
    if r['vol_ratio']:
        lines.append(f'  今日量/20日均量: {r["vol_ratio"]}倍')
    if r['stop_ref']:
        lines.append(f'  止损参考价(近20日高点-{r["rule"]["stop_loss"]*100:.0f}%): {r["stop_ref"]}')
    lines.append(f'  规则来源: 快线{r["rule"]["fast"]}/慢线{r["rule"]["slow"]}/'
                 f'止损{r["rule"]["stop_loss"] or 0}/量过滤{r["rule"]["volume_filter"] or 0}')
    lines.append('=' * 46)
    lines.append('⚠️ 虚拟信号仅供学习参考, 不构成投资建议')
    text = '\n'.join(lines)
    print(text)

    out = os.path.join(OUTDIR, f'每日信号_{r["date"]}.txt')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(text)
    print(f'\n已保存: {out}')


if __name__ == '__main__':
    main()
