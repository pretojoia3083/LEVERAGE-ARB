const $ = id => document.getElementById(id);
const EX_COLORS = {
  binance: '#F0B90B', bybit: '#F7A600', bitget: '#1EC6A7', kucoin: '#01C8C8',
  okx: '#7CC4FF', gate: '#31C4FE', mexc: '#4DD0E1', htx: '#FF6D6D',
  kraken: '#B08CFF', mercadobitcoin: '#25B9A5', bitso: '#37E2B2',
};

let AUTO_ON = false;
let MODE = 'paper';

window.toggleAuto = async function() {
  const btn = $('autoBtn');
  btn.textContent = 'Carregando...';
  btn.disabled = true;
  const res = await api('/api/auto', { method: 'POST' });
  AUTO_ON = res.auto_trade;
  updateAutoUI();
  btn.disabled = false;
};

window.toggleMode = async function() {
  const btn = $('modeBtn');
  btn.textContent = 'Carregando...';
  btn.disabled = true;
  const res = await api('/api/mode', { method: 'POST' });
  MODE = res.mode;
  updateModeUI();
  btn.disabled = false;
};

function updateModeUI() {
  const btn = $('modeBtn');
  const label = $('modeLabel');
  const wrap = $('modeWrap');
  if (btn) {
    if (MODE === 'real') { btn.textContent = '🔴 REAL'; btn.className = 'toggle-btn active-red'; }
    else if (MODE === 'demo') { btn.textContent = '🎬 Demo'; btn.className = 'toggle-btn active-orange'; }
    else { btn.textContent = '📝 Paper'; btn.className = 'toggle-btn'; }
  }
  if (label) label.textContent = MODE === 'real' ? 'Modo: REAL' : MODE === 'demo' ? 'Modo: Demo' : 'Modo: Paper';
  if (wrap) wrap.classList.toggle('real', MODE === 'real');
}

function updateAutoUI() {
  const btn = $('autoBtn');
  const label = $('autoLabel');
  if (btn) {
    btn.textContent = AUTO_ON ? '🤖 Auto ON' : '✋ Manual';
    btn.className = 'toggle-btn ' + (AUTO_ON ? 'active-green' : '');
  }
  if (label) label.textContent = AUTO_ON ? 'Auto: ON' : 'Auto: OFF';
  const rb = $('robotBadge');
  if (AUTO_ON) {
    rb.style.display = 'block';
    rb.innerHTML = MODE === 'real' ? '🔴 AUTO REAL LIGADO' : '🤖 Auto-TRADE LIGADO';
  } else {
    rb.style.display = 'none';
  }
}

function playBeep(frequency = 440, duration = 0.2) {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const oscillator = ctx.createOscillator();
    const gainNode = ctx.createGain();
    oscillator.connect(gainNode);
    gainNode.connect(ctx.destination);
    oscillator.frequency.value = frequency;
    gainNode.gain.value = 0.1;
    oscillator.start();
    oscillator.stop(ctx.currentTime + duration);
  } catch (e) { /* silencioso se falhar (ex: usuário bloqueou áudio) */ }
}

