# -*- coding: utf-8 -*-
"""
自动迭代系统 — AI 在环策略进化引擎
====================================
用法:  python iteration.py [股票代码] [运行分钟数]
示例:  python iteration.py 601108 60

进化循环(每轮):
  1. AI 教练(Ollama qwen2.5:7b) 基于历史结果提议一组参数
  2. 引擎随机探索两组参数(保证不陷在局部最优)
  3. 每组都跑虚拟回测(支持 止损/成交量过滤)
  4. 评分(夏普0.4+卡玛0.4+年化0.2), 更新全局最优
  5. 进度实时写入 桌面/量化回测/iteration/ (Web 操作台可看)

直到时间预算用完, 输出最终进化报告。
"""
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import os
import re
import json
import time
import random

import numpy as np
import pandas as pd
import requests

from backtest import fetch
from optimize import score, pct

SYMBOL = sys.argv[1] if len(sys.argv) > 1 else '601108'
SYMBOLS = [s.strip() for s in SYMBOL.split(',') if s.strip()]  # 支持逗号分隔多股票联考
MINUTES = float(sys.argv[2]) if len(sys.argv) > 2 else 60.0
WF = len(sys.argv) > 3 and sys.argv[3].lower() == 'wf'   # wf = 闭卷考试模式
START = '20190101'
END = '20260101'
# 闭卷考试切分: 训练段=2019~2022(AI可看), 测试段=2023起(AI从未见过)
WF_TRAIN_END = '2023-01-01'
WF_TEST_START = '2023-01-01'
WF_FEED = '2022-10-01'
OLLAMA = 'http://127.0.0.1:11434/api/generate'
OUTDIR = r'C:\Users\LZY20\Desktop\量化回测'
ITER_DIR = os.environ.get('ITER_DIR', os.path.join(OUTDIR, 'iteration'))

RNG = random.Random(42)


# ---------- 策略引擎(含止损/量过滤) ----------
def strategy_backtest(df, fast, slow, stop_loss=None, volume_filter=None, vol_n=20, eval_start=None):
    """双均线 + 可选止损 + 可选放量确认。返回 (d, stats, trades)
    eval_start: 评估起点(交易日之前只算均线预热, 不开仓), 用于样本外验证"""
    d = df.copy()
    d['ma_f'] = d['close'].rolling(fast).mean()
    d['ma_s'] = d['close'].rolling(slow).mean()
    d['vol_ma'] = d['volume'].rolling(vol_n).mean()

    closes = d['close'].values
    vols = d['volume'].values
    vol_mas = d['vol_ma'].values
    ma_f = d['ma_f'].values
    ma_s = d['ma_s'].values
    sig = (ma_f > ma_s).astype(int)
    idx = d.index
    n = len(d)
    n_eff = n if eval_start is None else int((idx >= eval_start).sum())

    pos_arr = np.zeros(n)
    trades = []
    in_pos = False
    entry_price = 0.0
    entry_date = None
    for i in range(n):
        if eval_start is not None and idx[i] < eval_start:
            pos_arr[i] = 0.0
            continue
        if not in_pos:
            cross = i > 0 and ma_f[i - 1] <= ma_s[i - 1] and ma_f[i] > ma_s[i]
            vol_ok = (volume_filter is None or volume_filter == 0
                      or (not np.isnan(vol_mas[i]) and vols[i] > vol_mas[i] * volume_filter))
            if cross and vol_ok and not np.isnan(ma_f[i]):
                in_pos = True
                entry_price = closes[i]
                entry_date = idx[i]
        else:
            stop_hit = (stop_loss and stop_loss > 0
                        and closes[i] < entry_price * (1 - stop_loss))
            if stop_hit or sig[i] == 0:
                trades.append((entry_date, idx[i], closes[i] / entry_price - 1))
                in_pos = False
        pos_arr[i] = 1.0 if in_pos else 0.0
    if in_pos:
        trades.append((entry_date, idx[-1], closes[-1] / entry_price - 1))

    ret = d['close'].pct_change().fillna(0.0).values
    strat_ret = ret * np.roll(pos_arr, 1)
    strat_ret[0] = 0.0
    strat = np.cumprod(1 + strat_ret)
    bench = np.cumprod(1 + ret)
    years = n_eff / 252.0

    ann = strat[-1] ** (1 / years) - 1
    total = strat[-1] - 1
    bench_total = bench[-1] - 1
    dd = strat / np.maximum.accumulate(strat) - 1
    maxdd = dd.min()
    sd = np.std(strat_ret)
    sharpe = (np.mean(strat_ret) * 252 - 0.015) / (sd * np.sqrt(252)) if sd > 0 else 0.0

    win_rate = np.mean([t[2] > 0 for t in trades]) if trades else 0.0
    wins = [t[2] for t in trades if t[2] > 0]
    losses = [t[2] for t in trades if t[2] <= 0]
    avg_win = np.mean(wins) if wins else 0.0
    avg_loss = np.mean(losses) if losses else 0.0

    stats = {
        '股票/代码': SYMBOL,
        '区间': f'{idx[0].date()} ~ {idx[-1].date()}',
        '参数': f'MA{fast}/{slow} 止损{stop_loss or 0} 量过滤{volume_filter or 0}',
        '总收益率(策略)': f'{total * 100:.2f}%',
        '总收益率(一直持有)': f'{bench_total * 100:.2f}%',
        '年化收益(策略)': f'{ann * 100:.2f}%',
        '年化收益(一直持有)': f'{((bench[-1]) ** (1 / years) - 1) * 100:.2f}%',
        '最大回撤': f'{maxdd * 100:.2f}%',
        '夏普比率': f'{sharpe:.2f}',
        '交易次数': len(trades),
        '胜率': f'{win_rate * 100:.1f}%',
        '平均盈利': f'{avg_win * 100:.2f}%',
        '平均亏损': f'{avg_loss * 100:.2f}%',
    }
    d['strat'] = strat
    d['bench'] = bench
    return d, stats, trades


