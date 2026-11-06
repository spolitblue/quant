# -*- coding: utf-8 -*-
"""
AI 综合研判模块 — 技术信号 + 个股新闻 + 市场风口 → AI 决策
============================================================
用法:  python advisor.py [股票代码]
流程:
  1. 技术信号: 复用每日信号(训练规则)
  2. 个股新闻: 东方财富接口, 最近 8 条标题
  3. 市场风口: 行业/概念板块涨幅榜 Top8
  4. Ollama 综合研判: 输出 看多/看空/中性 + 置信度 + 理由 + 风险

输出: 控制台 + 桌面/量化回测/AI研判_日期.txt
⚠️ 仅供学习研究, 不构成投资建议
"""
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import os
import json
import time
import datetime

import pandas as pd
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from daily_signal import signal_run

OUTDIR = r'C:\Users\LZY20\Desktop\量化回测'
OLLAMA = 'http://127.0.0.1:11434/api/generate'


def fetch_retry(fn, retries=3, wait=3):
    """东财接口偶发断连, 自动重试"""
    last = None
    for i in range(retries):
        try:
            return fn()
        except Exception as e:
            last = e
            time.sleep(wait)
    raise last


def get_news(symbol):
    """个股新闻(标题+时间)"""
    import akshare as ak
    df = fetch_retry(lambda: ak.stock_news_em(symbol=symbol))
    rows = []
    for _, r in df.head(8).iterrows():
        rows.append({'time': str(r.get('发布时间', ''))[:16], 'title': str(r.get('新闻标题', ''))})
    return rows


def get_hot_sectors():
    """市场热点: 行业+概念涨幅榜 Top8"""
    import akshare as ak
    hot = []
    for fn in (ak.stock_board_industry_name_em, ak.stock_board_concept_name_em):
        try:
            df = fetch_retry(fn)
            df = df.sort_values('涨跌幅', ascending=False)
            for _, r in df.head(4).iterrows():
                hot.append({'name': str(r['板块名称']), 'pct': round(float(r['涨跌幅']), 2)})
        except Exception:
            continue
    return hot


def ai_judge(symbol, tech, news, sectors):
    """Ollama 综合研判"""
    news_txt = '\n'.join(f"- [{n['time']}] {n['title']}" for n in news) or '(无近期新闻)'
    sec_txt = '\n'.join(f"- {s['name']} {s['pct']:+.2f}%" for s in sectors) or '(无数据)'
    prompt = f"""你是资深投资研究员。请综合以下三方面信息, 对股票 {symbol} 做研判。

【技术信号】
信号: {tech['signal']}
理由: {tech['reason']}
现价: {tech['price']}  趋势: {tech['trend']}
快线MA{tech['rule']['fast']}: {tech['ma_fast']}  慢线MA{tech['rule']['slow']}: {tech['ma_slow']}

【近期新闻】
{news_txt}

【今日市场热点板块】
{sec_txt}

请综合研判(注意: 新闻与热点只是背景信息, 不能凭空制造利好; 技术信号为主)。
只输出 JSON 对象:
{{"verdict": "看多/看空/中性", "confidence": 0到100的整数, "summary": "一句话结论", "reasons": ["理由1", "理由2"], "risks": ["风险1", "风险2"]}}"""
    r = requests.post(OLLAMA, json={
        'model': 'qwen2.5:7b', 'prompt': prompt, 'stream': False,
        'format': 'json', 'options': {'temperature': 0.4}},
        timeout=600)
    txt = r.json()['response']
    start, end = txt.find('{'), txt.rfind('}')
    return json.loads(txt[start:end + 1]) if start >= 0 else {'verdict': '中性', 'confidence': 0, 'summary': txt[:100]}


def advisor_run(symbol=None):
    """完整研判流程, 返回结构化结果"""
    symbol = symbol or '601108'
    print(f'[研判] {symbol} 正在收集信息...')
    tech = signal_run(symbol)
    print(f'[研判] 技术信号: {tech["signal"]}')
    news = get_news(symbol)
    print(f'[研判] 近期新闻 {len(news)} 条')
    sectors = get_hot_sectors()
    print(f'[研判] 热点板块 {len(sectors)} 个')
    print('[研判] AI 综合研判中(约30-90秒)...')
    judge = ai_judge(symbol, tech, news, sectors)
    judge.setdefault('verdict', '中性')
    judge.setdefault('confidence', 0)
    judge.setdefault('summary', '')
    judge.setdefault('reasons', [])
    judge.setdefault('risks', [])
    return {
        'symbol': symbol,
        'date': tech['date'],
        'tech': tech,
        'news': news,
        'hot_sectors': sectors,
        'verdict': judge['verdict'],
        'confidence': judge['confidence'],
        'summary': judge['summary'],
        'reasons': judge['reasons'],
        'risks': judge['risks'],
    }


def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else '601108'
    r = advisor_run(symbol)
    lines = [
        '=' * 50,
        f'  AI 综合研判 · {r["symbol"]} · {r["date"]}',
        '=' * 50,
        f'  结论: {r["verdict"]} (置信度 {r["confidence"]}%)',
        f'  一句话: {r["summary"]}',
        '-' * 50,
        '  技术信号:',
        f'    {r["tech"]["signal"]} — {r["tech"]["reason"]}',
        '  近期新闻:',
    ]
    for n in r['news'][:5]:
        lines.append(f'    [{n["time"]}] {n["title"][:45]}')
    lines.append('  今日热点板块:')
    for s in r['hot_sectors'][:6]:
        lines.append(f'    {s["name"]} {s["pct"]:+.2f}%')
    lines.append('  AI 理由:')
    for x in r['reasons']:
        lines.append(f'    • {x}')
    lines.append('  AI 风险提示:')
    for x in r['risks']:
        lines.append(f'    ⚠ {x}')
    lines.append('=' * 50)
    lines.append('⚠️ 仅供学习研究, 不构成投资建议')
    text = '\n'.join(lines)
    print(text)
    out = os.path.join(OUTDIR, f'AI研判_{r["date"]}.txt')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(text)
    print(f'\n已保存: {out}')


if __name__ == '__main__':
    main()