function fmtBrl(v) {
  const n = Number(v) || 0;
  const sign = n < 0 ? '-' : '';
  // valores de trade do par USDT/BRL sao em BRL (moeda de cotacao)
  return `${sign}R$${Math.abs(n).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
function fmtPrice(v) {
  const n = Number(v) || 0;
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
}
function exBadge(name) {
  const color = EX_COLORS[name] || 'var(--text)';
  return `<span class="ex-badge" style="color:${color}">${name}</span>`;
}
function fmtTime(sec) {
  sec = Math.round(Number(sec) || 0);
  if (!sec) return '—';
  if (sec < 60) return `${sec}s`;
  return `${Math.floor(sec / 60)}min ${String(sec % 60).padStart(2, '0')}s`;
}

// tempo da execução: em paper/demo a operação é instantânea,
// então mostra o tempo estimado de verdade (com a transferência)
function xTime(x) {
  const ms = Number(x.elapsed_ms) || 0;
  const est = Number(x.est_real_seconds) || 0;
  if (x.mode === 'paper' || ms < 1000) {
    return `<span class="badge badge-orange" title="tempo estimado com transferência">⏱ ~${fmtTime(est)} (est.)</span>`;
  }
  return `<span class="badge badge-green">⏱ ${(ms / 1000).toFixed(1)}s</span>`;
}

let DASH = null;
let totalSimOld = 0;

async function api(path, opts) {
  const r = await fetch(path, opts);
  return r.json();
}

/* ---------- TABS ---------- */
document.querySelectorAll('.menu-item').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.menu-item').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    $(`tab-${btn.dataset.tab}`).classList.add('active');
    if (btn.dataset.tab === 'analytics' || btn.dataset.tab === 'historico') loadHistory();
    if (btn.dataset.tab === 'saldo') loadBalances();
    if (btn.dataset.tab === 'oportunidades') loadDex();
    if (btn.dataset.tab === 'demobot') loadDemo();
    if (btn.dataset.tab === 'monitor') loadSummary();
    if (btn.dataset.tab === 'configuracao') { loadSettings(); }
  });
});

/* ---------- SCANNER ---------- */
function renderBest(best) {
  const el = $('bestPanel');
  if (!best) {
    el.className = 'best-empty muted';
    el.textContent = 'Nenhuma oportunidade no momento.';
    return;
  }
  el.className = '';
  el.innerHTML = `
    <div class="best-compact">
      <div class="best-route-row" style="padding:0 20px 16px;flex-wrap:wrap;gap:8px;align-items:center">
        ${exBadge(best.buy_exchange)} <span class="muted small">@${fmtPrice(best.buy_price)}</span>
        <span class="arrow">→</span>
        ${exBadge(best.sell_exchange)} <span class="muted small">@${fmtPrice(best.sell_price)}</span>
        <span class="badge badge-green" style="margin-left:auto">${best.gross_pct}% spread</span>
        <span class="badge badge-orange">⏱ ${best.est_time_fmt}</span>
        <b class="${best.net_usdt >= 0 ? 'green' : 'red'} font-display" style="font-size:18px">${fmtBrl(best.net_usdt)}</b>
        <button class="btn-exec" onclick="execRoute('${best.pair}','${best.buy_exchange}','${best.sell_exchange}')">⚡ Executar</button>
      </div>
    </div>`;
}

function renderOpps(list) {
  $('oppCount').textContent = list.length ? `${list.length} rotas com spread` : '';
  const oi = $('oppInvest');
  if (oi) oi.textContent = (DASH && DASH.investment) ? `· lucro calculado com ${fmtBrl(DASH.investment)} (troca no LeverageBot)` : '';
  const body = $('oppsBody');
  if (!list.length) {
    body.innerHTML = `<tr><td colspan="9" style="text-align:center;padding:36px" class="muted">Sem oportunidades agora — o scanner continua monitorando...</td></tr>`;
    return;
  }
  body.innerHTML = list.map(o => `
    <tr>
      <td><b>${o.pair}</b></td>
      <td><div class="route-cell">${exBadge(o.buy_exchange)}<span class="arrow">@${fmtPrice(o.buy_price)}</span></div></td>
      <td><div class="route-cell">${exBadge(o.sell_exchange)}<span class="arrow">@${fmtPrice(o.sell_price)}</span></div></td>
      <td><span class="badge badge-green">${o.gross_pct}%</span></td>
      <td><b>${o.network}</b> <span class="muted small">($${o.networks.find(n => n.network === o.network)?.withdrawal_fee_usd})</span></td>
      <td class="muted">${((o.taker_buy + o.taker_sell) * 100).toFixed(2)}%</td>
      <td><span class="badge badge-orange">⏱ ${o.est_time_fmt}</span></td>
      <td class="right"><b class="${o.net_usdt >= 0 ? 'green' : 'red'}">${fmtBrl(o.net_usdt)}</b><br><span class="muted small">${o.net_pct}%</span></td>
      <td><div class="exec-actions">
        <button class="btn-mini" onclick="fillSim('${o.pair}','${o.buy_exchange}','${o.sell_exchange}')">🧪</button>
        <button class="btn-exec" onclick="execRoute('${o.pair}','${o.buy_exchange}','${o.sell_exchange}')">⚡ Executar</button>
      </div></td>
    </tr>`).join('');
}

function renderPrices(prices, opps, exchangesOk) {
  const grid = $('pricesGrid');
  if (!grid) return;

  const activeExs = new Set();
  (opps || []).forEach(o => {
    activeExs.add(o.buy_exchange);
    activeExs.add(o.sell_exchange);
  });

  const ALL_EX = ['binance', 'bybit', 'bitget', 'okx', 'gate', 'mexc', 'kucoin', 'kraken', 'mercadobitcoin'];
  grid.innerHTML = ALL_EX.map(ex => {
    const isConnected = (exchangesOk || []).includes(ex) || ex === 'mercadobitcoin';
    const data = prices && prices[ex];
    const pair = data && data['USDT/BRL'];
    const isActive = activeExs.has(ex);
    const isMB = ex === 'mercadobitcoin';

    if (!pair || !pair.ask) {
      const noPair = !isConnected && /gate|kucoin|kraken/i.test(ex);
      return `<div class="price-card${isConnected ? '' : ' offline'}">
        <div class="ex-name" style="color:${EX_COLORS[ex] || 'var(--text)'}">${ex}</div>
        <div class="price-ask muted">${noPair ? 'sem par BRL' : (isConnected ? 'aguardando...' : 'offline')}</div>
      </div>`;
    }
    const spread = pair.ask && pair.bid ? (((pair.ask - pair.bid) / pair.bid) * 100).toFixed(3) : '—';
    const vol = pair.volume ? `<div class="price-vol">vol 24h $${Number(pair.volume).toLocaleString('en-US', { maximumFractionDigits: 0 })}</div>` : '';
    return `<div class="price-card${isActive ? ' active' : ''}">
      <div class="ex-name" style="color:${EX_COLORS[ex] || 'var(--text)'}">${ex}</div>
      <div class="price-ask">ask ${fmtPrice(pair.ask)}</div>
      <div class="price-bid">bid ${fmtPrice(pair.bid)}</div>
      <div class="price-spread">spread ${spread}%</div>
      ${vol}
      ${isActive ? '<div class="price-tag">OPORTUNIDADE</div>' : ''}
    </div>`;
  }).join('');
}

function renderNearMiss(list, minSpread) {
  const card = $('nearCard');
  const body = $('nearBody');
  if (!card || !body) return;
  const rows = (list || []).slice(0, 3);
  if (!rows.length) { card.style.display = 'none'; return; }
  card.style.display = 'block';
  const min = Number(minSpread || 0);
  body.innerHTML = rows.map(n => {
    const faltaPct = (min - n.net_pct).toFixed(4);
    const faltaBrl = Math.abs(n.net_usdt) < 0.005 ? '—' : fmtBrl(Math.abs(n.net_usdt) * (1 + min / Math.max(n.net_pct, 0.0001)));
    return `<div class="pending-row">
      <span>${exBadge(n.buy_exchange)} @${fmtPrice(n.buy_price)} → ${exBadge(n.sell_exchange)} @${fmtPrice(n.sell_price)}
        <span class="muted small">· ${n.network} · taxas ${((n.taker_buy + n.taker_sell) * 100).toFixed(2)}%</span></span>
      <b class="${n.net_usdt >= 0 ? 'green' : 'red'}">${fmtBrl(n.net_usdt)} (${n.net_pct}%)</b>
      <span class="muted small">faltam ${faltaPct}% para ${min}%</span>
    </div>`;
  }).join('');
}

async function pollDashboard() {
  try {
    const d = await api('/api/dashboard');
    if (DASH && DASH.total_simulations_old === undefined) {
      DASH.total_simulations_old = d.total_simulations;
    }
    DASH = d;

    AUTO_ON = d.auto_trade;
    MODE = d.mode || 'paper';
    updateAutoUI();
    updateModeUI();

    const badge = $('connBadge');
    if (d.connected) badge.innerHTML = '<span class="dot on"></span> Scanner ao vivo';
    else badge.innerHTML = '<span class="dot gray"></span> Conectando...';

    $('stOpps').textContent = d.total_opportunities;
    $('stScan').textContent = d.last_scan
      ? `varredura em ${d.scan_seconds}s · ${d.exchanges_ok.length} corretoras`
      : 'aguardando primeira varredura...';

    const b = d.best;
    $('stBest').textContent = b ? fmtBrl(b.net_usdt) : '—';
    $('stBest').className = `card-value font-display ${b ? (b.net_usdt >= 0 ? 'green' : 'red') : ''}`;
    $('stBestSub').textContent = b ? `${b.pair} · ${b.buy_exchange} → ${b.sell_exchange}` : 'esperando spread';

    renderBest(b);
    renderOpps(d.opportunities || []);
    renderNearMiss(d.near_miss || [], d.min_spread);
    renderPrices(d.prices, d.opportunities || [], d.exchanges_ok || []);
    renderSpreadPills(d.min_spread, d.spread_options);
    renderSpreadPills(d.min_spread, d.spread_options, 'demoSpreadPills');
    fillSimSelects();
    renderBalSummary(d.balances || {});
    renderPending(d.pending_transfers || []);
    calcProfit();

    if ($('investInput') && d.investment && document.activeElement !== $('investInput')) {
      $('investInput').value = d.investment;
    }
    if ($('demoInvestInput') && d.investment && document.activeElement !== $('demoInvestInput')) {
      $('demoInvestInput').value = d.investment;
    }
    if ($('cotUpdated') && d.last_scan) {
      $('cotUpdated').textContent = `atualizado ${new Date(d.last_scan).toLocaleTimeString('pt-BR')} · ${(d.exchanges_ok || []).length} corretoras`;
    }
    const foot = $('footEx');
    if (foot) foot.textContent = `${(d.exchanges_ok || []).length} corretoras · USDT/BRL`;

    if (b && b.net_usdt > 0) {
      const rb = $('robotBadge');
      rb.style.display = 'block';
      rb.innerHTML = `🤖 ${b.pair} ${b.buy_exchange}→${b.sell_exchange} +${b.net_pct}%`;
    } else if (!AUTO_ON) {
      $('robotBadge').style.display = 'none';
    }

    if (AUTO_ON) {
      const rb = $('robotBadge');
      rb.style.display = 'block';
      rb.innerHTML = MODE === 'real' ? '🔴 AUTO REAL LIGADO' : '🤖 Auto-TRADE LIGADO';
    } else {
      $('robotBadge').style.display = 'none';
    }

    if (d.total_simulations && d.total_simulations > totalSimOld) {
      playBeep(660, 0.15);
      const rb = $('robotBadge');
      rb.style.display = 'block';
      rb.innerHTML = '🤖 Nova simulação gravada!';
      setTimeout(() => { rb.style.display = 'none'; }, 4000);
    }
    totalSimOld = d.total_simulations || 0;
  } catch (e) { /* servidor ainda subindo */ }
}

/* ---------- SIMULADOR ---------- */
let SIM_SIG = '';
function fillSimSelects() {
  if (!DASH) return;
  const pricesWithData = {};
  for (const [ex, data] of Object.entries(DASH.prices || {})) {
    if (data && data['USDT/BRL'] && data['USDT/BRL'].ask) {
      pricesWithData[ex] = data;
    }
  }
  const pairs = Object.keys(
    Object.values(pricesWithData)[0] || {}
  ).sort();
  const exs = Object.keys(pricesWithData);
  // nao reconstrói a cada 5s (preserva o que o usuário escolheu)
  const sig = pairs.join(',') + '|' + exs.join(',');
  if (sig === SIM_SIG) return;
  SIM_SIG = sig;

  // padrão inteligente: compra no ask mais barato, vende no bid mais alto
  let defBuy = exs[0] || '', defSell = exs[0] || '';
  let bestAsk = Infinity, bestBid = 0, secondBid = 0, secondBidEx = '';
  for (const ex of exs) {
    const p = pricesWithData[ex]['USDT/BRL'];
    if (p.ask < bestAsk) { bestAsk = p.ask; defBuy = ex; }
    if (p.bid > bestBid) { secondBid = bestBid; secondBidEx = defSell; bestBid = p.bid; defSell = ex; }
    else if (p.bid > secondBid) { secondBid = p.bid; secondBidEx = ex; }
  }
  if (defSell === defBuy && secondBidEx) defSell = secondBidEx;

  const keep = (sel, arr, val, def) => {
    if (!sel) return;
    sel.innerHTML = arr.map(x => `<option value="${x}">${x}</option>`).join('');
    if (val && arr.includes(val)) sel.value = val;
    else if (def && arr.includes(def)) sel.value = def;
    else if (arr.length) sel.value = arr[0];
  };
  keep($('simPair'), pairs.length ? pairs : ['USDT/BRL'], $('simPair').value, 'USDT/BRL');
  keep($('simBuy'), exs, $('simBuy').value, defBuy);
  keep($('simSell'), exs, $('simSell').value, defSell);
}

window.fillSim = function (pair, buyEx, sellEx) {
  document.querySelector('[data-tab="oportunidades"]').click();
  fillSimSelects();
  setTimeout(() => {
    $('simPair').value = pair;
    $('simBuy').value = buyEx;
    $('simSell').value = sellEx;
    runSim();
  }, 50);
};

async function runSim() {
  const box = $('simResult');
  const payload = {
    pair: $('simPair').value,
    buy_exchange: $('simBuy').value,
    sell_exchange: $('simSell').value,
    invest_usdt: parseFloat($('simInvest').value) || 1000,
    network: $('simNetwork').value,
  };
  if (!payload.pair || !payload.buy_exchange || !payload.sell_exchange) {
    box.className = 'muted';
    box.textContent = 'Aguarde carregar os preços das corretoras...';
    return;
  }
  const res = await api('/api/simulate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (res.error) {
    box.className = 'red';
    box.textContent = res.error;
    return;
  }

  const rows = res.networks.map(n => `
    <tr class="${n.network === res.network ? 'best-net' : ''}">
      <td><b>${n.network}</b> ${n.network === res.network ? '<span class="tag-best">MELHOR</span>' : ''}</td>
      <td>$${n.withdrawal_fee_usd.toFixed(2)}</td>
      <td>${fmtTime(n.est_seconds)}</td>
      <td class="${n.net_usdt >= 0 ? 'green' : 'red'}"><b>${fmtBrl(n.net_usdt)}</b></td>
      <td class="${n.net_pct >= 0 ? 'green' : 'red'}">${n.net_pct}%</td>
    </tr>`).join('');

  box.innerHTML = `
    <div class="sim-breakdown fade-in-up">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px">
        <span class="font-display" style="font-size:22px;font-weight:700">${res.pair}</span>
        <span class="badge badge-green">${res.gross_pct}% bruto · ${res.net_pct}% líquido</span>
      </div>
      <div style="display:flex;gap:16px;flex-wrap:wrap">
        <div>${exBadge(res.buy_exchange || payload.buy_exchange)} <span class="muted small">compra @${fmtPrice(res.buy_price)}</span></div>
        <span class="arrow">→</span>
        <div>${exBadge(payload.sell_exchange)} <span class="muted small">venda @${fmtPrice(res.sell_price)}</span></div>
      </div>
      <div class="best-row"><span>Quantidade comprada</span><b>${res.quantity} ${res.asset}</b></div>
      <div class="best-row"><span>Taxas taker (compra+venda)</span><b>${((res.taker_buy + res.taker_sell) * 100).toFixed(3)}%</b></div>
      <div class="best-row"><span>Rede selecionada</span><b>${res.network}</b></div>
      <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-top:6px">
        <span class="time-chip">⏱ Tempo total estimado: ${res.est_time_fmt}</span>
        <span style="font-size:20px">=</span>
        <span class="net-big font-display ${res.net_usdt >= 0 ? 'green' : 'red'}">${fmtBrl(res.net_usdt)}</span>
      </div>
      <table class="net-table">
        <thead><tr><th>Rede</th><th>Taxa saque</th><th>Tempo transfer.</th><th>Lucro líq.</th><th>%</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

$('simRun').addEventListener('click', runSim);

/* ---------- EXECUÇÃO ---------- */
window.execRoute = async function (pair, buyEx, sellEx) {
  const toast = $('execToast');
  toast.innerHTML = '<h3>⚡ Executando operação...</h3><div class="muted small">' +
    `${pair} · ${buyEx} → ${sellEx}</div>`;
  toast.classList.add('show');
  const res = await api('/api/execute', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      pair, buy_exchange: buyEx, sell_exchange: sellEx,
      invest_usdt: parseFloat($('simInvest').value) || 1000,
      network: $('simNetwork').value,
    }),
  });
  if (!res.ok) {
    toast.innerHTML = `<h3 class="red">✕ Erro</h3><div class="muted small">${res.error || 'falhou'}</div>`;
    setTimeout(() => toast.classList.remove('show'), 4000);
    return;
  }
  playBeep(880, 0.3); // bip de confirmação
  toast.innerHTML = `
    <h3 class="green">✔ Operação executada (#${res.id})</h3>
    <div class="row"><span>Rota</span><b>${res.pair} · ${res.buy_exchange} → ${res.sell_exchange}</b></div>
    <div class="row"><span>Rede</span><b>${res.network}</b></div>
    <div class="row"><span>Lucro líquido</span><b class="${res.net_usdt >= 0 ? 'green' : 'red'}">${fmtBrl(res.net_usdt)} (${res.net_pct}%)</b></div>
    <div class="row"><span>⏱ Tempo em dinheiro real (com transferência)</span><b>~${fmtTime(res.est_real_seconds)}</b></div>
    <div class="muted" style="font-size:11px;margin-top:8px">Modo paper-trade: preços reais, ordens simuladas.</div>`;
  setTimeout(() => toast.classList.remove('show'), 9000);
};