# ---------- 参数工具 ----------
def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def sanitize(cfg):
    """把 AI 输出钳制到合法范围, 保留 reason 决策理由"""
    fast = int(clamp(cfg.get('fast', 10), 3, 50))
    slow = int(clamp(cfg.get('slow', 60), fast + 5, 250))
    sl = float(cfg.get('stop_loss', 0) or 0)
    sl = round(clamp(sl, 0, 0.15), 3)
    vf = float(cfg.get('volume_filter', 0) or 0)
    vf = round(clamp(vf, 0, 3.0), 2)
    if vf < 0.8:
        vf = 0
    out = {'fast': fast, 'slow': slow, 'stop_loss': sl, 'volume_filter': vf}
    reason = str(cfg.get('reason', '')).strip()
    if reason:
        out['reason'] = reason[:120]
    return out


def bt_cfg(c):
    """剔除 reason 等非回测参数, 供 strategy_backtest 使用"""
    return {k: v for k, v in c.items() if k != 'reason'}


def rand_cfg():
    """随机探索参数"""
    fast = RNG.randint(3, 50)
    slow = RNG.randint(fast + 5, 250)
    sl = 0 if RNG.random() < 0.4 else round(RNG.uniform(0.02, 0.15), 3)
    vf = 0 if RNG.random() < 0.6 else round(RNG.uniform(0.8, 3.0), 2)
    return {'fast': fast, 'slow': slow, 'stop_loss': sl, 'volume_filter': vf}


