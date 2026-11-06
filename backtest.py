# -*- coding: utf-8 -*-
"""
双均线量化策略回测引擎（演示版）
==================================
用法:  python backtest.py [股票代码] [快线天数] [慢线天数] [起始日期]
示例:  python backtest.py 601108 20 60 20190101

策略逻辑（经典双均线趋势策略）:
  - 快线(MA20) 从下方上穿 慢线(MA60)  -> 金叉, 买入
  - 快线 从上方下穿 慢线             -> 死叉, 卖出
  - 不预测涨跌, 只跟随趋势: 涨势持有, 跌势空仓
"""
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import numpy as np
import pandas as pd
import akshare as ak
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# ---------- 中文显示 ----------
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False

# ---------- 参数(仅命令行直接运行时解析, import 时用默认值) ----------
SYMBOL = '601108'   # 股票代码
FAST   = 20         # 快线
SLOW   = 60         # 慢线
START  = '20190101' # 回测起点
END    = '20260101'
if __name__ == '__main__':
    if len(sys.argv) > 1:
        SYMBOL = sys.argv[1]
    if len(sys.argv) > 2:
        FAST = int(sys.argv[2])
    if len(sys.argv) > 3:
        SLOW = int(sys.argv[3])
    if len(sys.argv) > 4:
        START = sys.argv[4]
OUTDIR = r'C:\Users\LZY20\Desktop\量化回测'

import os
os.makedirs(OUTDIR, exist_ok=True)


def fetch(symbol: str, start: str, end: str, use_cache: bool = True) -> pd.DataFrame:
    """爬取 A 股日线行情(前复权), 全量缓存到本地 CSV; 断连自动重试
    缓存策略: 总是存全量(2019 起), 请求起点不同直接切片, 不再重复爬"""
    import time as _time
    data_dir = os.path.join(OUTDIR, 'data')
    os.makedirs(data_dir, exist_ok=True)
    csv_path = os.path.join(data_dir, f'{symbol}.csv')
    FULL_START, FULL_END = '20190101', '20270101'

    if use_cache and os.path.exists(csv_path):
        try:
            cached = pd.read_csv(csv_path, parse_dates=['date'])
            fresh = (pd.Timestamp.now() - cached['date'].max()).days <= 15  # 缓存新鲜度
            if (len(cached) > 100 and fresh
                    and cached['date'].min() <= pd.Timestamp(start)):
                df = cached.set_index('date')[['open', 'close', 'high', 'low', 'volume']].astype(float)
                print(f'[本地缓存] {csv_path}  共 {len(df)} 行')
                return df[df.index >= pd.Timestamp(start)]
        except Exception:
            pass

    print(f'[爬取] 正在从东方财富接口获取 {symbol} 日线数据(全量缓存)...')
    last = None
    for i in range(3):  # 东财接口偶发断连/风控/空数据, 自动重试
        try:
            df = ak.stock_zh_a_hist(symbol=symbol, period='daily',
                                    start_date=FULL_START, end_date=FULL_END, adjust='qfq')
            if df is not None and len(df) > 0:
                break
            last = Exception('东财返回空数据')
            _time.sleep(3)
        except Exception as e:
            last = e
            _time.sleep(3)
    else:
        # 东财不可用, 降级到新浪源(ETF 用新浪ETF接口)
        print('[爬取] 东财接口不可用, 降级新浪源...')
        prefix = 'sh' if symbol[0] in '569' else 'sz'
        if symbol[0] in '51':  # ETF
            df = ak.fund_etf_hist_sina(symbol=prefix + symbol)
        else:
            df = ak.stock_zh_a_daily(symbol=prefix + symbol,
                                     start_date=FULL_START, end_date=FULL_END, adjust='qfq')
        if df is None or len(df) == 0:
            raise last
    if '日期' in df.columns:  # 东财中文列
        df = df.rename(columns={
            '日期': 'date', '开盘': 'open', '收盘': 'close',
            '最高': 'high', '最低': 'low', '成交量': 'volume'})
    # 新浪源列已是英文 date/open/high/low/close/volume
    df['date'] = pd.to_datetime(df['date'])
    df = df.set_index('date')[['open', 'close', 'high', 'low', 'volume']].astype(float)
    df.to_csv(csv_path)
    print(f'[已存本地] {csv_path}  共 {len(df)} 行')
    return df[df.index >= pd.Timestamp(start)]