/* ---------- HISTÓRICO ---------- */
async function loadHistory() {
  const [hist, stats, execs] = await Promise.all([
    api('/api/simulations?limit=200'), api('/api/stats'), api('/api/executions?limit=100'),
  ]);
  $('hsCount').textContent = (stats.total_simulations ?? 0) + (stats.total_executions ?? 0);
  $('hsTotal').textContent = fmtBrl((stats.total_net_usdt ?? 0) + (stats.total_executed_net ?? 0));
  $('stSims').textContent = stats.total_simulations ?? 0;
  $('stProfit').textContent = fmtBrl(stats.total_net_usdt ?? 0);
  $('stProfit').className = `card-value font-display ${(stats.total_net_usdt ?? 0) >= 0 ? 'green' : 'red'}`;
  $('stAvg').textContent = `${stats.avg_net_pct ?? 0}% média por operação`;
  const br = stats.best_route;
  if (br) {
    $('hsBest').textContent = `${br.pair} +$${br.net_usdt}`;
    $('hsBestSub').textContent = `${br.buy_exchange} → ${br.sell_exchange} via ${br.network}`;
  }

  const rows = (hist.data || []).map(h => `
    <tr>
      <td class="muted">${h.ts ? h.ts.replace('T', ' ').slice(5, 16) : ''}</td>
      <td><span class="badge ${h.trigger === 'auto' ? 'badge-orange' : 'badge-green'}">${h.trigger}</span></td>
      <td><b>${h.pair}</b></td>
      <td><div class="route-cell">${exBadge(h.buy_exchange)}<span class="arrow">→</span>${exBadge(h.sell_exchange)}</div></td>
      <td>${h.network}</td>
      <td>${h.gross_pct}%</td>
      <td>${fmtBrl(h.invest_usdt)}</td>
      <td>${fmtTime(h.est_seconds)}</td>
      <td class="right"><b class="${h.net_usdt >= 0 ? 'green' : 'red'}">${fmtBrl(h.net_usdt)}</b></td>
    </tr>`).join('');
  $('histBody').innerHTML = rows ||
    `<tr><td colspan="9" style="text-align:center;padding:36px" class="muted">Nenhuma operação registrada ainda. O sistema registra automaticamente oportunidades ≥ 0.10% de lucro líquido.</td></tr>`;

  const exRows = (execs.data || []).map(x => `
    <tr>
      <td class="muted">${x.ts ? x.ts.replace('T', ' ').slice(5, 16) : ''}</td>
      <td><b>${x.pair}</b></td>
      <td><div class="route-cell">${exBadge(x.buy_exchange)}<span class="arrow">→</span>${exBadge(x.sell_exchange)}</div></td>
      <td>${x.network}</td>
      <td><span class="badge badge-orange">${x.mode}</span></td>
      <td>${fmtBrl(x.invest_usdt)}</td>
      <td>${xTime(x)}</td>
      <td class="right"><b class="${x.net_usdt >= 0 ? 'green' : 'red'}">${fmtBrl(x.net_usdt)}</b></td>
    </tr>`).join('');
  $('execBody').innerHTML = exRows ||
    `<tr><td colspan="8" style="text-align:center;padding:36px" class="muted">Nenhuma execução ainda — clique em ⚡ Executar numa oportunidade.</td></tr>`;
}

