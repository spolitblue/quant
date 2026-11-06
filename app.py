# -*- coding: utf-8 -*-
"""
量化虚拟购买系统 - 本地操作台 (Web GUI)
=========================================
双击 桌面\量化系统.bat 启动, 自动打开浏览器操作界面
后端: Flask 本地服务 (127.0.0.1:8321)
"""
import os
import sys
import json
import time
import datetime
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, request, jsonify, send_from_directory

import backtest as bt
import optimize as opt

APP_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(APP_DIR, 'web')
OUTDIR = r'C:\Users\LZY20\Desktop\量化回测'

app = Flask(__name__, static_folder=WEB_DIR, static_url_path='/static')
app.json.ensure_ascii = False  # Flask 3.x: 中文直接输出

# 单次回测的最近图表文件名（供前端展示）
_last_chart = {'name': None}


@app.route('/')
def index():
    return send_from_directory(WEB_DIR, 'index.html')


@app.route('/api/backtest', methods=['POST'])
def api_backtest():
    """单次回测: 返回指标 + 生成图表"""
    data = request.get_json(silent=True) or {}
    symbol = str(data.get('symbol', '601108')).strip()
    fast = int(data.get('fast', 20))
    slow = int(data.get('slow', 60))
    start = str(data.get('start', '20190101')).strip()
    try:
        df = bt.fetch(symbol, start, bt.END)
        if len(df) < slow + 10:
            return jsonify({'ok': False, 'error': f'{symbol} 数据不足, 无法回测'})
        d, stats, trades = bt.backtest(df, fast, slow, symbol)
        # 生成图表
        chart_name = f'回测_{symbol}_MA{fast}_{slow}.png'
        bt.plot(d, stats, trades, os.path.join(OUTDIR, chart_name), fast, slow, symbol)
        _last_chart['name'] = chart_name
        return jsonify({'ok': True, 'stats': stats, 'trades': len(trades), 'chart': chart_name})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/optimize', methods=['POST'])
