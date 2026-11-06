# -*- coding: utf-8 -*-
"""
最终分析脚本 — 迭代跑完后输出完整进化报告
==========================================
用法: python final_analysis.py
读 桌面/量化回测/iteration/history.csv, 用修正评分(样本量惩罚)重排全部尝试,
输出: 修正最优策略 + 图表 + 进化轨迹 + 与初始双均线对比
"""
import os
import sys
import json

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from optimize import score
from iteration import strategy_backtest, SYMBOL, START, END
from backtest import fetch, plot, backtest

OUTDIR = r'C:\Users\LZY20\Desktop\量化回测'
ITER_DIR = os.path.join(OUTDIR, 'iteration')
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False


def main():
    hdf = pd.read_csv(os.path.join(ITER_DIR, 'history.csv'))
    print(f'总尝试次数: {len(hdf)}')

    # 修正评分重排
    hdf['new_score'] = hdf.apply(
        lambda r: score(r['年化%'] / 100, r['回撤%'] / 100, r['夏普'], r['交易']), axis=1)
    best_old = hdf.loc[hdf['score'].idxmax()]
    best_new = hdf.loc[hdf['new_score'].idxmax()]

    print('\n========== 自动迭代最终报告 ==========')
    print(f'【原始评分最优】轮{best_old["round"]}[{best_old["source"]}] '
          f'快线{best_old["fast"]} 慢线{best_old["slow"]} 止损{best_old["stop_loss"]} '
          f'量过滤{best_old["volume_filter"]}')
    print(f'  交易{best_old["交易"]}次 | 年化{best_old["年化%"]}% | 回撤{best_old["回撤%"]}% | 分{best_old["score"]}')
    print(f'【修正评分最优(样本量惩罚)】轮{best_new["round"]}[{best_new["source"]}] '
          f'快线{best_new["fast"]} 慢线{best_new["slow"]} 止损{best_new["stop_loss"]} '
          f'量过滤{best_new["volume_filter"]}')
    print(f'  交易{best_new["交易"]}次 | 年化{best_new["年化%"]}% | 回撤{best_new["回撤%"]}% | 修正分{best_new["new_score"]:.4f}')

    # 与初始双均线 MA20/60 对比
    df = fetch(SYMBOL, START, END)
    _, init_stats, _ = backtest(df, 20, 60)
    print('\n【与初始双均线 MA20/60 对比】')
    print(f'  初始: 年化{init_stats["年化收益(策略)"]} 回撤{init_stats["最大回撤"]} '
          f'夏普{init_stats["夏普比率"]} 交易{init_stats["交易次数"]}次')

    # 生成修正最优策略图表
    cfg = dict(fast=int(best_new['fast']), slow=int(best_new['slow']),
               stop_loss=float(best_new['stop_loss']),
               volume_filter=float(best_new['volume_filter']))
    d, stats, trades = strategy_backtest(df, **cfg)
    plot(d, stats, trades, os.path.join(ITER_DIR, f'最终策略_修正_{SYMBOL}.png'),
         cfg['fast'], cfg['slow'], SYMBOL)
    print(f'  修正最优策略图: 桌面\\量化回测\\iteration\\最终策略_修正_{SYMBOL}.png')

    # 进化轨迹图(新旧评分)
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    axes[0].scatter(hdf['round'], hdf['score'], s=12, alpha=0.4, color='#8b94a7', label='单次尝试(旧分)')
    axes[0].plot(hdf['round'], hdf['score'].cummax(), color='#f0b90b', lw=2, label='累计最优(旧分)')
    axes[0].set_ylabel('旧评分')
    axes[0].legend(); axes[0].grid(alpha=0.3)
    axes[1].scatter(hdf['round'], hdf['new_score'], s=12, alpha=0.4, color='#8b94a7', label='单次尝试(修正分)')
    axes[1].plot(hdf['round'], hdf['new_score'].cummax(), color='#00d4aa', lw=2, label='累计最优(修正分)')
    axes[1].set_xlabel('轮次'); axes[1].set_ylabel('修正评分')
    axes[1].legend(); axes[1].grid(alpha=0.3)
    axes[0].set_title(f'{SYMBOL} 自动迭代进化轨迹 (共{len(hdf)}次尝试, {os.path.basename(sys.argv[0])})')
    plt.tight_layout()
    plt.savefig(os.path.join(ITER_DIR, f'进化轨迹_修正_{SYMBOL}.png'), dpi=120)
    plt.close()
    print(f'  进化轨迹图: 桌面\\量化回测\\iteration\\进化轨迹_修正_{SYMBOL}.png')

    # 保存最终结论 JSON
    report = {
        'symbol': SYMBOL,
        'attempts': len(hdf),
        'best_old': best_old.to_dict(),
        'best_new': {**best_new.to_dict(), 'new_score': round(float(best_new['new_score']), 4)},
        'initial_ma20_60': init_stats,
    }
    with open(os.path.join(ITER_DIR, 'final_conclusion.json'), 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print('\n最终结论已保存: final_conclusion.json')
    print('==========================================')


if __name__ == '__main__':
    main()