$('btnClear').addEventListener('click', async () => {
  if (!confirm('Apagar todo o histórico de simulações?')) return;
  await api('/api/simulations', { method: 'DELETE' });
  loadHistory();
});

/* ---------- RESUMO DO BOT (Monitor) ---------- */
function renderSummary(d, st) {
  const mode = (d && d.mode) || 'paper';
  const byMode = (st && st.by_mode) || {};
  const daily = (st && st.daily) || {};
  const dia = daily.dia || { ops: 0, net: 0 };
  const acum = daily.acumulado || { ops: 0, net: 0 };
  const demo = byMode.demo || { ops: 0, net: 0 };
  const real = byMode.real || { ops: 0, net: 0 };

  const modoTxt = $('sumMode');
  if (modoTxt) {
    modoTxt.textContent = mode === 'demo'
      ? '🎬 DEMO — dinheiro fictício, serve para você avaliar o resultado'
      : mode === 'real'
        ? '🔴 REAL — operações de verdade'
        : '📝 PAPER — apenas simulação';
  }

  // lucro de hoje (zera à meia-noite) e acumulado (nunca zera)
  const setVal = (id, v, suffix) => {
    const el = $(id);
    if (!el) return;
    el.textContent = fmtBrl(v);
    el.className = 'card-value font-display ' + (v > 0 ? 'green' : v < 0 ? 'red' : '');
  };
  setVal('sumDia', dia.net || 0);
  setVal('sumAcum', acum.net || 0);

  // saldo: capital unico que gira entre as corretoras
  const saldoEl = $('sumSaldo');
  const wbox = $('sumWallet');
  const saldos = (st && st.saldos) || null;
  if (saldoEl) {
    const v = st ? (st.capital ?? st.total_brl ?? 0) : 0;
    saldoEl.textContent = fmtBrl(v);
    saldoEl.className = 'card-value font-display ' + (v > 0 ? 'green' : '');
  }
  if (wbox) {
    const base = saldos && Object.keys(saldos).length ? saldos : (st && st.wallet) || {};
    const chaves = Object.keys(base);
    wbox.innerHTML = chaves.length ? chaves.map(ex => `
      <div class="balance-card">
        <div class="balance-card-header">
          <span class="ex-name" style="color:${EX_COLORS[ex] || 'var(--text)'}">${ex}</span>
          <span class="bal-status ok">✓</span>
        </div>
        <div class="balance-coin"><span class="balance-coin-name">BRL</span><span class="balance-coin-free">${fmtBrl(base[ex].BRL)}</span></div>
        <div class="balance-coin"><span class="balance-coin-name">USDT</span><span class="balance-coin-free">${(base[ex].USDT || 0).toFixed(2)}</span></div>
      </div>`).join('') : '<div class="balance-empty">configure a API key de uma corretora para o bot usar seu saldo real</div>';
  }

  const opsEl = $('sumOps');
  if (opsEl) opsEl.textContent = dia.ops || 0;

  const bEl = $('sumBest');
  if (bEl) bEl.textContent = daily.melhor_hoje ? fmtBrl(daily.melhor_hoje.net_usdt) : '—';
}

async function loadSummary() {
  try {
    const [st, demo] = await Promise.all([api('/api/stats'), api('/api/demo/status')]);
    const d = DASH || await api('/api/dashboard');
    renderSummary(d, Object.assign({}, st, {
      wallet: demo.wallet, total_brl: demo.total_brl,
    }));
  } catch (e) { /* servidor subindo */ }
}

/* ---------- BOOT ---------- */
pollDashboard();
setInterval(pollDashboard, 5000);
setInterval(() => {
  if ($('tab-historico').classList.contains('active')) loadHistory();
  if ($('tab-demobot').classList.contains('active')) loadDemo();
  if ($('tab-monitor').classList.contains('active')) loadSummary();
}, 8000);
setInterval(() => {
  if ($('tab-oportunidades').classList.contains('active')) loadDex();
}, 30000);

/* ---------- SPREAD MINIMO ---------- */
function renderSpreadPills(current, options, boxId) {
  const box = $(boxId || 'spreadPills');
  if (!box) return;
  const opts = options && options.length ? options : [0.00, 0.02, 0.05, 0.10, 0.20, 0.50, 1.0, 2.0];
  box.innerHTML = opts.map(v => `
    <button class="spread-pill${Number(current) === Number(v) ? ' active' : ''}"
      onclick="setSpread(${v})">${Number(v).toFixed(2)}%</button>`).join('');
  for (const mid of ['spreadManual', 'demoSpreadManual']) {
    const man = $(mid);
    if (man && document.activeElement !== man && !opts.some(v => Number(v) === Number(current))) {
      man.value = current;
    }
  }
}

async function doSaveSpread(v, msgId) {
  const msg = msgId ? $(msgId) : null;
  if (!(v >= 0) || v > 5) {
    if (msg) { msg.textContent = 'Digite um valor de 0 a 5'; msg.style.color = 'var(--red)'; }
    return;
  }
  const res = await api('/api/spread', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ min_spread: v }),
  });
  if (res.ok) {
    const opts = (DASH && DASH.spread_options) || [0.00, 0.02, 0.05, 0.10, 0.20, 0.50, 1.0, 2.0];
    renderSpreadPills(res.min_spread, opts);
    renderSpreadPills(res.min_spread, opts, 'demoSpreadPills');
    if (DASH) DASH.min_spread = res.min_spread;
    if (msg) { msg.textContent = `✓ Spread ${v}% salvo — o bot só entra acima disso`; msg.style.color = 'var(--green)'; }
    setTimeout(() => { if (msg) msg.textContent = ''; }, 4000);
    pollDashboard();
  } else if (msg) {
    msg.textContent = '✗ ' + (res.error || 'erro');
    msg.style.color = 'var(--red)';
  }
}

window.saveSpreadManual = async function() {
  const inp = $('spreadManual');
  await doSaveSpread(inp ? parseFloat(inp.value) : NaN, 'spreadMsg');
};

window.saveDemoSpread = async function() {
  const inp = $('demoSpreadManual');
  await doSaveSpread(inp ? parseFloat(inp.value) : NaN, 'demoSpreadMsg');
};

