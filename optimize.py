# -*- coding: utf-8 -*-
"""
参数寻优 + AI 打分迭代引擎（虚拟购买系统核心）
================================================
用法:  python optimize.py [股票代码] [起始日期]
示例:  python optimize.py 601108 20190101

流程:
  1. 爬取/读取本地行情数据（一次爬取, 反复使用）
  2. 网格搜索几百组「快线/慢线」参数组合, 每组做一次虚拟回测
  3. 按综合评分（夏普+卡玛+年化）排序, 输出 Top10
  4. 调用本地 Ollama (qwen2.5:7b) 对最优组合打分点评, 输出 AI 教练报告
"""
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import os
import json
from itertools import product

import numpy as np
import requests

from backtest import fetch, backtest

SYMBOL = sys.argv[1] if len(sys.argv) > 1 else '601108'
START  = sys.argv[2] if len(sys.argv) > 2 else '20190101'
END    = '20260101'
OUTDIR = r'C:\Users\LZY20\Desktop\量化回测'


def pct(s: str) -> float:
    """把 '12.34%' 转成 0.1234"""
    return float(str(s).rstrip('%')) / 100.0


def score(ann: float, maxdd: float, sharpe: float, trades: int = None) -> float:
    """综合评分: 夏普(风险调整收益)*0.4 + 卡玛(收益/回撤)*0.4 + 年化*0.2
    trades 不为 None 时加样本量惩罚: 交易次数太少(过拟合风险)则打折"""
    calmar = ann / abs(maxdd) if maxdd < 0 else 0.0
    base = sharpe * 0.4 + calmar * 0.4 + ann * 0.2
    if trades is not None:
        base = base * (trades / (trades + 10))  # 2笔→0.17倍, 10笔→0.5倍, 30笔→0.75倍, 60笔→0.86倍
    return base


def optimize_run(symbol: str, start: str, with_ai: bool = True):
    """
    完整寻优流程, 返回结构化结果:
    {ok, symbol, count, top: [...], best: {...}, ai_report: str, error: str}
    """
    result = {'ok': False, 'symbol': symbol, 'count': 0, 'top': [],
              'best': None, 'ai_report': '', 'error': ''}
    try:
        # ---------- 1. 数据 ----------
        df = fetch(symbol, start, END)
        if len(df) < 130:
            result['error'] = '数据不足, 无法寻优'
            return result

        # ---------- 2. 网格搜索 ----------
        fasts = [5, 10, 15, 20, 25, 30, 35, 40]
        slows = [30, 40, 50, 60, 75, 90, 110, 130]
        results = []
        for fast, slow in product(fasts, slows):
            if fast >= slow:
                continue
            try:
                d, stats, trades = backtest(df, fast, slow)
            except Exception:
                continue
            ann = pct(stats['年化收益(策略)'])
            maxdd = pct(stats['最大回撤'])
            sharpe = float(stats['夏普比率'])
            results.append({
                '快线': fast, '慢线': slow,
                '年化收益%': round(ann * 100, 2),
                '最大回撤%': round(maxdd * 100, 2),
                '夏普': round(sharpe, 2),
                '胜率%': stats['胜率'],
                '交易次数': stats['交易次数'],
                '综合分': round(score(ann, maxdd, sharpe), 3),
            })
        results.sort(key=lambda r: r['综合分'], reverse=True)
        top = results[:10]
        result['count'] = len(results)
        result['top'] = top
        result['best'] = top[0]

        # 保存最优参数供后续使用
        with open(os.path.join(OUTDIR, f'最优参数_{symbol}.json'), 'w', encoding='utf-8') as f:
            json.dump({'symbol': symbol, 'start': start, **top[0]}, f,
                      ensure_ascii=False, indent=2)

        # ---------- 3. AI 打分点评 ----------
        if with_ai:
            prompt = f"""你是量化投资教练。下面是同一只股票 {symbol} 用不同双均线参数回测的虚拟交易结果（历史模拟，非真实资金）：

{json.dumps(top[:5], ensure_ascii=False, indent=2)}

请完成三件事：
1. 给每组打一个 0-100 的分数，按分数排序。
2. 指出综合分最高的组合有什么优点和潜在风险（比如是否可能过拟合历史）。
3. 给出 3 条具体可执行的策略改进建议（例如加止损线、换更长周期、结合成交量过滤等）。

用中文回答，控制在 300 字以内，直接给结论。"""
            try:
                r = requests.post('http://127.0.0.1:11434/api/generate',
                                  json={'model': 'qwen2.5:7b', 'prompt': prompt,
                                        'stream': False, 'options': {'temperature': 0.6}},
                                  timeout=600)
                reply = r.json()['response']
            except Exception as e:
                reply = f'(AI 调用失败: {e})'
            result['ai_report'] = reply
            with open(os.path.join(OUTDIR, f'AI教练报告_{symbol}.txt'), 'w', encoding='utf-8') as f:
                f.write(reply)

        result['ok'] = True
        return result
    except Exception as e:
        result['error'] = str(e)
        return result


def main():
    res = optimize_run(SYMBOL, START)
    if not res['ok']:
        print('失败:', res['error'])
        sys.exit(1)
    print(f'\n========== {SYMBOL} 参数寻优结果 Top10（共 {res["count"]} 组） ==========')
    print(f'{"快线":>4} {"慢线":>4} {"年化%":>7} {"最大回撤%":>9} {"夏普":>6} {"胜率":>6} {"次数":>4} {"综合分":>7}')
    for r in res['top']:
        print(f'{r["快线"]:>4} {r["慢线"]:>4} {r["年化收益%"]:>7} {r["最大回撤%"]:>9} {r["夏普"]:>6} {r["胜率%"]:>6} {r["交易次数"]:>4} {r["综合分"]:>7}')
    print('=' * 60)
    print('\n================ AI 教练报告 ================')
    print(res['ai_report'])
    print('==============================================')


if __name__ == '__main__':
    main()