# ---------- AI 提议 ----------
def ai_propose(best, history):
    """让 Ollama 基于历史进化结果提议下一组参数"""
    symbol_desc = '、'.join(SYMBOLS) + (' (多股票闭卷联考: 规则需在所有股票的训练段+测试段都过关)' if len(SYMBOLS) > 1 else '')
    ctx = {
        'symbol': symbol_desc,
        'best_now': {**bt_cfg(best['cfg']), 'score': round(best['score'], 4)} if best['cfg'] else None,
        'recent_rounds': history[-12:],
    }
    prompt = f"""你是量化策略进化引擎。正在优化 {symbol_desc} 的双均线策略, 参数含义:
- fast: 快线天数(3-50整数)
- slow: 慢线天数(fast+5 到 250整数)
- stop_loss: 止损比例(0=不用, 0.02-0.15)
- volume_filter: 成交量过滤倍数(0=不用, 0.8-3.0, 金叉日成交量需超过20日均量此倍数)

当前最优策略: {json.dumps(ctx['best_now'], ensure_ascii=False)}
最近尝试过的组合与分数: {json.dumps(ctx['recent_rounds'], ensure_ascii=False)}

请基于这些结果提议下一组值得测试的参数。策略: 在最优附近微调与大胆探索之间平衡; 若回撤过大优先加止损; 若连续多轮无改进就换方向; 避免重复最近试过的组合。
只输出 JSON 对象, 不要任何其他文字或解释:
{{"fast": 3到50的整数, "slow": 大于fast且不超过250的整数, "stop_loss": 0到0.15的小数(0表示不用), "volume_filter": 0.8到3.0的小数(0表示不用), "reason": "一句话理由"}}"""
    try:
        r = requests.post(OLLAMA, json={
            'model': 'qwen2.5:7b', 'prompt': prompt, 'stream': False,
            'format': 'json', 'options': {'temperature': 0.7}},
            timeout=600)
        txt = r.json()['response']
        m = re.search(r'\{.*\}', txt, re.S)
        if not m:
            return None
        return sanitize(json.loads(m.group(0)))
    except Exception:
        return None


# ---------- 进度持久化 ----------
def save_progress(best, round_no, history, start, total_sec):
    os.makedirs(ITER_DIR, exist_ok=True)
    elapsed = time.time() - start
    prog = {
        'symbol': SYMBOL,
        'started': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start)),
        'elapsed_sec': round(elapsed),
        'total_sec': round(total_sec),
        'round': round_no,
        'best': {**best['cfg'], 'score': round(best['score'], 4),
                 '年化%': pct(best['stats']['年化收益(策略)']) * 100 if best['stats'] else None,
                 '回撤%': pct(best['stats']['最大回撤']) * 100 if best['stats'] else None,
                 '夏普': best['stats']['夏普比率'] if best['stats'] else None,
                 '胜率': best['stats']['胜率'] if best['stats'] else None,
                 '测试年化%': (best.get('te_mean', 0) * 100 if best.get('te_mean') is not None
                              else (pct(best['test_stats']['年化收益(策略)']) * 100
                                    if best.get('test_stats') else None))} if best['cfg'] else None,
        'last_update': time.strftime('%H:%M:%S'),
    }
    with open(os.path.join(ITER_DIR, 'progress.json'), 'w', encoding='utf-8') as f:
        json.dump(prog, f, ensure_ascii=False, indent=2)
    if history:
        pd.DataFrame(history).to_csv(os.path.join(ITER_DIR, 'history.csv'),
                                     index=False, encoding='utf-8-sig')