def api_optimize():
    """参数寻优 + AI 打分"""
    data = request.get_json(silent=True) or {}
    symbol = str(data.get('symbol', '601108')).strip()
    start = str(data.get('start', '20190101')).strip()
    use_ai = bool(data.get('use_ai', True))
    try:
        res = opt.optimize_run(symbol, start, with_ai=use_ai)
        if not res['ok']:
            return jsonify({'ok': False, 'error': res['error']})
        # 用最优参数生成图表
        best = res['best']
        df = bt.fetch(symbol, start, bt.END)
        d, stats, trades = bt.backtest(df, int(best['快线']), int(best['慢线']), symbol)
        chart_name = f'回测_{symbol}_MA{best["快线"]}_{best["慢线"]}.png'
        bt.plot(d, stats, trades, os.path.join(OUTDIR, chart_name),
                int(best['快线']), int(best['慢线']), symbol)
        _last_chart['name'] = chart_name
        return jsonify({
            'ok': True,
            'count': res['count'],
            'top': res['top'],
            'best': {**res['best'], 'stats': stats},
            'ai_report': res['ai_report'],
            'chart': chart_name,
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/chart/<path:name>')
def api_chart(name):
    """返回回测图表图片"""
    return send_from_directory(OUTDIR, name)


@app.route('/api/fund', methods=['POST'])
def api_fund():
    """基金专析: 净值+重仓股扫描+企稳三关"""
    data = request.get_json(silent=True) or {}
    symbol = str(data.get('symbol', '020982')).strip()
    try:
        import fund_analyzer
        r = fund_analyzer.analyze(symbol)
        return jsonify(r)
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/watchlist', methods=['POST'])
def api_watchlist():
    """多股票监控: 每只股票的技术信号速览"""
    data = request.get_json(silent=True) or {}
    symbols = [s.strip() for s in str(data.get('symbols', '601108')).replace('，', ',').split(',') if s.strip()]
    symbols = symbols[:8]  # 最多 8 只
    try:
        import daily_signal
        rows = []
        for s in symbols:
            try:
                r = daily_signal.signal_run(s)
                rows.append({'ok': True, 'symbol': s, **r})
            except Exception as e:
                rows.append({'ok': False, 'symbol': s, 'error': str(e)[:80]})
        return jsonify({'ok': True, 'rows': rows})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/advisor')
def api_advisor():
    """AI 综合研判: 技术信号+新闻+热点 → AI 决策(耗时30-90秒)"""
    try:
        import advisor
        r = advisor.advisor_run()
        return jsonify({'ok': True, **r})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/signal')
def api_signal():
    """每日信号: 用最新训练规则对当前行情算买卖信号"""
    try:
        import daily_signal
        r = daily_signal.signal_run()
        return jsonify({'ok': True, **r})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/iteration/start', methods=['POST'])
def api_iteration_start():
    """从操作台一键启动自动迭代(独立控制台窗口运行)"""
    data = request.get_json(silent=True) or {}
    symbol = str(data.get('symbol', '601108')).strip()
    minutes = int(data.get('minutes', 60))
    # 已在运行则拒绝
    p = os.path.join(OUTDIR, 'iteration', 'progress.json')
    if os.path.exists(p):
        try:
            with open(p, encoding='utf-8') as f:
                prog = json.load(f)
            if prog.get('elapsed_sec', 0) < prog.get('total_sec', 0):
                return jsonify({'ok': False, 'error': '迭代已在运行中, 请先等它跑完'})
        except Exception:
            pass
    try:
        subprocess.Popen([sys.executable, 'iteration.py', symbol, str(minutes)],
                         cwd=APP_DIR,
                         creationflags=getattr(subprocess, 'CREATE_NEW_CONSOLE', 0))
        return jsonify({'ok': True, 'msg': f'自动迭代已启动: {symbol} · {minutes} 分钟'})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


def _active_iteration():
    """扫描所有迭代目录, 返回活跃(心跳新鲜)的那个 progress dict"""
    dirs = [os.path.join(OUTDIR, d) for d in ('iteration', 'iteration_multi', 'iteration_wf_smoke')]
    active = None
    for d in dirs:
        p = os.path.join(d, 'progress.json')
        if not os.path.exists(p):
            continue
        prog = None
        for attempt in range(3):  # 读-写竞争: 失败重试
            try:
                with open(p, encoding='utf-8') as f:
                    prog = json.load(f)
                break
            except Exception:
                time.sleep(0.3)
        if prog is None:
            continue
        if prog.get('elapsed_sec', 0) >= prog.get('total_sec', 0):
            continue  # 已跑满
        try:
            # strptime 只给时分秒(日期是1900年), 必须补上今天日期再算年龄
            t = datetime.datetime.strptime(prog.get('last_update', ''), '%H:%M:%S').time()
            last = datetime.datetime.combine(datetime.date.today(), t)
            age = (datetime.datetime.now() - last).total_seconds()
            if age > 180:
                continue  # 心跳过期 = 已停止
        except Exception:
            pass
        if active is None or prog.get('last_update', '') > active.get('last_update', ''):
            active = prog
    return active


@app.route('/api/iteration/status')
def api_iteration_status():
    """自动迭代系统进度(自动识别活跃迭代)"""
    prog = _active_iteration()
    if prog is None:
        return jsonify({'running': False, 'error': '当前没有运行中的迭代'})
    return jsonify({'running': True, **prog})


@app.route('/api/iteration/history')
def api_iteration_history():
    """迭代尝试历史(最近200条, 含修正评分)"""
    prog = _active_iteration()
    csv = None
    if prog is not None:
        for d in ('iteration', 'iteration_multi', 'iteration_wf_smoke'):
            cand = os.path.join(OUTDIR, d, 'history.csv')
            if os.path.exists(cand):
                # 与活跃 progress 同目录的 history
                if os.path.exists(os.path.join(OUTDIR, d, 'progress.json')):
                    csv = cand
                    break
    if csv is None:
        csv = os.path.join(OUTDIR, 'iteration', 'history.csv')
    if not os.path.exists(csv):
        return jsonify({'rows': []})
    try:
        df = pd.read_csv(csv)
        if '交易' in df.columns and '年化%' in df.columns:
            df['修正分'] = df.apply(
                lambda r: opt.score(r['年化%'] / 100, r['回撤%'] / 100, r['夏普'], r['交易']),
                axis=1).round(4)
        return jsonify({'rows': df.tail(200).to_dict('records')})
    except Exception as e:
        return jsonify({'rows': [], 'error': str(e)})


if __name__ == '__main__':
    print('量化操作台已启动: http://127.0.0.1:8321')
    app.run(host='127.0.0.1', port=8321, debug=False, threaded=True)