window.setSpread = async function(v) {
  const res = await api('/api/spread', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ min_spread: v }),
  });
  if (res.ok) {
    renderSpreadPills(res.min_spread, (DASH && DASH.spread_options) || [0.10, 0.20, 0.50, 1.0, 2.0]);
    if (DASH) DASH.min_spread = res.min_spread;
    pollDashboard();
  }
};

/* ---------- INVESTIMENTO ---------- */
async function doSaveInvestment(v, msgId) {
  const msg = msgId ? $(msgId) : null;
  const res = await api('/api/investment', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ invest_usdt: v }),
  });
  if (msg) {
    msg.textContent = res.ok ? `✓ Salvo! Oportunidades e bot passam a usar ${fmtBrl(res.invest_usdt || v)}` : ('✗ ' + (res.error || 'erro'));
    msg.style.color = res.ok ? 'var(--green)' : 'var(--red)';
    setTimeout(() => { if (msg) msg.textContent = ''; }, 4000);
  }
  if (res.ok) pollDashboard();
}

window.saveInvestment = async function() {
  await doSaveInvestment(parseFloat($('investInput').value) || 0, 'investMsg');
};

window.saveHome = async function() {
  const sel = $('homeSelect');
  const msg = $('homeMsg');
  const res = await api('/api/home', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ home: sel ? sel.value : 'auto' }),
  });
  if (msg) {
    msg.textContent = res.ok ? '✓ Salvo! O lucro volta pra ' + res.home : '✗ erro';
    msg.style.color = res.ok ? 'var(--green)' : 'var(--red)';
    setTimeout(() => { if (msg) msg.textContent = ''; }, 3500);
  }
  loadDemo();
};

window.toggleAllCapital = async function() {
  const btn = $('allCapitalBtn');
  const on = !(btn && btn.dataset.on === '1');
  const res = await api('/api/all-capital', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ value: on }),
  });
  if (res.ok) loadDemo();
};

window.saveDemoInvestment = async function() {
  await doSaveInvestment(parseFloat($('demoInvestInput').value) || 0, 'demoInvestMsg');
};

/* ---------- BOT DEMO ---------- */
async function loadDemo() {
  if (!$('demoState')) return;
  try {
    const [a, m, st] = await Promise.all([
      api('/api/auto'), api('/api/mode'), api('/api/demo/status'),
    ]);
    AUTO_ON = a.auto_trade;
    MODE = m.mode || 'paper';
    updateAutoUI();
    updateModeUI();
    const on = AUTO_ON && MODE === 'demo';
    $('demoState').textContent = on ? '● Rodando' : 'Desligado';
    $('demoState').className = 'card-value font-display ' + (on ? 'green' : 'orange');
    const rotas = Object.entries(st.routes_waiting || {});
    const home = st.home_exchange && st.home_exchange !== 'auto' ? st.home_exchange : null;
    const esperaTxt = rotas.length
      ? `aguardando spread reacender: ${rotas.map(([r, m2]) => `${r} (${m2}min)`).join(', ')}`
      : (home ? `entra quando comprar barato e vender na ${home} for favorável`
              : 'entrando sozinho quando o spread estiver favorável');
    $('demoStateSub').textContent = on ? esperaTxt : 'clique em Ligar pra começar';

    const btn = $('demoToggleBtn');
    if (btn) {
      btn.textContent = on ? '⏹ Desligar BOT Demo' : '▶ Ligar BOT Demo';
      btn.className = 'toggle-btn ' + (on ? 'active-green' : '');
    }
    if (DASH) {
      $('demoSpread').textContent = (st.spread_alvo ?? DASH.min_spread ?? 0.1) + '%';
      $('demoInvest').textContent = fmtBrl(DASH.investment ?? 50);
    }

    // corretora principal (hub)
    const sel = $('homeSelect');
    if (sel) {
      const opts = ['auto', 'binance', 'bitget', 'okx', 'mexc', 'mercadobitcoin'];
      const exs = Array.from(new Set(opts.concat(Object.keys(DASH && DASH.prices || {}))))
        .filter(x => x === 'auto' || (DASH && DASH.prices && DASH.prices[x]));
      if (!sel.dataset.ready) {
        sel.innerHTML = exs.map(x => `<option value="${x}">${x === 'auto' ? 'Automática (qualquer par)' : x}</option>`).join('');
        sel.dataset.ready = '1';
      }
      const want = (st.home_exchange && st.home_exchange !== 'auto') ? st.home_exchange : 'auto';
      if ([...sel.options].some(o => o.value === want)) sel.value = want;
    }

    // info de regras
    const info = $('demoOpInfo');
    if (info) {
      const partes = [`${st.ops_24h}/${st.max_per_day} operações hoje`];
      if (st.next_in_min > 0) partes.push(`próxima em ${st.next_in_min}min`);
      if (st.ref_spread !== null && st.ref_spread !== undefined) {
        partes.push(`último spread ${st.ref_spread}% (referência expira em ${st.ref_expira_em_min}min)`);
      }
      info.textContent = partes.join(' · ');
    }

    // carteira virtual
    const wbox = $('demoWallet');
    if (wbox) {
      const w = st.wallet || {};
      const chaves = Object.keys(w);
      wbox.innerHTML = chaves.length ? chaves.map(ex => `
        <div class="balance-card">
          <div class="balance-card-header">
            <span class="ex-name" style="color:${EX_COLORS[ex] || 'var(--text)'}">${ex}</span>
            <span class="bal-status ok">✓</span>
          </div>
          <div class="balance-coin"><span class="balance-coin-name">BRL</span><span class="balance-coin-free">${fmtBrl(w[ex].BRL)}</span></div>
          <div class="balance-coin"><span class="balance-coin-name">USDT</span><span class="balance-coin-free">${(w[ex].USDT || 0).toFixed(2)}</span></div>
        </div>`).join('') : '<div class="balance-empty">ligue o BOT Demo para ver o dinheiro se movendo</div>';
    }
    const acBtn = $('allCapitalBtn');
    if (acBtn) {
      const on = !!st.all_capital;
      acBtn.dataset.on = on ? '1' : '0';
      acBtn.textContent = on ? '💰 Usando todo o saldo' : '💰 Usar todo o saldo';
      acBtn.className = 'btn-mini' + (on ? ' active-green' : '');
      const ch = $('compoundHint');
      if (ch) {
        ch.textContent = on
          ? `juros compostos: cada arbitragem usa o saldo inteiro (R$${(st.capital || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}) e o lucro entra na próxima`
          : `valor fixo de R$${(DASH && DASH.investment) || 0} por operação`;
      }
    }

    // ranking: qual corretora principal da o melhor lucro liquido agora
    const rank = $('hubRank');
    if (rank) {
      const hubs = st.hubs || [];
      rank.innerHTML = hubs.length
        ? 'melhor principal agora: ' + hubs.slice(0, 4).map(h =>
            `<b style="color:${EX_COLORS[h.hub] || 'var(--text)'}">${h.hub}</b> ${h.net_pct >= 0 ? '+' : ''}${h.net_pct}%`
          ).join(' · ')
        : '';
    }

    const pend = ((DASH && DASH.pending_transfers) || []).filter(t => t.demo);
    const box = $('demoPending');
    if (!pend.length) {
      box.className = 'muted';
      box.textContent = on
        ? `Aguardando oportunidade acima de ${DASH ? DASH.min_spread : 0.10}% — ou clique em 🧪 Testar agora.`
        : 'Nenhuma operação demo agora.';
    } else {
      box.className = '';
      box.innerHTML = pend.map(t => `
        <div class="pending-card">
          <div class="pending-row"><span>Rota</span><b>${t.from} → ${t.to}</b></div>
          <div class="pending-row"><span>Quantidade</span><b>${t.qty} USDT</b></div>
          <div class="pending-row"><span>Rede</span><b>${t.network}</b></div>
          <div class="pending-row"><span>Vende sozinha em</span><b class="orange">⏱ ${t.seconds_left ?? '?'}s</b></div>
        </div>`).join('');
    }
    const ex = await api('/api/executions?limit=50');
    const demos = (ex.data || []).filter(x => x.mode === 'demo');
    $('demoExecBody').innerHTML = demos.map(x => `
      <tr>
        <td class="muted">${x.ts ? x.ts.replace('T', ' ').slice(5, 16) : ''}</td>
        <td><div class="route-cell">${exBadge(x.buy_exchange)}<span class="arrow">→</span>${exBadge(x.sell_exchange)}</div></td>
        <td>${x.network}</td>
        <td>${fmtBrl(x.invest_usdt)}</td>
        <td class="right"><b class="${x.net_usdt >= 0 ? 'green' : 'red'}">${fmtBrl(x.net_usdt)}</b><br><span class="muted small">${x.net_pct}%</span></td>
      </tr>`).join('') ||
      `<tr><td colspan="5" style="text-align:center;padding:24px" class="muted">Nenhuma demo ainda — ligue o BOT Demo.</td></tr>`;
  } catch (e) { /* servidor ainda subindo */ }
}