def backtest(df: pd.DataFrame, fast: int, slow: int, symbol: str = None):
    """核心回测: 返回带信号/持仓/净值的 DataFrame 和统计指标"""
    symbol = symbol or SYMBOL
    d = df.copy()
    d['ma_f'] = d['close'].rolling(fast).mean()
    d['ma_s'] = d['close'].rolling(slow).mean()

    # 信号: 快线在慢线上方 -> 持仓(1), 否则空仓(0)
    d['signal'] = np.where(d['ma_f'] > d['ma_s'], 1.0, 0.0)
    d['pos'] = d['signal'].diff().fillna(0.0)          # 今天是否换仓

    # 净值计算: 策略按 signal 决定是否持有; 基准=一直持有
    d['ret'] = d['close'].pct_change().fillna(0.0)
    d['strat_ret'] = d['ret'] * d['signal'].shift(1).fillna(0.0)
    d['strat'] = (1 + d['strat_ret']).cumprod()
    d['bench'] = (1 + d['ret']).cumprod()

    # ---------- 统计指标 ----------
    days = len(d)
    years = days / 252.0
    total = d['strat'].iloc[-1] - 1
    bench_total = d['bench'].iloc[-1] - 1
    ann = (d['strat'].iloc[-1]) ** (1 / years) - 1
    ann_bench = (d['bench'].iloc[-1]) ** (1 / years) - 1

    # 最大回撤
    dd = d['strat'] / d['strat'].cummax() - 1
    max_dd = dd.min()

    # 夏普比率(无风险利率按 1.5%)
    rf = 0.015
    sharpe = (d['strat_ret'].mean() * 252 - rf) / (d['strat_ret'].std() * np.sqrt(252)) if d['strat_ret'].std() > 0 else 0

    # 交易记录与胜率
    trades = []
    entry_price = None
    entry_date = None
    for idx, row in d.iterrows():
        if row['pos'] > 0 and entry_price is None:          # 买入
            entry_price = row['close']; entry_date = idx
        elif row['pos'] < 0 and entry_price is not None:    # 卖出
            trades.append((entry_date, idx, row['close'] / entry_price - 1))
            entry_price = None
    if entry_price is not None:                              # 还在持仓, 按最后价格平仓
        trades.append((entry_date, d.index[-1], d['close'].iloc[-1] / entry_price - 1))
    win_rate = np.mean([t[2] > 0 for t in trades]) if trades else 0.0
    avg_win = np.mean([t[2] for t in trades if t[2] > 0]) if any(t[2] > 0 for t in trades) else 0.0
    avg_loss = np.mean([t[2] for t in trades if t[2] <= 0]) if any(t[2] <= 0 for t in trades) else 0.0

    stats = {
        '股票/代码': symbol, '区间': f'{d.index[0].date()} ~ {d.index[-1].date()}',
        '参数': f'MA{fast}/MA{slow}',
        '总收益率(策略)': f'{total*100:.2f}%',
        '总收益率(一直持有)': f'{bench_total*100:.2f}%',
        '年化收益(策略)': f'{ann*100:.2f}%',
        '年化收益(一直持有)': f'{ann_bench*100:.2f}%',
        '最大回撤': f'{max_dd*100:.2f}%',
        '夏普比率': f'{sharpe:.2f}',
        '交易次数': len(trades),
        '胜率': f'{win_rate*100:.1f}%',
        '平均盈利': f'{avg_win*100:.2f}%',
        '平均亏损': f'{avg_loss*100:.2f}%',
    }
    return d, stats, trades


def plot(d: pd.DataFrame, stats: dict, trades: list, outpath: str,
         fast: int = None, slow: int = None, symbol: str = None):
    fast = fast or FAST
    slow = slow or SLOW
    symbol = symbol or SYMBOL
    fig, axes = plt.subplots(3, 1, figsize=(14, 11), sharex=True,
                             gridspec_kw={'height_ratios': [2.2, 1.2, 1.2]})

    # 上图: 价格 + 均线 + 买卖点
    ax = axes[0]
    ax.plot(d.index, d['close'], lw=1.2, color='#333333', label='收盘价')
    ax.plot(d.index, d['ma_f'], lw=1.0, color='#e6a23c', label=f'MA{fast} 快线')
    ax.plot(d.index, d['ma_s'], lw=1.0, color='#409eff', label=f'MA{slow} 慢线')
    buys = [t[0] for t in trades]
    sells = [t[1] for t in trades]
    ax.scatter(buys, d.loc[buys, 'close'], marker='^', s=90, color='red', zorder=5, label='买入(金叉)')
    ax.scatter(sells, d.loc[sells, 'close'], marker='v', s=90, color='green', zorder=5, label='卖出(死叉)')
    ax.set_title(f'{symbol} 双均线策略回测  MA{fast}/MA{slow}  {stats["区间"]}', fontsize=14)
    ax.legend(loc='upper left', fontsize=9)
    ax.grid(alpha=0.3)

    # 中图: 策略净值 vs 基准
    ax = axes[1]
    ax.plot(d.index, d['strat'], lw=1.6, color='#f56c6c', label='策略净值')
    ax.plot(d.index, d['bench'], lw=1.2, color='#909399', label='一直持有(基准)')
    ax.axhline(1.0, color='black', lw=0.6, alpha=0.5)
    ax.set_title(f'策略收益 {stats["总收益率(策略)"]}  vs  一直持有 {stats["总收益率(一直持有)"]}   最大回撤 {stats["最大回撤"]}', fontsize=11)
    ax.legend(loc='upper left', fontsize=9)
    ax.grid(alpha=0.3)

    # 下图: 回撤
    ax = axes[2]
    dd = d['strat'] / d['strat'].cummax() - 1
    ax.fill_between(d.index, dd * 100, 0, color='#f56c6c', alpha=0.4)
    ax.set_title('策略回撤曲线', fontsize=11)
    ax.set_ylabel('%')
    ax.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(outpath, dpi=120)
    plt.close()
    print(f'图表已保存: {outpath}')


def main():
    print(f'正在拉取 {SYMBOL} 的行情数据(东方财富接口)...')
    try:
        df = fetch(SYMBOL, START, END)
    except Exception as e:
        print(f'拉取失败: {e}\n请检查网络或股票代码是否正确(如 601108=财通证券, 510300=沪深300ETF)')
        sys.exit(1)
    if len(df) < SLOW + 10:
        print('数据量太少, 无法回测(可能代码错误或上市时间短)')
        sys.exit(1)

    d, stats, trades = backtest(df, FAST, SLOW)

    print('\n================ 回测结果 ================')
    for k, v in stats.items():
        print(f'  {k:<14}: {v}')
    print('==========================================\n')

    outpath = os.path.join(OUTDIR, f'回测_{SYMBOL}_MA{FAST}_{SLOW}.png')
    plot(d, stats, trades, outpath)


if __name__ == '__main__':
    main()
