const $ = id => document.getElementById(id);
const EX_COLORS = {
  binance: '#F0B90B', bybit: '#F7A600', bitget: '#1EC6A7', kucoin: '#01C8C8',
  okx: '#7CC4FF', gate: '#31C4FE', mexc: '#4DD0E1', htx: '#FF6D6D',
  kraken: '#B08CFF', mercadobitcoin: '#25B9A5', bitso: '#37E2B2',
};

let AUTO_ON = false;

window.toggleAuto = async function() {
  const res = await api('/api/auto', { method: 'POST' });
  AUTO_ON = res.auto_trade;
  updateAutoUI();
};

function updateAutoUI() {
  const check = $('autoCheck');
  const label = $('autoLabel');
  const status = $('autoStatus');
  if (check) check.checked = AUTO_ON;
  if (label) label.textContent = AUTO_ON ? 'Modo: Automático' : 'Modo: Manual';
  if (status) {
    status.textContent = AUTO_ON ? '🤖 Auto ON' : '✋ Manual';
    status.className = 'auto-status ' + (AUTO_ON ? 'on' : 'off');
  }
  const rb = $('robotBadge');
  if (AUTO_ON) {
    rb.style.display = 'block';
    rb.innerHTML = '🤖 Auto-TRADE LIGADO';
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

function fmtUsd(v) {
  const n = Number(v) || 0;
  const sign = n < 0 ? '-' : '';
  return `${sign}$${Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
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
    if (btn.dataset.tab === 'historico') loadHistory();
    if (btn.dataset.tab === 'configuracao') loadSettings();
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
        <b class="${best.net_usdt >= 0 ? 'green' : 'red'} font-display" style="font-size:18px">${fmtUsd(best.net_usdt)}</b>
        <button class="btn-exec" onclick="execRoute('${best.pair}','${best.buy_exchange}','${best.sell_exchange}')">⚡ Executar</button>
      </div>
    </div>`;
}

function renderOpps(list) {
  $('oppCount').textContent = list.length ? `${list.length} rotas com spread` : '';
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
      <td class="right"><b class="${o.net_usdt >= 0 ? 'green' : 'red'}">${fmtUsd(o.net_usdt)}</b><br><span class="muted small">${o.net_pct}%</span></td>
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
      return `<div class="price-card${isConnected ? '' : ' offline'}">
        <div class="ex-name" style="color:${EX_COLORS[ex] || 'var(--text)'}">${ex}</div>
        <div class="price-ask muted">${isConnected ? 'aguardando...' : 'offline'}</div>
      </div>`;
    }
    const spread = pair.ask && pair.bid ? (((pair.ask - pair.bid) / pair.bid) * 100).toFixed(3) : '—';
    return `<div class="price-card${isActive ? ' active' : ''}">
      <div class="ex-name" style="color:${EX_COLORS[ex] || 'var(--text)'}">${ex}</div>
      <div class="price-ask">ask ${fmtPrice(pair.ask)}</div>
      <div class="price-bid">bid ${fmtPrice(pair.bid)}</div>
      <div class="price-spread">spread ${spread}%</div>
      ${isActive ? '<div class="price-tag">OPORTUNIDADE</div>' : ''}
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
    updateAutoUI();

    const badge = $('connBadge');
    if (d.connected) badge.innerHTML = '<span class="dot on"></span> Scanner ao vivo';
    else badge.innerHTML = '<span class="dot gray"></span> Conectando...';

    $('stOpps').textContent = d.total_opportunities;
    $('stScan').textContent = d.last_scan
      ? `varredura em ${d.scan_seconds}s · ${d.exchanges_ok.length} corretoras`
      : 'aguardando primeira varredura...';

    const b = d.best;
    $('stBest').textContent = b ? fmtUsd(b.net_usdt) : '—';
    $('stBest').className = `card-value font-display ${b ? (b.net_usdt >= 0 ? 'green' : 'red') : ''}`;
    $('stBestSub').textContent = b ? `${b.pair} · ${b.buy_exchange} → ${b.sell_exchange}` : 'esperando spread';

    renderBest(b);
    renderOpps(d.opportunities || []);
    renderPrices(d.prices, d.opportunities || [], d.exchanges_ok || []);
    fillSimSelects();

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
      rb.innerHTML = '🤖 Auto-TRADE LIGADO';
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

  const keep = (sel, arr, val) => {
    sel.innerHTML = arr.map(x => `<option value="${x}">${x}</option>`).join('');
    if (val && arr.includes(val)) sel.value = val;
  };
  keep($('simPair'), pairs, $('simPair').value);
  keep($('simBuy'), exs, $('simBuy').value);
  keep($('simSell'), exs, $('simSell').value);
}

window.fillSim = function (pair, buyEx, sellEx) {
  document.querySelector('[data-tab="simulador"]').click();
  fillSimSelects();
  setTimeout(() => {
    $('simPair').value = pair;
    $('simBuy').value = buyEx;
    $('simSell').value = sellEx;
    runSim();
  }, 50);
};

async function runSim() {
  const payload = {
    pair: $('simPair').value,
    buy_exchange: $('simBuy').value,
    sell_exchange: $('simSell').value,
    invest_usdt: parseFloat($('simInvest').value) || 1000,
    network: $('simNetwork').value,
  };
  const res = await api('/api/simulate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const box = $('simResult');
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
      <td class="${n.net_usdt >= 0 ? 'green' : 'red'}"><b>${fmtUsd(n.net_usdt)}</b></td>
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
        <span class="net-big font-display ${res.net_usdt >= 0 ? 'green' : 'red'}">${fmtUsd(res.net_usdt)}</span>
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
    <div class="row"><span>Lucro líquido</span><b class="${res.net_usdt >= 0 ? 'green' : 'red'}">${fmtUsd(res.net_usdt)} (${res.net_pct}%)</b></div>
    <div class="row"><span>⏱ Tempo real da operação</span><b>${res.elapsed_fmt}</b></div>
    <div class="row"><span>Tempo em dinheiro real (com transferência)</span><b>~${fmtTime(res.est_real_seconds)}</b></div>
    <div class="muted" style="font-size:11px;margin-top:8px">Modo paper-trade: preços reais, ordens simuladas.</div>`;
  setTimeout(() => toast.classList.remove('show'), 9000);
};

/* ---------- HISTÓRICO ---------- */
async function loadHistory() {
  const [hist, stats, execs] = await Promise.all([
    api('/api/simulations?limit=200'), api('/api/stats'), api('/api/executions?limit=100'),
  ]);
  $('hsCount').textContent = (stats.total_simulations ?? 0) + (stats.total_executions ?? 0);
  $('hsTotal').textContent = fmtUsd((stats.total_net_usdt ?? 0) + (stats.total_executed_net ?? 0));
  $('stSims').textContent = stats.total_simulations ?? 0;
  $('stProfit').textContent = fmtUsd(stats.total_net_usdt ?? 0);
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
      <td>${fmtUsd(h.invest_usdt)}</td>
      <td>${fmtTime(h.est_seconds)}</td>
      <td class="right"><b class="${h.net_usdt >= 0 ? 'green' : 'red'}">${fmtUsd(h.net_usdt)}</b></td>
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
      <td>${fmtUsd(x.invest_usdt)}</td>
      <td><span class="badge badge-green">⏱ ${x.elapsed_fmt}</span></td>
      <td class="right"><b class="${x.net_usdt >= 0 ? 'green' : 'red'}">${fmtUsd(x.net_usdt)}</b></td>
    </tr>`).join('');
  $('execBody').innerHTML = exRows ||
    `<tr><td colspan="8" style="text-align:center;padding:36px" class="muted">Nenhuma execução ainda — clique em ⚡ Executar numa oportunidade.</td></tr>`;
}

$('btnClear').addEventListener('click', async () => {
  if (!confirm('Apagar todo o histórico de simulações?')) return;
  await api('/api/simulations', { method: 'DELETE' });
  loadHistory();
});

/* ---------- BOOT ---------- */
pollDashboard();
setInterval(pollDashboard, 5000);
setInterval(() => {
  if ($('tab-historico').classList.contains('active')) loadHistory();
}, 8000);

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