window.toggleDemo = async function() {
  const btn = $('demoToggleBtn');
  const sub = $('demoStateSub');
  if (btn) { btn.textContent = 'Carregando...'; btn.disabled = true; }
  try {
    const m = await api('/api/mode');
    if (!m || !m.mode) throw new Error('sem resposta do servidor');
    if (m.mode === 'demo') {
      await api('/api/auto', { method: 'POST' }); // liga/desliga mantendo demo
    } else {
      const set = await api('/api/mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: 'demo' }),
      });
      if (!set || set.mode !== 'demo') throw new Error('modo demo não ativou');
      const a = await api('/api/auto');
      if (!a.auto_trade) await api('/api/auto', { method: 'POST' });
    }
  } catch (e) {
    if (sub) sub.textContent = '✗ Erro: ' + (e.message || 'falhou — tente de novo');
  }
  if (btn) btn.disabled = false;
  await pollDashboard();
  loadDemo();
};

window.runDemoNow = async function() {
  const sub = $('demoStateSub');
  if (sub) sub.textContent = '⏳ Iniciando demo...';
  try {
    const res = await api('/api/demo/run', { method: 'POST' });
    if (res && res.ok) {
      if (sub) sub.textContent = `🎬 Demo ${res.buy_exchange} → ${res.sell_exchange} — vende sozinha em ~45s`;
    } else if (sub) {
      sub.textContent = '✗ ' + ((res && res.error) || 'falhou');
    }
  } catch (e) {
    if (sub) sub.textContent = '✗ Erro: ' + (e.message || 'falhou');
  }
  await pollDashboard();
  loadDemo();
};

/* ---------- DEX KYBERSWAP ---------- */
async function loadDex() {
  const body = $('dexBody');
  if (!body) return;
  try {
    const d = await api('/api/dex');
    const rows = d.rows || [];
    if (!rows.length) {
      body.innerHTML = `<tr><td colspan="5" style="text-align:center;padding:24px" class="muted">Buscando cotações DEX...</td></tr>`;
      return;
    }
    body.innerHTML = rows.map(r => {
      if (!r.ok) return `<tr><td><b>${r.chain}</b></td><td colspan="4" class="muted">indisponível agora</td></tr>`;
      const pnlCls = r.roundtrip_pnl >= 0 ? 'green' : 'red';
      return `<tr>
        <td><b>${r.chain}</b></td>
        <td>${Number(r.brz_out).toLocaleString('pt-BR', { maximumFractionDigits: 0 })} BRZ</td>
        <td>$${r.brz_price_usdt}</td>
        <td>$${r.roundtrip_usdt}</td>
        <td class="right"><b class="${pnlCls}">${r.roundtrip_pnl >= 0 ? '+' : ''}$${r.roundtrip_pnl}</b></td>
      </tr>`;
    }).join('');
    const upd = $('dexUpdated');
    if (upd) upd.textContent = d.updated_ts
      ? 'atualizado ' + new Date(d.updated_ts * 1000).toLocaleTimeString('pt-BR')
      : '';
  } catch (e) {
    body.innerHTML = `<tr><td colspan="5" style="text-align:center;padding:24px" class="muted">DEX offline no momento</td></tr>`;
  }
}

/* ---------- CONFIGURACAO ---------- */
const EX_LABELS = {
  binance: 'Binance', bybit: 'Bybit', bitget: 'Bitget', okx: 'OKX',
  gate: 'Gate.io', mexc: 'MEXC', kucoin: 'KuCoin', mercadobitcoin: 'MercadoBitcoin',
};
const EX_FIELDS = {
  binance: ['API_KEY', 'SECRET_KEY'],
  bybit: ['API_KEY', 'SECRET_KEY'],
  bitget: ['API_KEY', 'SECRET_KEY', 'PASSPHRASE'],
  okx: ['API_KEY', 'SECRET_KEY', 'PASSPHRASE'],
  gate: ['API_KEY', 'SECRET_KEY'],
  mexc: ['API_KEY', 'SECRET_KEY'],
  kucoin: ['API_KEY', 'SECRET_KEY', 'PASSPHRASE'],
  mercadobitcoin: ['API_KEY', 'SECRET_KEY'],
};

function maskKey(val) {
  if (!val) return '';
  if (val.length <= 8) return val;
  return val.slice(0, 4) + '••••••••' + val.slice(-4);
}

async function loadSettings() {
  const [settings, dash] = await Promise.all([api('/api/settings'), api('/api/dashboard')]);
  const list = $('settingsList');
  const status = $('settingsStatus');

  let html = '';
  for (const [eid, info] of Object.entries(settings)) {
    const color = EX_COLORS[eid] || 'var(--text)';
    const label = EX_LABELS[eid] || eid;
    const configured = info.configured;
    const isOpen = eid === 'binance';
    html += `
      <div class="settings-card${configured ? ' has-keys' : ''}${isOpen ? ' open' : ''}" id="scard-${eid}">
        <div class="settings-card-header" onclick="toggleSettingsCard('${eid}')">
          <div class="settings-card-left">
            <span class="settings-status-dot ${configured ? 'on' : 'off'}"></span>
            <span class="ex-name" style="color:${color}">${label}</span>
            <span class="muted small">${configured ? '✓ Configurada' : 'Não configurada'}</span>
          </div>
          <span class="settings-card-toggle">▼</span>
        </div>
        <div class="settings-card-body">
          <div class="settings-fields">
            ${EX_FIELDS[eid].map(f => `
              <div class="settings-field">
                <label>${f}</label>
                <input type="password" id="field-${eid}-${f}"
                  placeholder="${f === 'PASSPHRASE' ? 'Passphrase (se aplicável)' : f}"
                  value="${info.fields[f] || ''}"
                  autocomplete="off" spellcheck="false">
              </div>
            `).join('')}
          </div>
          <div class="settings-actions">
            <button class="btn-save" onclick="saveSettings('${eid}')">💾 Salvar</button>
            ${configured ? `<button class="btn-clear-keys" onclick="clearSettings('${eid}')">🗑 Remover</button>` : ''}
            <span class="settings-saved-msg" id="saved-${eid}"></span>
          </div>
        </div>
      </div>`;
  }
  list.innerHTML = html;

  let shtml = '';
  for (const [eid, data] of Object.entries(dash.prices || {})) {
    const color = EX_COLORS[eid] || 'var(--text)';
    const label = EX_LABELS[eid] || eid;
    const connected = (dash.exchanges_ok || []).includes(eid);
    const hasData = data && data['USDT/BRL'] && data['USDT/BRL'].ask;
    const error = (dash.errors || {})[eid];
    shtml += `
      <div class="status-item">
        <span class="ex-dot" style="background:${hasData ? 'var(--green)' : connected ? 'var(--orange)' : '#64748B'}"></span>
        <span style="color:${color};font-weight:600;font-size:13px">${label}</span>
        <span class="muted small" style="margin-left:auto">${hasData ? '✓ online' : error ? '✗ erro' : 'offline'}</span>
      </div>`;
  }
  status.innerHTML = shtml;
}