def final_report(best, history, start):
    print('\n================ 自动迭代最终报告 ================')
    print(f'股票: {SYMBOL}  共 {len(history)} 次尝试, 耗时 {(time.time()-start)/60:.1f} 分钟')
    if best['cfg']:
        print(f'最优策略: 快线{best["cfg"]["fast"]} 慢线{best["cfg"]["slow"]} '
              f'止损{best["cfg"]["stop_loss"]} 量过滤{best["cfg"]["volume_filter"]}')
        print(f'综合分: {best["score"]:.4f}')
        for k in ['总收益率(策略)', '年化收益(策略)', '最大回撤', '夏普比率', '胜率', '交易次数']:
            print(f'  {k}: {best["stats"][k]}')
        if best.get('te_anns'):
            print('  --- 闭卷联考测试段(2023-2025, AI从未见过) ---')
            for s, v in best['te_anns'].items():
                print(f'    {s}: 测试年化 {v*100:.2f}%')
        elif best.get('test_stats'):
            print('  --- 闭卷测试段(2023-2025, AI从未见过) ---')
            for k in ['总收益率(策略)', '年化收益(策略)', '最大回撤', '夏普比率', '胜率', '交易次数']:
                print(f'  {k}: {best["test_stats"][k]}')
    else:
        print('未找到有效策略(可能 Ollama 不可用且数据异常)')
    print('==================================================')
    with open(os.path.join(ITER_DIR, 'final_report.txt'), 'w', encoding='utf-8') as f:
        f.write(json.dumps({
            'symbol': SYMBOL,
            'attempts': len(history),
            'minutes': round((time.time() - start) / 60, 1),
            'best': {**best['cfg'], 'score': best['score']} if best['cfg'] else None,
        }, ensure_ascii=False, indent=2))

    # 最终交付: 最优策略买卖点图 + 进化轨迹图
    if best['cfg']:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            from backtest import plot
            df = fetch(SYMBOLS[0], START, END)
            d, stats, trades = strategy_backtest(df, **bt_cfg(best['cfg']))
            plot(d, stats, trades, os.path.join(ITER_DIR, f'最终策略_{SYMBOL}.png'),
                 best['cfg']['fast'], best['cfg']['slow'], SYMBOL)
            # 进化轨迹
            hdf = pd.DataFrame(history)
            plt.figure(figsize=(12, 5))
            plt.scatter(hdf['round'], hdf['score'], s=14, alpha=0.45,
                        color='#8b94a7', label='单次尝试分数')
            plt.plot(hdf['round'], hdf['score'].cummax(), color='#f0b90b', lw=2, label='累计最优')
            plt.xlabel('轮次')
            plt.ylabel('综合分')
            plt.title(f'{SYMBOL} 自动迭代进化轨迹 (共 {len(history)} 次尝试, 最优 {best["score"]:.4f})')
            plt.legend()
            plt.grid(alpha=0.3)
            plt.tight_layout()
            plt.savefig(os.path.join(ITER_DIR, f'进化轨迹_{SYMBOL}.png'), dpi=120)
            plt.close()
            print(f'图表已保存: 桌面\\量化回测\\iteration\\  (最终策略/进化轨迹)')
        except Exception as e:
            print('图表生成失败:', e)


