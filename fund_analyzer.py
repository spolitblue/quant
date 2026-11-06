# -*- coding: utf-8 -*-
"""
基金专析系统 — 020982 华安机器人ETF联接C 专属分析
==================================================
功能:
  1. 基金基本信息(名称/规模/经理/成立)
  2. 净值走势 + 近5日涨跌
  3. 重仓股扫描: 每只重仓股的技术信号/趋势/止损线
  4. 健康度评分: 趋势分 + 止损分
  5. 企稳信号检查: 加仓窗口判断(趋势/止损/大盘三关)
用法: python fund_analyzer.py [基金代码]
"""
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import os
import json

import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from daily_signal import signal_run
from backtest import fetch

OUTDIR = r'C:\Users\LZY20\Desktop\量化回测'
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False


def get_fund_basic(symbol):
    import akshare as ak
    info = ak.fund_individual_basic_info_xq(symbol=symbol)
    d = dict(zip(info['item'], info['value']))
    return {
        '代码': symbol,
        '名称': d.get('基金名称', ''),
        '成立': str(d.get('成立时间', ''))[:10],
        '规模': d.get('最新规模', ''),
        '经理': d.get('基金经理', ''),
        '类型': d.get('基金类型', ''),
    }


def get_fund_nav(symbol):
    """净值走势(东财)"""
    import akshare as ak
    df = ak.fund_open_fund_info_em(symbol=symbol, indicator='单位净值走势')
    df = df.rename(columns={'净值日期': 'date', '单位净值': 'nav', '日增长率': 'chg'})
    df['date'] = pd.to_datetime(df['date'])
    df['nav'] = pd.to_numeric(df['nav'], errors='coerce')
    return df.dropna(subset=['nav'])


def get_holdings(symbol, top_n=10):
    """最新季度重仓股(东财), 按占净值比例降序取前十大
    注意: 必须显式传报告期 date, 否则接口只返回 2024 年旧数据"""
    import akshare as ak
    df = ak.fund_portfolio_hold_em(symbol=symbol, date='20263')
    df = df.sort_values(['季度', '占净值比例'], ascending=[True, False])
    df = df.drop_duplicates(subset=['股票代码'], keep='last')
    return df.head(top_n)


def analyze(symbol='020982'):
    """完整分析流程"""
    result = {'ok': False, 'symbol': symbol}
    basic = get_fund_basic(symbol)
    nav = get_fund_nav(symbol)
    holds = get_holdings(symbol)

    # 重仓股扫描
    rows = []
    for _, h in holds.iterrows():
        code = str(h['股票代码']).zfill(6)
        name = str(h['股票名称'])
        weight = float(h['占净值比例'])
        try:
            r = signal_run(code)
            above = r['stop_ref'] is None or r['price'] >= r['stop_ref']
            rows.append({
                'code': code, 'name': name, 'weight': round(weight, 2),
                'signal': r['signal'], 'trend': r['trend'],
                'price': r['price'], 'stop_ref': r['stop_ref'],
                'above_stop': bool(above), 'vol': r['vol_ratio'],
            })
        except Exception as e:
            rows.append({'code': code, 'name': name, 'weight': round(weight, 2), 'error': str(e)[:50]})

    ok_rows = [r for r in rows if 'error' not in r]
    up = sum(1 for r in ok_rows if r['trend'] == '上升')
    above = sum(1 for r in ok_rows if r['above_stop'])
    trend_score = round(up / len(ok_rows) * 100) if ok_rows else 0
    stop_score = round(above / len(ok_rows) * 100) if ok_rows else 0

    # 大盘
    mkt_ok = None
    try:
        mkt = signal_run('510300')
        mkt_ok = mkt['trend'] == '上升'
    except Exception:
        pass

    # 净值近5日
    nav5 = nav.tail(5)
    nav_chg = round((nav5['nav'].iloc[-1] / nav5['nav'].iloc[0] - 1) * 100, 2) if len(nav5) >= 2 else None

    # 企稳三关
    checks = [
        {'name': '重仓股趋势关(≥2/3上升)', 'pass': up >= max(2, len(ok_rows) * 2 // 3),
         'detail': f'{up}/{len(ok_rows)} 只上升'},
        {'name': '止损线关(≥半数站回)', 'pass': above >= max(2, len(ok_rows) // 2),
         'detail': f'{above}/{len(ok_rows)} 只站回止损线上方'},
        {'name': '大盘关(沪深300趋势向上)', 'pass': mkt_ok,
         'detail': '沪深300趋势向上' if mkt_ok else ('沪深300趋势向下' if mkt_ok is False else '未知')},
    ]
    pass_count = sum(1 for c in checks if c['pass'])
    if pass_count == 3:
        verdict = '✅ 企稳信号齐了, 可按计划分批加仓(仍建议分2批)'
    elif pass_count == 2:
        verdict = '🟡 接近企稳, 再观察1-2天, 别急'
    elif pass_count == 1:
        verdict = '🔴 仍在调整期, 观望为主, 不加仓'
    else:
        verdict = '⛔ 全线走弱, 警惕趋势破坏, 不加仓并考虑风控'

    # 净值图
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(nav['date'], nav['nav'], lw=1.4, color='#3d7eff')
    ax.set_title(f'{basic["名称"]} 净值走势')
    ax.grid(alpha=0.3)
    plt.tight_layout()
    chart = os.path.join(OUTDIR, f'基金净值_{symbol}.png')
    plt.savefig(chart, dpi=110)
    plt.close()

    result.update({
        'ok': True,
        'basic': basic,
        'nav_last': str(nav['date'].iloc[-1].date()),
        'nav_price': round(float(nav['nav'].iloc[-1]), 4),
        'nav_chg5': nav_chg,
        'holdings': rows,
        'trend_score': trend_score,
        'stop_score': stop_score,
        'checks': checks,
        'verdict': verdict,
        'chart': f'基金净值_{symbol}.png',
    })
    return result


def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else '020982'
    r = analyze(symbol)
    if not r['ok']:
        print('分析失败')
        return
    b = r['basic']
    print('=' * 56)
    print(f'  {b["名称"]} ({b["代码"]})')
    print(f'  成立 {b["成立"]} | 规模 {b["规模"]} | 经理 {b["经理"]}')
    print('=' * 56)
    print(f'  最新净值: {r["nav_price"]} ({r["nav_last"]})  近5日: {r["nav_chg5"]}%')
    print(f'  健康度: 趋势分 {r["trend_score"]} | 止损分 {r["stop_score"]}')
    print('-' * 56)
    print(f'  {"代码":<8}{"名称":<10}{"占比%":<7}{"趋势":<5}{"站回止损":<7}')
    for h in r['holdings']:
        if 'error' in h:
            print(f'  {h["code"]:<8}{h["name"]:<10}{h["weight"]:<7}查询失败')
        else:
            print(f'  {h["code"]:<8}{h["name"]:<10}{h["weight"]:<7}{h["trend"]:<5}{"✅" if h["above_stop"] else "❌"}')
    print('-' * 56)
    for c in r['checks']:
        print(f'  {"✅" if c["pass"] else "❌"} {c["name"]} ({c["detail"]})')
    print(f'\n  结论: {r["verdict"]}')
    print('=' * 56)
    print(f'  净值图: 桌面\\量化回测\\基金净值_{symbol}.png')


if __name__ == '__main__':
    main()