window.toggleSettingsCard = function(eid) {
  const card = $(`scard-${eid}`);
  card.classList.toggle('open');
};

window.saveSettings = async function(eid) {
  const fields = {};
  for (const f of EX_FIELDS[eid]) {
    fields[f] = $(`field-${eid}-${f}`).value.trim();
  }
  const res = await api('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ exchange: eid, fields }),
  });
  const msg = $(`saved-${eid}`);
  if (res.ok) {
    msg.textContent = '✓ Salvo! Reinicie o servidor pra conectar.';
    msg.style.color = 'var(--green)';
    $(`scard-${eid}`).classList.add('has-keys');
    const dot = $(`scard-${eid}`).querySelector('.settings-status-dot');
    if (dot) { dot.className = 'settings-status-dot on'; }
  } else {
    msg.textContent = '✗ ' + (res.error || 'Erro ao salvar');
    msg.style.color = 'var(--red)';
  }
  setTimeout(() => { msg.textContent = ''; }, 4000);
};

window.clearSettings = async function(eid) {
  if (!confirm(`Remover as API keys da ${EX_LABELS[eid]}?`)) return;
  await api(`/api/settings?exchange=${eid}`, { method: 'DELETE' });
  for (const f of EX_FIELDS[eid]) {
    $(`field-${eid}-${f}`).value = '';
  }
  $(`scard-${eid}`).classList.remove('has-keys');
  const dot = $(`scard-${eid}`).querySelector('.settings-status-dot');
  if (dot) { dot.className = 'settings-status-dot off'; }
  const msg = $(`saved-${eid}`);
  msg.textContent = '✓ Removida';
  msg.style.color = 'var(--green)';
  setTimeout(() => { msg.textContent = ''; }, 3000);
};

/* ---------- CALCULATOR ---------- */
var EX_FEES = {
  binance: 0.001, bybit: 0.001, bitget: 0.001, okx: 0.001,
  mexc: 0.0005, kucoin: 0.001, mercadobitcoin: 0.005,
};
var WD_FEES = {
  binance: {BEP20: 0.01, SOL: 0.30, POLYGON: 0.07, ARBITRUM: 0.10, TRC20: 1.50, ERC20: 0.40},
  bybit: {BEP20: 1.00, SOL: 1.00, POLYGON: 0.07, ARBITRUM: 1.00, TRC20: 1.60, ERC20: 5.00},
  bitget: {BEP20: 0.15, SOL: 1.00, POLYGON: 0.07, ARBITRUM: 0.05, TRC20: 1.50, ERC20: 2.00},
  okx: {BEP20: 0.05, SOL: 0.34, POLYGON: 0.012, ARBITRUM: 0.0034, TRC20: 1.00, ERC20: 0.43},
  mexc: {BEP20: 0.01, SOL: 0.18, POLYGON: 0.0065, ARBITRUM: 0.05, TRC20: 1.00, ERC20: 0.094},
  mercadobitcoin: {BEP20: 1.50, SOL: 2.00, POLYGON: 2.00, ARBITRUM: 2.00, TRC20: 3.00, ERC20: 10.00},
};

function setCalcAmount(v) {
  var inp = document.getElementById('calcAmount');
  if (inp) inp.value = v;
  calcProfit();
}

// melhor rota ao vivo direto dos preços (menor ask -> maior bid),
// usada quando nao ha oportunidade acima do spread minimo
function bestRouteFromPrices(prices) {
  try {
    var exs = Object.keys(prices || {});
    var best = null;
    for (var i = 0; i < exs.length; i++) {
      for (var j = 0; j < exs.length; j++) {
        if (i === j) continue;
        var bp = prices[exs[i]] && prices[exs[i]]['USDT/BRL'];
        var sp = prices[exs[j]] && prices[exs[j]]['USDT/BRL'];
        if (!bp || !sp || !bp.ask || !sp.bid) continue;
        var g = (sp.bid - bp.ask) / bp.ask * 100;
        if (!best || g > best.gross_pct) {
          best = { buy_exchange: exs[i], sell_exchange: exs[j],
                   buy_price: bp.ask, sell_price: sp.bid,
                   gross_pct: Math.round(g * 10000) / 10000, network: 'BEP20' };
        }
      }
    }
    return best;
  } catch (e) { return null; }
}

function calcProfit() {
  var el = function(id) { return document.getElementById(id); };
  // se nao ha oportunidade acima do spread, usa a melhor rota ao vivo (menor ask -> maior bid)
  var b = (DASH && DASH.best) || bestRouteFromPrices(DASH && DASH.prices);
  if (!b) {
    ['calcRoute','calcSpread','calcFeeBuy','calcFeeSell','calcFeeNet','calcTotalFees','calcNet','calcPct','calcMonthly'].forEach(function(id) {
      var e = el(id); if (e) e.textContent = '\u2014';
    });
    var r = el('calcRoute'); if (r) r.textContent = 'Aguardando preços...';
    return;
  }
  try {
    var inp = el('calcAmount');
    var brl = inp ? (parseFloat(inp.value) || 1000) : 1000;
    var rate = b.buy_price || 5.16;
    var buyEx = b.buy_exchange || 'binance';
    var sellEx = b.sell_exchange || 'bitget';
    var netName = b.network || 'BEP20';
    var grossPct = b.gross_pct || 0;
    var feeBuyPct = EX_FEES[buyEx] !== undefined ? EX_FEES[buyEx] : 0.001;
    var feeSellPct = EX_FEES[sellEx] !== undefined ? EX_FEES[sellEx] : 0.001;
    var feeBuy = brl * feeBuyPct;
    var feeSell = brl * feeSellPct;
    var exFees = WD_FEES[buyEx] || {};
    var feeNetUsd = exFees[netName] !== undefined ? exFees[netName] : 0.30;
    var feeNetBrl = feeNetUsd * rate;
    var totalFees = feeBuy + feeSell + feeNetBrl;
    var grossProfit = brl * (grossPct / 100);
    var netProfit = grossProfit - totalFees;
    var netPct = brl > 0 ? (netProfit / brl * 100) : 0;
    var monthly = netProfit * 30;
    var cBuy = EX_COLORS[buyEx] || '#fff';
    var cSell = EX_COLORS[sellEx] || '#fff';
    var rEl = el('calcRoute'); if (rEl) rEl.innerHTML = '<span style="color:'+cBuy+'">'+buyEx+'</span> \u2192 <span style="color:'+cSell+'">'+sellEx+'</span>';
    var sEl = el('calcSpread'); if (sEl) sEl.textContent = 'R$' + grossProfit.toFixed(2) + ' (' + grossPct + '%)';
    var fbEl = el('calcFeeBuy'); if (fbEl) fbEl.textContent = '-R$' + feeBuy.toFixed(2) + ' (' + (feeBuyPct * 100).toFixed(2) + '%)';
    var fsEl = el('calcFeeSell'); if (fsEl) fsEl.textContent = '-R$' + feeSell.toFixed(2) + ' (' + (feeSellPct * 100).toFixed(2) + '%)';
    var fnEl = el('calcFeeNet'); if (fnEl) fnEl.textContent = '-R$' + feeNetBrl.toFixed(2) + ' ($' + feeNetUsd + ' ' + netName + ')';
    var tfEl = el('calcTotalFees'); if (tfEl) tfEl.textContent = '-R$' + totalFees.toFixed(2);
    var nEl = el('calcNet'); if (nEl) { nEl.textContent = 'R$' + netProfit.toFixed(2); nEl.className = netProfit >= 0 ? 'green' : 'red'; }
    var pEl = el('calcPct'); if (pEl) { pEl.textContent = netPct.toFixed(3) + '%'; pEl.className = netPct >= 0 ? 'green' : 'red'; }
    var mEl = el('calcMonthly'); if (mEl) { mEl.textContent = 'R$' + monthly.toFixed(2); mEl.className = monthly >= 0 ? 'green' : 'red'; }
  } catch(e) { console.error('calc error', e); }
}

