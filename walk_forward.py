# -*- coding: utf-8 -*-
"""
样本外验证系统 (Walk-Forward) — 把后面的走线遮住
==================================================
用法:  python walk_forward.py [股票代码] [训练分钟数]
示例:  python walk_forward.py 601108 3

流程:
  1. 训练段(2019-01-01 ~ 2022-12-31): AI 只在这段历史里选参数
  2. 测试段(2023-01-01 起): AI 从未见过的"未来", 用训练好的规则原封不动跑
  3. 对比打分: 训练段赚/测试段也赚 = 真策略; 训练赚/测试亏 = 过拟合

输出: 桌面/量化回测/walk_forward/ 目录 (报告 + 测试段走势图)
"""
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import time
import json

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest import fetch
from iteration import strategy_backtest, ai_propose, rand_cfg, bt_cfg
from optimize import score, pct

SYMBOL = sys.argv[1] if len(sys.argv) > 1 else '601108'
TRAIN_MIN = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0
TRAIN_START = pd.Timestamp('2019-01-01')
TRAIN_END = pd.Timestamp('2023-01-01')      # 训练段终点(含)
TEST_START = pd.Timestamp('2023-01-01')     # 测试段交易起点
TEST_FEED = pd.Timestamp('2022-10-01')      # 测试段数据起点(前3个月做均线预热)

OUTDIR = r'C:\Users\LZY20\Desktop\量化回测\walk_forward'
os.makedirs(OUTDIR, exist_ok=True)

plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False


def evaluate(df, eval_start, cfg):
    """跑一次回测, 返回 (综合分, stats, trades)"""
    d, stats, trades = strategy_backtest(df, eval_start=eval_start, **bt_cfg(cfg))
    ann = pct(stats['年化收益(策略)'])
    maxdd = pct(stats['最大回撤'])
    sharpe = float(stats['夏普比率'])
    sc = score(ann, maxdd, sharpe, len(trades))
    return sc, stats, trades


def main():
    # ---------- 数据切分(严格遮住测试段) ----------
    print(f'[WF] {SYMBOL} 加载数据...')
    df = fetch(SYMBOL, '2019-01-01', '2026-01-01')
    train_df = df[df.index < TRAIN_END]
    test_df = df[df.index >= TEST_FEED]
    print(f'[WF] 训练段: {train_df.index[0].date()} ~ {train_df.index[-1].date()} ({len(train_df)} 交易日)')
    print(f'[WF] 测试段: {test_df.index[0].date()} ~ {test_df.index[-1].date()} ({len(test_df)} 交易日, 前3个月仅预热)')
    print(f'[WF] AI 全程只能看训练段, 测试段完全遮住')

    # ---------- 训练: AI 迭代找最优规则 ----------
    best = {'cfg': None, 'score': -1e9, 'stats': None}
    history = []
    start = time.time()
    round_no = 0
    while time.time() - start < TRAIN_MIN * 60:
        round_no += 1
        cfg = ai_propose(best, history)
        candidates = [cfg] if cfg else []
        for _ in range(2):
            candidates.append(rand_cfg())
        for c in candidates:
            sc, stats, trades = evaluate(train_df, TRAIN_START, c)
            history.append({'round': round_no, **c, 'score': round(sc, 4),
                            '年化%': stats['年化收益(策略)'], '回撤%': stats['最大回撤'],
                            '交易': stats['交易次数']})
            if sc > best['score']:
                best = {'cfg': c, 'score': sc, 'stats': stats}
                print(f'  ★ 训练段新最优 轮{round_no}: {c} 分={sc:.4f}', flush=True)
        if round_no % 10 == 0:
            print(f'[WF] 训练轮次 {round_no}, 已用 {int(time.time()-start)}s, 最优 {best["score"]:.4f}', flush=True)

    print(f'\n[WF] 训练完成: {len(history)} 次尝试, 最优规则 {best["cfg"]}')
    print(f'[WF] 训练段表现: 年化{best["stats"]["年化收益(策略)"]} 回撤{best["stats"]["最大回撤"]} '
          f'交易{best["stats"]["交易次数"]}次')

    # ---------- 测试: 闭卷考试 ----------
    print('\n[WF] 现在把规则拿到 2023 年之后的"未来"去跑...')
    test_sc, test_stats, test_trades = evaluate(test_df, TEST_START, best['cfg'])
    print(f'[WF] 测试段表现: 年化{test_stats["年化收益(策略)"]} 回撤{test_stats["最大回撤"]} '
          f'交易{test_stats["交易次数"]}次 夏普{test_stats["夏普比率"]}')

    # ---------- 结论 ----------
    train_ann = pct(best['stats']['年化收益(策略)'])
    test_ann = pct(test_stats['年化收益(策略)'])
    print('\n================ 样本外验证结论 ================')
    print(f'训练段(2019-2022) 年化: {train_ann*100:.2f}%')
    print(f'测试段(2023-2025) 年化: {test_ann*100:.2f}%')
    if test_ann > 0 and test_ann >= train_ann * 0.5:
        print('判定: ✅ 策略真实有效! 没见过的未来也能赚钱, 不是过拟合')
    elif test_ann > 0:
        print('判定: ⚠️ 测试段仍为正收益但明显衰减, 策略有部分过拟合, 建议迭代改进')
    else:
        print('判定: ❌ 测试段亏损, 训练段成绩是过拟合, 策略不可用')
    print('=================================================')

    # ---------- 图表: 测试段策略 vs 一直持有 ----------
    d, _, _ = strategy_backtest(test_df, eval_start=TEST_START, **best['cfg'])
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(d.index, d['strat'], lw=1.6, color='#f0b90b', label='策略净值(样本外)')
    ax.plot(d.index, d['bench'], lw=1.2, color='#8b94a7', label='一直持有(基准)')
    ax.axhline(1.0, color='black', lw=0.6, alpha=0.5)
    ax.set_title(f'{SYMBOL} 样本外测试 2023-2025  规则: {best["cfg"]}')
    ax.legend(); ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTDIR, f'样本外测试_{SYMBOL}.png'), dpi=120)
    plt.close()
    print(f'图表已保存: 桌面\\量化回测\\walk_forward\\样本外测试_{SYMBOL}.png')

    with open(os.path.join(OUTDIR, f'结论_{SYMBOL}.json'), 'w', encoding='utf-8') as f:
        json.dump({
            'symbol': SYMBOL,
            'best_rule': best['cfg'],
            'train': {'年化%': best['stats']['年化收益(策略)'], '回撤%': best['stats']['最大回撤'],
                      '交易': best['stats']['交易次数']},
            'test': {'年化%': test_stats['年化收益(策略)'], '回撤%': test_stats['最大回撤'],
                     '交易': test_stats['交易次数'], '夏普': test_stats['夏普比率']},
            'verdict': '通过' if test_ann > 0 and test_ann >= train_ann * 0.5 else ('衰减' if test_ann > 0 else '过拟合'),
        }, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
