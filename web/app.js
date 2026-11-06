/* ===== 量化虚拟购买系统 · 前端逻辑 ===== */
(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const show = (id) => $(id).classList.remove('hidden');
  const hide = (id) => $(id).classList.add('hidden');

  let toastTimer = null;
  function toast(msg) {
    const t = $('toast');
    t.textContent = msg;
    t.classList.remove('hidden');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.add('hidden'), 3200);
  }

  function setLoading(text, on) {
    if (on) { $('loadingText').textContent = text; show('loading'); }
    else { hide('loading'); }
    $('btnOptimize').disabled = on;
    $('btnBacktest').disabled = on;
  }

  function readInputs() {
    const symbol = $('symbol').value.trim();
    const start = $('start').value.trim();
    const fast = parseInt($('fast').value, 10);
    const slow = parseInt($('slow').value, 10);
    if (!/^\d{6}$/.test(symbol)) { toast('股票代码需为 6 位数字'); return null; }
    if (!/^\d{8}$/.test(start)) { toast('起始日期需为 8 位数字, 如 20190101'); return null; }
    if (!(fast >= 3 && fast < slow && slow <= 250)) { toast('快线需小于慢线(3~250)'); return null; }
    return { symbol, start, fast, slow, use_ai: $('useAi').checked };
  }

  function fmtPct(s) {
    const v = parseFloat(String(s).replace('%', ''));
    return isNaN(v) ? '—' : (v > 0 ? '+' + v + '%' : v + '%');
  }

  function renderKpi(stats) {
    $('kpiTotal').textContent = fmtPct(stats['总收益率(策略)']);
    $('kpiTotal').className = 'kpi-value ' + (parseFloat(stats['总收益率(策略)']) >= 0 ? 'pos' : 'danger');
    $('kpiAnn').textContent = fmtPct(stats['年化收益(策略)']);
    $('kpiAnn').className = 'kpi-value ' + (parseFloat(stats['年化收益(策略)']) >= 0 ? 'pos' : 'danger');
    $('kpiMdd').textContent = fmtPct(stats['最大回撤']);
    $('kpiMdd').className = 'kpi-value danger';
    $('kpiSharpe').textContent = stats['夏普比率'];
    $('kpiWin').textContent = stats['胜率'];
    $('kpiTrades').textContent = stats['交易次数'];
    show('kpiSection');
  }

  function renderChart(name, symbol, fast, slow) {
    if (!name) { hide('chartSection'); return; }
    $('chartTag').textContent = `${symbol} · MA${fast}/${slow}`;
    $('chartImg').src = '/api/chart/' + encodeURIComponent(name) + '?t=' + Date.now();
    show('chartSection');
  }

  function renderTable(top, count) {
    const body = $('optTable').querySelector('tbody');
    body.innerHTML = '';
    top.forEach((r, i) => {
      const tr = document.createElement('tr');
      const cells = [i + 1, r['快线'], r['慢线'], fmtPct(r['年化收益%'] + '%'),
        fmtPct(r['最大回撤%'] + '%'), r['夏普'].toFixed(2), r['胜率%'], r['交易次数'], r['综合分'].toFixed(3)];
      cells.forEach(c => {
        const td = document.createElement('td');
        td.textContent = c;
        tr.appendChild(td);
      });
      body.appendChild(tr);
    });
    $('optCount').textContent = `共 ${count} 组参数`;
    const best = top[0];
    $('bestLine').textContent =
      `✅ 最优组合: 快线 MA${best['快线']} + 慢线 MA${best['慢线']} · 年化 ${fmtPct(best['年化收益%'] + '%')} · 综合分 ${best['综合分'].toFixed(3)}`;
  }

  function renderAiReport(text) {
    const el = $('aiReport');
    el.classList.remove('placeholder');
    el.textContent = text || '(AI 未返回内容)';
  }

  function showError(msg) {
    $('errorText').textContent = '⚠️ ' + msg;
    show('errorBox');
  }
  function hideError() { hide('errorBox'); }

  async function api(path, payload) {
    const res = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error('服务响应异常: HTTP ' + res.status);
    return res.json();
  }

  // ---- 单次回测 ----
  $('btnBacktest').addEventListener('click', async () => {
    const p = readInputs(); if (!p) return;
    hideError(); setLoading('正在跑单次回测...', true);
    try {
      const r = await api('/api/backtest', p);
      if (!r.ok) throw new Error(r.error);
      renderKpi(r.stats);
      renderChart(r.chart, p.symbol, p.fast, p.slow);
      toast(`回测完成 · ${p.symbol} 共 ${r.trades} 次交易`);
    } catch (e) {
      showError(e.message); toast('回测失败');
    } finally { setLoading('', false); }
  });

  // ---- 参数寻优 + AI 打分 ----
  $('btnOptimize').addEventListener('click', async () => {
    const p = readInputs(); if (!p) return;
    hideError(); setLoading('正在爬取数据 + 回测 60 组参数...', true);
    try {
      const r = await api('/api/optimize', p);
      if (!r.ok) throw new Error(r.error);
      renderKpi(r.best.stats);
      renderChart(r.chart, p.symbol, r.best['快线'], r.best['慢线']);
      renderTable(r.top, r.count);
      renderAiReport(r.ai_report);
      show('resultSection');
      toast(`优化完成 · 最优 MA${r.best['快线']}/${r.best['慢线']}`);
      if (p.use_ai) setLoading('AI 教练正在打分点评...', true);
      else setLoading('', false);
    } catch (e) {
      showError(e.message); toast('优化失败');
    } finally { setLoading('', false); }
  });

  // ---- 重置 ----
  $('btnReset').addEventListener('click', () => {
    hide('kpiSection'); hide('chartSection'); hide('resultSection');
    hide('errorBox'); hide('loading');
    toast('已重置');
  });

  // 回车触发优化
  ['symbol', 'start', 'fast', 'slow'].forEach(id => {
    $(id).addEventListener('keydown', (e) => { if (e.key === 'Enter') $('btnOptimize').click(); });
  });

  // ---- 基金专析 ----
  $('btnFund').addEventListener('click', async () => {
    const symbol = $('fundSymbol').value.trim();
    if (!/^\d{6}$/.test(symbol)) { toast('基金代码需为 6 位数字'); return; }
    setLoading('正在分析基金(净值+重仓股扫描, 约30秒)...', true);
    try {
      const r = await api('/api/fund', { symbol });
      if (!r.ok) throw new Error(r.error);
      $('fundTag').textContent = `${r.basic.名称} · ${r.nav_last}`;
      $('fundName').textContent = r.basic.名称 || '—';
      $('fundMeta').textContent = `规模 ${r.basic.规模 || '—'} · 经理 ${r.basic.经理 || '—'} · ${r.basic.成立 || ''}成立`;
      $('fundNav').textContent = r.nav_price;
      const chg = r.nav_chg5;
      $('fundChg5').textContent = chg != null ? (chg > 0 ? '+' + chg + '%' : chg + '%') : '—';
      $('fundChg5').className = 'kpi-value ' + (chg != null && chg > 0 ? 'pos' : 'danger');
      $('fundTrendScore').textContent = r.trend_score + '/100';
      $('fundStopScore').textContent = r.stop_score + '/100';
      $('fundChart').src = '/api/chart/' + encodeURIComponent(r.chart) + '?t=' + Date.now();
      $('fundTable').querySelector('tbody').innerHTML = r.holdings.map(h => {
        if (h.error) return `<tr><td>${h.code}</td><td>${h.name}</td><td colspan="6" style="text-align:left;color:var(--red);">⚠ ${h.error}</td></tr>`;
        return `<tr><td>${h.code}</td><td>${h.name}</td><td>${h.weight}</td>` +
          `<td style="color:${h.signal.includes('买入') ? 'var(--red)' : h.signal.includes('卖出') ? 'var(--green)' : 'var(--text-dim)'}">${h.signal}</td>` +
          `<td>${h.trend}</td><td>${h.price}</td><td>${h.stop_ref || '—'}</td>` +
          `<td>${h.above_stop ? '✅' : '❌'}</td></tr>`;
      }).join('');
      $('fundChecks').innerHTML = r.checks.map(c =>
        `<div class="chk">${c.pass ? '✅' : '❌'} ${c.name} <span style="color:var(--text-dim);font-size:12px;">(${c.detail})</span></div>`).join('');
      $('fundVerdict').textContent = '🎯 ' + r.verdict;
      show('fundSection');
      toast('基金分析完成');
    } catch (e) {
      toast('基金分析失败: ' + e.message);
    } finally {
      setLoading('', false);
    }
  });

  // ---- 多股票监控 ----
  $('btnWatch').addEventListener('click', async () => {
    const symbols = $('symbol').value.trim();
    if (!symbols) { toast('请先输入股票代码'); return; }
    setLoading('正在获取多只股票信号...', true);
    try {
      const r = await api('/api/watchlist', { symbols });
      if (!r.ok) throw new Error(r.error);
      $('watchTag').textContent = `${r.rows.length} 只股票`;
      const tbody = $('watchTable').querySelector('tbody');
      tbody.innerHTML = r.rows.map(x => {
        if (!x.ok) return `<tr><td>${x.symbol}</td><td colspan="8" style="text-align:left;color:var(--red);">⚠ ${x.error}</td></tr>`;
        const cls = x.signal.includes('买入') ? 'buy' : x.signal.includes('卖出') ? 'sell' : x.signal.includes('持有') ? 'hold' : 'wait';
        return `<tr><td>${x.symbol}</td><td class="${cls}">${x.signal}</td><td>${x.price}</td>` +
          `<td>${x.trend}</td><td>${x.ma_fast}</td><td>${x.ma_slow}</td>` +
          `<td>${x.vol_ratio != null ? x.vol_ratio + 'x' : '—'}</td><td>${x.stop_ref || '—'}</td>` +
          `<td style="text-align:left;font-size:12px;color:var(--text-dim);">${x.reason}</td></tr>`;
      }).join('');
      show('watchSection');
      toast('监控面板已刷新');
    } catch (e) {
      toast('监控失败: ' + e.message);
    } finally {
      setLoading('', false);
    }
  });

  // ---- AI 综合研判 ----
  $('btnAdvisor').addEventListener('click', async () => {
    $('btnAdvisor').disabled = true;
    setLoading('AI 正在收集新闻和热点, 综合研判中(约30-90秒)...', true);
    try {
      const r = await (await fetch('/api/advisor')).json();
      if (!r.ok) throw new Error(r.error);
      $('advisorTag').textContent = `${r.symbol} · ${r.date}`;
      const v = $('advisorVerdict');
      v.textContent = `${r.verdict} · 置信度 ${r.confidence}%`;
      v.className = 'signal-text ' +
        (r.verdict.includes('看多') ? 'buy' : r.verdict.includes('看空') ? 'sell' : 'hold');
      $('advisorSummary').textContent = '💡 ' + r.summary;
      $('advisorConf').style.width = Math.max(4, Math.min(100, r.confidence)) + '%';
      $('advisorConfText').textContent = `置信度: ${r.confidence}%`;
      $('advisorReasons').innerHTML = (r.reasons || []).map(x => `<li>${x}</li>`).join('');
      $('advisorRisks').innerHTML = (r.risks || []).map(x => `<li>${x}</li>`).join('');
      $('advisorSectors').innerHTML = (r.hot_sectors || []).map(s => `<span>${s.name} ${s.pct > 0 ? '+' : ''}${s.pct}%</span>`).join('');
      $('advisorNews').innerHTML = (r.news || []).slice(0, 5).map(n => `<li>[${n.time}] ${n.title.slice(0, 40)}</li>`).join('');
      show('advisorSection');
      toast('AI 研判完成');
    } catch (e) {
      toast('研判失败: ' + e.message);
    } finally {
      $('btnAdvisor').disabled = false;
      setLoading('', false);
    }
  });

  // ---- 今日信号 ----
  $('btnSignal').addEventListener('click', async () => {
    try {
      const r = await (await fetch('/api/signal')).json();
      if (!r.ok) throw new Error(r.error);
      $('signalTag').textContent = `${r.symbol} · ${r.date}`;
      const st = $('signalText');
      st.textContent = r.signal;
      st.className = 'signal-text ' +
        (r.signal.includes('买入') ? 'buy' : r.signal.includes('卖出') ? 'sell' : r.signal.includes('持有') ? 'hold' : 'wait');
      $('signalReason').textContent = '💡 ' + r.reason +
        `（规则: 快线${r.rule.fast}/慢线${r.rule.slow}/止损${r.rule.stop_loss || 0}/量过滤${r.rule.volume_filter || 0}）`;
      $('sigPrice').textContent = r.price;
      $('sigTrend').textContent = r.trend;
      $('sigMaf').textContent = r.ma_fast;
      $('sigMas').textContent = r.ma_slow;
      $('sigVol').textContent = r.vol_ratio != null ? r.vol_ratio + 'x' : '—';
      $('sigStop').textContent = r.stop_ref || '—';
      show('signalSection');
    } catch (e) {
      toast('信号获取失败: ' + e.message);
    }
  });

  // ---- 启动自动迭代 ----
  $('btnIterate').addEventListener('click', async () => {
    const symbol = $('symbol').value.trim();
    const minutes = parseInt($('minutes').value, 10);
    if (!/^\d{6}$/.test(symbol)) { toast('股票代码需为 6 位数字'); return; }
    if (!(minutes >= 1 && minutes <= 600)) { toast('迭代时长需在 1~600 分钟之间'); return; }
    try {
      const r = await api('/api/iteration/start', { symbol, minutes });
      if (!r.ok) throw new Error(r.error);
      toast(r.msg);
      setTimeout(refreshIteration, 2000);
    } catch (e) {
      toast('启动失败: ' + e.message);
    }
  });

  // ---- 自动迭代系统进度轮询 ----
  function fmtTime(sec) {
    sec = Math.max(0, Math.round(sec || 0));
    const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
    return (h > 0 ? h + ':' : '') + String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
  }
  async function refreshIteration() {
    try {
      const s = await (await fetch('/api/iteration/status')).json();
      const box = $('iterSection');
      if (!s.running || !s.best) { box.classList.add('hidden'); return; }
      box.classList.remove('hidden');
      $('iterRound').textContent = s.round;
      $('iterTime').textContent = fmtTime(s.elapsed_sec) + ' / ' + fmtTime(s.total_sec);
      $('iterBar').style.width = Math.min(100, (s.elapsed_sec / s.total_sec) * 100) + '%';
      $('iterScore').textContent = s.best.score;
      $('iterAnn').textContent = (s.best['年化%'] != null ? s.best['年化%'].toFixed(2) + '%' : '—');
      $('iterBest').textContent =
        `🤖 当前最优: 快线${s.best.fast} 慢线${s.best.slow} 止损${s.best.stop_loss || 0} 量过滤${s.best.volume_filter || 0}` +
        ` · 年化 ${s.best['年化%'] != null ? s.best['年化%'].toFixed(2) + '%' : '—'}` +
        ` · 回撤 ${s.best['回撤%'] != null ? s.best['回撤%'].toFixed(2) + '%' : '—'}` +
        ` · 胜率 ${s.best['胜率'] || '—'}` +
        (s.best['测试年化%'] != null ? ` · 闭卷测试年化 ${s.best['测试年化%'].toFixed(2)}%` : '');
      const h = await (await fetch('/api/iteration/history')).json();
      const tbody = $('iterTable').querySelector('tbody');
      const rows = (h.rows || []).slice(-8).reverse();
      tbody.innerHTML = rows.map(r =>
        `<tr><td>${r.round}</td><td>${r.source === 'ai' ? '🤖AI' : '🎲随机'}</td>` +
        `<td>${r.fast}</td><td>${r.slow}</td><td>${r.stop_loss || 0}</td><td>${r.volume_filter || 0}</td>` +
        `<td>${r.score}</td><td>${r['修正分'] != null ? r['修正分'] : '—'}</td>` +
        `<td>${r['年化%']}</td><td>${r['回撤%']}</td></tr>`).join('');
    } catch (e) { /* 服务未启动时静默 */ }
  }
  refreshIteration();
  setInterval(refreshIteration, 10000);
})();