/* ---------- PENDING TRANSFERS ---------- */
function renderPending(pending) {
  const section = $('pendingSection');
  const body = $('pendingBody');
  if (!section || !body) return;

  if (!pending || pending.length === 0) {
    section.style.display = 'none';
    return;
  }

  section.style.display = 'block';
  body.innerHTML = pending.map(t => {
    const color = EX_COLORS[t.from] || 'var(--text)';
    const colorTo = EX_COLORS[t.to] || 'var(--text)';
    if (t.demo) {
      return `
      <div class="pending-card">
        <div class="pending-row">
          <span>Modo</span><b class="orange">🎬 DEMO (fictício)</b>
        </div>
        <div class="pending-row">
          <span>Rota</span>
          <b><span style="color:${color}">${t.from}</span> → <span style="color:${colorTo}">${t.to}</span></b>
        </div>
        <div class="pending-row">
          <span>Quantidade</span><b style="color:var(--green)">${t.qty} USDT</b>
        </div>
        <div class="pending-row">
          <span>Rede</span><b>${t.network}</b>
        </div>
        ${t.live_net !== undefined && t.live_net !== null ? `
        <div class="pending-row">
          <span>💰 Lucro agora (ao vivo)</span><b class="${t.live_net >= 0 ? 'green' : 'red'}">${fmtBrl(t.live_net)} (${t.live_pct}%)</b>
        </div>` : ''}
        <div class="pending-row">
          <span>⏱ Tempo real da arbitragem</span><b class="orange">${fmtTime(t.seconds_left ?? 0)} restantes</b>
        </div>
      </div>`;
    }
    return `
    <div class="pending-card">
      <div class="pending-row">
        <span>Par</span><b>${t.pair}</b>
      </div>
      <div class="pending-row">
        <span>Rota</span>
        <b><span style="color:${color}">${t.from}</span> → <span style="color:${colorTo}">${t.to}</span></b>
      </div>
      <div class="pending-row">
        <span>Quantidade</span><b style="color:var(--green)">${t.qty} USDT</b>
      </div>
      <div class="pending-row">
        <span>Rede</span><b>${t.network} (~$${t.tx_fee_usd})</b>
      </div>
      <div class="pending-row">
        <span>Status</span><b class="orange">${t.status}</b>
      </div>

      <div class="pending-step">
        <span class="pending-step-num done">✓</span>
        <span>Compra executada em ${t.from}</span>
      </div>
      <div class="pending-step">
        <span class="pending-step-num active">2</span>
        <span><b>Envie USDT de ${t.from} para ${t.to}</b></span>
      </div>
      <div class="pending-step">
        <span class="pending-step-num wait">3</span>
        <span>Venda automática em ${t.to} (quando detectar depósito)</span>
      </div>

      <div class="pending-instructions">
        <b>📋 Passo a passo:</b><br>
        1. Abra o app/site da <b>${t.from}</b><br>
        2. Vá em <b>Carteira → Sacar → USDT</b><br>
        3. Rede: <b>${t.network}</b> — ⚠️ confira se o endereço abaixo é dessa rede!<br>
        4. Cole o endereço abaixo:<br>
        <div class="pending-addr">
          ${t.deposit_address}
          <button class="btn-copy" onclick="navigator.clipboard.writeText('${t.deposit_address}').then(()=>this.textContent='Copiado!')">📋 Copiar</button>
        </div>
        ${t.deposit_tag ? `<div class="pending-addr">TAG/MEMO: ${t.deposit_tag}</div>` : ''}
        5. Envie <b>${t.qty} USDT</b><br>
        6. O sistema detecta automaticamente e vende em ${t.to}
      </div>
    </div>`;
  }).join('');
}

/* ---------- BALANCES ---------- */
function renderBalSummary(balances) {
  const card = $('balSummaryCard');
  const grid = $('balSummary');
  if (!card || !grid) return;

  const hasKeys = Object.values(balances).some(b => !b.error);
  if (!hasKeys) {
    card.style.display = 'none';
    return;
  }
  card.style.display = 'block';

  let html = '';
  for (const [eid, info] of Object.entries(balances)) {
    const color = EX_COLORS[eid] || 'var(--text)';
    const label = EX_LABELS[eid] || eid;
    if (info.error) {
      html += `
        <div class="balance-card" style="opacity:.4">
          <div class="balance-card-header">
            <span class="ex-name" style="color:${color}">${label}</span>
            <span class="bal-status err">sem key</span>
          </div>
        </div>`;
    } else if (info.coins && Object.keys(info.coins).length > 0) {
      html += `
        <div class="balance-card">
          <div class="balance-card-header">
            <span class="ex-name" style="color:${color}">${label}</span>
            <span class="bal-status ok">✓</span>
          </div>
          ${Object.entries(info.coins).map(([coin, bal]) => `
            <div class="balance-coin">
              <span class="balance-coin-name">${coin}</span>
              <span class="balance-coin-free">${bal.free}</span>
            </div>
          `).join('')}
        </div>`;
    } else {
      html += `
        <div class="balance-card">
          <div class="balance-card-header">
            <span class="ex-name" style="color:${color}">${label}</span>
            <span class="bal-status ok">✓</span>
          </div>
          <div class="balance-empty">sem saldo</div>
        </div>`;
    }
  }
  grid.innerHTML = html;
}

window.loadBalances = async function() {
  const grid = $('balancesGrid');
  grid.innerHTML = '<div class="balance-empty">Carregando saldos...</div>';
  const hint = $('balanceHint');
  if (hint) hint.textContent = 'Buscando saldos...';

  const data = await api('/api/balances');
  if (data.error) {
    grid.innerHTML = `<div class="balance-empty red">${data.error}</div>`;
    return;
  }

  let html = '';
  let hasAny = false;
  for (const [eid, info] of Object.entries(data)) {
    const color = EX_COLORS[eid] || 'var(--text)';
    const label = EX_LABELS[eid] || eid;
    if (info.error) {
      html += `
        <div class="balance-card error">
          <div class="balance-card-header">
            <span class="ex-name" style="color:${color}">${label}</span>
            <span class="bal-status err">✗ ${info.error}</span>
          </div>
          <div class="balance-empty">Configure API key pra ver saldo</div>
        </div>`;
    } else if (info.coins && Object.keys(info.coins).length > 0) {
      hasAny = true;
      html += `
        <div class="balance-card">
          <div class="balance-card-header">
            <span class="ex-name" style="color:${color}">${label}</span>
            <span class="bal-status ok">✓ online</span>
          </div>
          ${Object.entries(info.coins).map(([coin, bal]) => `
            <div class="balance-coin">
              <div>
                <span class="balance-coin-name">${coin}</span>
                <span class="balance-coin-used"> · frozen: ${bal.used}</span>
              </div>
              <span class="balance-coin-free">${bal.free}</span>
            </div>
          `).join('')}
        </div>`;
    } else {
      html += `
        <div class="balance-card">
          <div class="balance-card-header">
            <span class="ex-name" style="color:${color}">${label}</span>
            <span class="bal-status ok">✓ online</span>
          </div>
          <div class="balance-empty">${info.note || 'conta vazia ou sem dados'}</div>
        </div>`;
    }
  }

  if (hint) hint.textContent = hasAny ? 'Saldos atualizados' : 'Configure API keys pra ver saldos';
  grid.innerHTML = html || '<div class="balance-empty">Nenhuma corretora configurada</div>';
};