def main():
    total_sec = MINUTES * 60
    os.makedirs(ITER_DIR, exist_ok=True)

    print(f'[迭代系统] 股票池 {SYMBOLS} 预算 {MINUTES} 分钟, 加载数据...')
    if WF:
        train_dfs, test_dfs = {}, {}
        for s in SYMBOLS:
            df = fetch(s, START, END)
            train_dfs[s] = df[df.index < pd.Timestamp(WF_TRAIN_END)]
            test_dfs[s] = df[df.index >= pd.Timestamp(WF_FEED)]
            print(f'[闭卷联考] {s}: 训练段 {len(train_dfs[s])}日 / 测试段 {len(test_dfs[s])}日(含预热)')
        print(f'[闭卷联考] 共 {len(SYMBOLS)} 只股票, 规则必须在每只股票 训练段+测试段 都过关')
    else:
        df = fetch(SYMBOL, START, END)
        print(f'[迭代系统] 数据 {len(df)} 行, 开始进化循环')

    best = {'cfg': None, 'score': -1e9, 'stats': None, 'test_stats': None, 'te_mean': None}
    history = []
    start = time.time()
    round_no = 0
    ai_ok = 0
    while time.time() - start < total_sec:
        round_no += 1
        candidates = []
        cfg = ai_propose(best, history)
        if cfg:
            ai_ok += 1
            candidates.append(('ai', cfg))
        else:
            print(f'[轮次{round_no}] AI 提议失败, 本轮仅随机探索', flush=True)
        for _ in range(2):
            candidates.append(('random', rand_cfg()))

        for src, c in candidates:
            if WF:
                # ---- 多股票闭卷联考: 每只股票训练+测试, 全部及格才算数 ----
                tr_scores, te_anns, te_stats_all = [], {}, {}
                tr_stats0 = te_stats0 = None
                for s in SYMBOLS:
                    tr_d, tr_stats, tr_trades = strategy_backtest(train_dfs[s], **bt_cfg(c))
                    te_d, te_stats, te_trades = strategy_backtest(
                        test_dfs[s], eval_start=pd.Timestamp(WF_TEST_START), **bt_cfg(c))
                    tr_ann = pct(tr_stats['年化收益(策略)'])
                    tr_maxdd = pct(tr_stats['最大回撤'])
                    tr_sharpe = float(tr_stats['夏普比率'])
                    tr_scores.append(score(tr_ann, tr_maxdd, tr_sharpe, len(tr_trades)))
                    te_anns[s] = pct(te_stats['年化收益(策略)'])
                    te_stats_all[s] = te_stats
                    if tr_stats0 is None:
                        tr_stats0, te_stats0 = tr_stats, te_stats
                tr_sc = float(np.mean(tr_scores))
                te_mean = float(np.mean(list(te_anns.values())))
                all_pass = all(v > 0 for v in te_anns.values())
                # 联考规则: 每只股票测试段都赚钱才给满分奖励; 平均及格半价; 否则淘汰
                if all_pass:
                    sc = tr_sc * (1 + 0.5 * min(te_mean, 0.25) / 0.25)
                elif te_mean > 0:
                    sc = tr_sc * 0.5
                else:
                    sc = tr_sc * 0.1
                stats = tr_stats0
                history.append({
                    'round': round_no, 'time': time.strftime('%H:%M:%S'),
                    'source': src, **c,
                    'score': round(sc, 4),
                    '年化%': round(pct(tr_stats0['年化收益(策略)']) * 100, 2),
                    '回撤%': round(pct(tr_stats0['最大回撤']) * 100, 2),
                    '夏普': round(float(tr_stats0['夏普比率']), 2),
                    '胜率': tr_stats0['胜率'],
                    '交易': tr_stats0['交易次数'],
                    '联考测试均年化%': round(te_mean * 100, 2),
                    **{f'测试年化_{s}': round(v * 100, 2) for s, v in te_anns.items()},
                })
                if sc > best['score']:
                    best = {'cfg': c, 'score': sc, 'stats': tr_stats0,
                            'test_stats': te_stats0, 'te_mean': te_mean, 'te_anns': te_anns}
                    print(f'  ★ 新最优 轮{round_no}[{src}] {c} 分={sc:.4f} '
                          f'(训练均{tr_sc*100:.1f}% 测试均{te_mean*100:.1f}% '
                          f'各股{[f"{s}:{v*100:.0f}%" for s, v in te_anns.items()]})', flush=True)
            else:
                d, stats, trades = strategy_backtest(df, **bt_cfg(c))
                ann = pct(stats['年化收益(策略)'])
                maxdd = pct(stats['最大回撤'])
                sharpe = float(stats['夏普比率'])
                sc = score(ann, maxdd, sharpe, len(trades))
                history.append({
                    'round': round_no, 'time': time.strftime('%H:%M:%S'),
                    'source': src, **c,
                    'score': round(sc, 4),
                    '年化%': round(ann * 100, 2),
                    '回撤%': round(maxdd * 100, 2),
                    '夏普': round(sharpe, 2),
                    '胜率': stats['胜率'],
                    '交易': stats['交易次数'],
                })
                if sc > best['score']:
                    best = {'cfg': c, 'score': sc, 'stats': stats}
                    print(f'  ★ 新最优 轮{round_no}[{src}] {c} 分={sc:.4f}', flush=True)

        save_progress(best, round_no, history, start, total_sec)
        if round_no % 2 == 0:
            elapsed = time.time() - start
            print(f'[心跳 轮{round_no}] 已用 {int(elapsed)}s/{int(total_sec)}s, '
                  f'AI提议成功{ai_ok}次, 当前最优分={best["score"]:.4f}', flush=True)

    final_report(best, history, start)


if __name__ == '__main__':
    main()
