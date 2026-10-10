import os
import threading
import time

import ccxt

import config
import db
import json
from datetime import datetime, timedelta, timezone
from engine import simulate

BRT = timezone(timedelta(hours=-3))


def fmt_brl(v):
    return f"R${float(v or 0):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')


def sim_fee_sell(t):
    """Taxa taker da corretora de venda (para devolver o BRL liquido)."""
    return float(config.TAKER_FEES.get(t.get('sell_exchange'), 0.001))


class Executor:
    def __init__(self):
        self.lock = threading.Lock()
        self.counter = 0
        self.mode = 'paper'  # 'paper', 'demo' ou 'real'
        self.pending_transfers = []
        # controle realista da demo
        self.wallet = {}          # {ex: {'BRL': float, 'USDT': float}}
        # CAPITAL UNICO: comeca em DEMO_START_BRL (R$5.000) e GIRA entre as
        # corretoras — vai para a de compra a cada ciclo e volta (com lucro) no fim.
        self.demo_capital = config.DEMO_START_BRL
        # o capital inicial da demo segue o valor configurado pelo usuario
        # (evita comecar com 5000 enquanto o campo dice 250)
        if float(getattr(config, 'DEMO_START_BRL', 0) or 0) <= 0:
            self.demo_capital = float(config.INVESTMENT_USDT)
        self.capital_base = self.demo_capital
        self.balances_cache = {}   # saldos REAIS por corretora (quando ha API key)
        self.balances_errors = {}  # motivo de cada falha (aparece na tela)
        self.real_total_brl = 0.0
        self.real_total_usdt = 0.0
        self.using_real_balance = False
        self.capital_in_use = None  # {ex, amount} enquanto o ciclo esta em andamento
        home = (getattr(config, 'HOME_EXCHANGE', '') or '').strip().lower()
        self.home_exchange = None if home in ('', 'auto') else home
        self._demo_routes = {}    # rota -> ultima vez executada
        self._demo_last = 0       # ultima operacao demo (timestamp)
        self._demo_times = []     # timestamps das operacoes demo (teto diario)
        self._demo_ref = None     # (spread_pct, timestamp) da ultima operacao
        self._load_demo_state()    # ritmo continua apos reiniciar o servidor

    def refresh_real_balances(self, scanner, min_interval=60):
        """Puxa o saldo REAL das corretoras (via API key) para usar de capital.
        Actualiza a cada ~1min para nao estourar rate limit."""
        now = time.time()
        if now - getattr(self, '_last_bal', 0) < min_interval:
            return self.balances_cache
        self._last_bal = now
        try:
            b = scanner.fetch_balances()
        except Exception as e:
            print(f"[EXEC] ⚠️ saldo indisponivel: {str(e)[:80]}")
            return self.balances_cache
        cache = {}
        erros = {}
        total_brl = 0.0
        total_usdt = 0.0
        for ex, info in (b or {}).items():
            if not isinstance(info, dict):
                continue
            if info.get('error'):
                erros[ex] = str(info['error'])[:80]
                continue
            coins = info.get('coins') or {}
            brl = float((coins.get('BRL') or {}).get('total') or 0)
            usdt = float((coins.get('USDT') or {}).get('total') or 0)
            if brl or usdt:
                cache[ex] = {'BRL': brl, 'USDT': usdt}
                total_brl += brl
                total_usdt += usdt
            else:
                erros[ex] = 'saldo zero'
        self.balances_cache = cache
        self.balances_errors = erros
        self.real_total_brl = round(total_brl, 2)
        self.real_total_usdt = round(total_usdt, 2)
        if total_brl > 0:
            # capital real disponible e a fonte de verdade da demo
            if not self.using_real_balance:
                # primeira vez com saldo real: a base passa a ser ele
                self.capital_base = round(total_brl, 2)
            self.demo_capital = round(total_brl, 2)
            self.using_real_balance = True
        return cache

    def available_for(self, exchange, invest):
        """Capital disponivel. O BRL fica na corretora principal (casa) e viaja
        ate a corretora de compra, entao o limite e o capital acumulado em casa."""
        return float(self.demo_capital), self.using_real_balance

    def demo_wallet_for(self, ex):
        """Carteira virtual por corretora (so o USDT que chega nela; o BRL e o
        capital unico que circula)."""
        if ex not in self.wallet:
            self.wallet[ex] = {'BRL': 0.0, 'USDT': 0.0}
        return self.wallet[ex]

    def demo_wallet_state(self):
        return {ex: dict(v) for ex, v in self.wallet.items()}

    def set_capital_base(self, valor):
        """Define o capital inicial da demo (segue o valor configurado)."""
        try:
            v = round(float(valor), 2)
        except Exception:
            return
        if v <= 0:
            return
        with self.lock:
            self.capital_base = v
            if not self.using_real_balance and not self.pending_transfers:
                self.demo_capital = v
        try:
            db.set_setting('demo_start_brl', v)
        except Exception:
            pass
        print(f"[DEMO] capital inicial: {fmt_brl(v)}")

    def sync_capital(self):
        """Capital virtual = valor inicial + lucro de hoje.
        Assim o lucro realmente entra na proxima arbitragem, mesmo depois
        de o servidor ter reiniciado (o lucro fica salvo no banco)."""
        if self.using_real_balance:
            return
        try:
            d = db.daily_stats(mode='demo')
            self.demo_capital = round(float(self.capital_base) + float(d['dia']['net']), 2)
        except Exception:
            pass

    def _demo_size(self, o):
        """Quanto usar na proxima operacao.
        Com juros compostos, usa TODO o saldo (lucro incluido)."""
        # so sincroniza quando nao ha ciclo em andamento (evita contar em dobro)
        if not any(t.get('demo') for t in self.pending_transfers):
            self.sync_capital()
        if getattr(config, 'DEMO_ALL_CAPITAL', True):
            cap = float(self.demo_capital)
            if cap >= 20:
                return round(cap, 2)
        return float(o.get('invest_usdt') or config.INVESTMENT_USDT)

    def _save_demo_state(self):
        """Grava o ritmo da demo no banco: reiniciar o servidor nao pode
        zerar o intervalo entre operacoes (senao o bot opera colado)."""
        try:
            db.set_setting('demo_state', json.dumps({
                'last': self._demo_last,
                'times': [round(t, 2) for t in self._demo_times],
                'routes': {f'{b}|{s}': round(t, 2) for (b, s), t in self._demo_routes.items()},
                'ref': list(self._demo_ref) if self._demo_ref else None,
            }))
        except Exception:
            pass

    def _load_demo_state(self):
        try:
            raw = db.get_setting('demo_state')
            if not raw:
                return
            d = json.loads(raw)
            self._demo_last = float(d.get('last') or 0)
            self._demo_times = [float(t) for t in (d.get('times') or [])]
            self._demo_routes = {}
            for k, t in (d.get('routes') or {}).items():
                b, s = k.split('|', 1)
                self._demo_routes[(b, s)] = float(t)
            ref = d.get('ref')
            self._demo_ref = (float(ref[0]), float(ref[1])) if ref else None
            if self._demo_last:
                print(f"[DEMO] ritmo restaurado: ultimo ciclo ha "
                      f"{int((time.time() - self._demo_last) // 60)}min")
        except Exception as e:
            print(f"[DEMO] estado nao restaurado: {str(e)[:60]}")

    def _demo_blocked_reason(self, o):
        """Travas que impedem arbitragem continua/infinita (igual vida real)."""
        now = time.time()
        with self.lock:
            if any(t.get('demo') for t in self.pending_transfers):
                return 'operacao demo em andamento (aguardando a venda)'
            day = now - 86400
            self._demo_times = [t for t in self._demo_times if t >= day]
            if len(self._demo_times) >= config.DEMO_MAX_PER_DAY:
                return f'limite diario de {config.DEMO_MAX_PER_DAY} operacoes atingido'
            if self._demo_last:
                espera = self._demo_last + config.DEMO_MIN_INTERVAL_MIN * 60 - now
                if espera > 0:
                    return f'aguarda {int(espera // 60)}min {int(espera % 60)}s entre operacoes'
            # so entra se ainda estiver favoravel (spread minimo + margem)
            alvo = float(config.MIN_SPREAD_PCT) + float(getattr(config, 'DEMO_MARGIN_PCT', 0.05))
            # memoria do spread: nao aceita pior que o da ultima operacao (ate expirar)
            ref, ref_ts = self._demo_ref or (None, 0)
            ttl = float(getattr(config, 'DEMO_REF_TTL_MIN', 30)) * 60
            if ref is not None and now - ref_ts <= ttl:
                if float(o.get('net_pct') or 0) < ref:
                    return (f'spread {o.get("net_pct")}% esta pior que o da ultima '
                            f'operacao ({ref}%) — espera melhorar')
                alvo = max(alvo, ref)
            if float(o.get('net_pct') or 0) < alvo:
                return f'spread {o.get("net_pct")}% abaixo do alvo {round(alvo, 4)}%'
            rota = (o.get('buy_exchange'), o.get('sell_exchange'))
            ult = self._demo_routes.get(rota, 0)
            if ult:
                espera = ult + config.DEMO_ROUTE_COOLDOWN_MIN * 60 - now
                if espera > 0:
                    return f'spread desta rota ({rota[0]}→{rota[1]}) reacende em {int(espera // 60)}min'
            w = self.demo_wallet_for(o.get('buy_exchange'))
            disponivel, real = self.available_for(o.get('buy_exchange'), o.get('invest_usdt') or 0)
            casa = self.home_exchange or 'capital'
            if float(disponivel) < 10:
                return f'sem capital em {casa} (todas as carteiras em operação)'
            if float(disponivel) < float(o.get('invest_usdt') or 0):
                return (f'capital insuficiente em {casa}: {fmt_brl(disponivel)} '
                        f'(operação pede {fmt_brl(o.get("invest_usdt"))})')
        return None

    def _hubs_ranking(self, prices, pair='USDT/BRL', invest=None):
        """Para cada corretora como 'principal', qual o melhor lucro liquido?
        Serve para escolher o hub com base em-spread E taxa (nao no chute)."""
        invest = float(invest or config.INVESTMENT_USDT)
        out = []
        exs = [e for e, m in prices.items() if (m.get(pair) or {}).get('bid')]
        for hub in exs:
            hub_bid = prices[hub][pair]['bid']
            best = None
            for buy_ex, m in prices.items():
                if buy_ex == hub:
                    continue
                ask = (m.get(pair) or {}).get('ask')
                if not ask or ask >= hub_bid:
                    continue
                try:
                    sim = simulate(pair, buy_ex, ask, hub, hub_bid, invest, 'AUTO')
                except Exception:
                    continue
                if best is None or sim['net_pct'] > best['net_pct']:
                    best = sim
            if best:
                out.append({
                    'hub': hub,
                    'net_pct': best['net_pct'],
                    'net_usdt': best['net_usdt'],
                    'buy_exchange': buy_ex,
                    'network': best['network'],
                })
        out.sort(key=lambda r: r['net_pct'], reverse=True)
        return out

    def demo_status(self, scanner=None):
        now = time.time()
        # reset diario: a cada meia-noite o lucro de hoje zera e o capital volta ao inicial
        hoje = datetime.now(BRT).date().isoformat()
        if not self.using_real_balance and getattr(self, '_capital_day', None) != hoje:
            if getattr(self, '_capital_day', None) is not None:
                print("[DEMO] novo dia — lucro zera, capital volta ao inicial")
            self._capital_day = hoje
        # mantem o capital = inicial + lucro de hoje (lucro entra na proxima)
        if not any(t.get('demo') for t in self.pending_transfers):
            self.sync_capital()
        hubs = []
        if scanner is not None:
            try:
                hubs = self._hubs_ranking((scanner.snapshot().get('prices') or {}))
            except Exception:
                hubs = []
        day = now - 86400
        ttl = float(getattr(config, 'DEMO_REF_TTL_MIN', 30)) * 60
        with self.lock:
            times = [t for t in self._demo_times if t >= day]
            last = self._demo_last
            routes = {}
            for (b, s), t in self._demo_routes.items():
                restante = int(max(0, t + config.DEMO_ROUTE_COOLDOWN_MIN * 60 - now) // 60)
                if restante > 0:
                    routes[f'{b}→{s}'] = restante
            w = {ex: dict(v) for ex, v in self.wallet.items()}
            ref = self._demo_ref
        alvo = float(config.MIN_SPREAD_PCT) + float(getattr(config, 'DEMO_MARGIN_PCT', 0.05))
        if ref:
            alvo = max(alvo, ref[0])
        if self.using_real_balance:
            saldo = round(self.real_total_brl, 2)
        else:
            saldo = round(float(self.demo_capital), 2)
        return {
            'ops_24h': len(times),
            'max_per_day': config.DEMO_MAX_PER_DAY,
            'min_interval_min': config.DEMO_MIN_INTERVAL_MIN,
            'route_cooldown_min': config.DEMO_ROUTE_COOLDOWN_MIN,
            'ref_ttl_min': getattr(config, 'DEMO_REF_TTL_MIN', 30),
            'ref_spread': ref[0] if ref else None,
            'ref_expira_em_min': int(max(0, (ref[1] + ttl - now) // 60)) if ref else 0,
            'spread_alvo': round(alvo, 4),
            'next_in_min': int(max(0, last + config.DEMO_MIN_INTERVAL_MIN * 60 - now) // 60),
            'routes_waiting': routes,
            'capital': saldo,
            'home_exchange': self.home_exchange or 'auto',
            'all_capital': bool(getattr(config, 'DEMO_ALL_CAPITAL', True)),
            'capital_em_uso': self.capital_in_use,
            'lucro': round(saldo - float(self.capital_base), 2),
            'usando_saldo_real': bool(self.using_real_balance),
            'saldo_real_brl': round(self.real_total_brl, 2),
            'saldo_real_usdt': round(self.real_total_usdt, 2),
            'saldos': dict(self.balances_cache) if self.using_real_balance else w,
            'saldo_erros': dict(getattr(self, 'balances_errors', {})),
            'hubs': hubs,
            'wallet': {ex: {'BRL': v.get('BRL', 0), 'USDT': v.get('USDT', 0)} for ex, v in w.items()},
            'start_brl': self.capital_base,
            'total_brl': round(saldo, 2),
            'total_usdt': round(sum(v.get('USDT', 0) for v in w.values()), 2),
        }

    def set_mode(self, mode):
        if mode not in ('paper', 'demo', 'real'):
            mode = 'paper'
        self.mode = mode
        print(f"[EXEC] Modo alterado para: {mode}")

    def set_home(self, home):
        """Define a corretora principal (onde o BRL fica e o lucro volta)."""
        home = (home or 'auto').strip().lower()
        self.home_exchange = None if home in ('', 'auto') else home
        config.HOME_EXCHANGE = self.home_exchange or 'auto'
        try:
            db.set_setting('home_exchange', config.HOME_EXCHANGE)
        except Exception:
            pass
        print(f"[EXEC] Corretora principal: {config.HOME_EXCHANGE}")

    def _get_exchange(self, eid):
        opts = {
            'enableRateLimit': True,
            'timeout': 30000,
            'options': {'defaultType': 'spot'},
        }
        env_key = f'{eid.upper()}_API_KEY'
        env_secret = f'{eid.upper()}_SECRET_KEY'
        env_pass = f'{eid.upper()}_PASSPHRASE'
        api_key = os.environ.get(env_key, '')
        secret = os.environ.get(env_secret, '')
        passphrase = os.environ.get(env_pass, '')
        if api_key:
            opts['apiKey'] = api_key
        if secret:
            opts['secret'] = secret
        if passphrase:
            opts['password'] = passphrase
        ex = getattr(ccxt, eid)(opts)
        try:
            ex.load_markets()
        except Exception:
            pair = 'USDT/BRL'
            ex.markets = {pair: {'id': 'USDTBRL', 'symbol': pair, 'base': 'USDT', 'quote': 'BRL', 'active': True, 'type': 'spot'}}
            ex.markets_by_id = {'USDTBRL': ex.markets[pair]}
        return ex

    def execute(self, scanner, pair, buy_exchange, sell_exchange, invest_usdt, network='AUTO'):
        snap = scanner.snapshot()
        buy_side = snap['prices'].get(buy_exchange, {}).get(pair)
        sell_side = snap['prices'].get(sell_exchange, {}).get(pair)

        if not buy_side or not sell_side:
            result = self._error_result(pair, buy_exchange, sell_exchange, invest_usdt, {}, 'Sem preço disponível')
            return result

        sim = simulate(pair, buy_exchange, buy_side['ask'],
                       sell_exchange, sell_side['bid'], invest_usdt, network)

        if self.mode == 'real':
            return self._execute_semi_auto(scanner, pair, buy_exchange, sell_exchange, invest_usdt, sim, buy_side, sell_side)

        return self._execute_paper(pair, buy_exchange, sell_exchange, invest_usdt, sim, buy_side, sell_side)

    def execute_auto(self, scanner, o):
        """Robo automatico: escolhe o fluxo conforme o modo (paper/demo/real)."""
        if self.mode == 'demo':
            with self.lock:
                if any(t.get('demo') for t in self.pending_transfers):
                    return {'ok': False, 'error': 'demo ja em andamento'}
            o = dict(o)
            o['invest_usdt'] = self._demo_size(o)   # juros compostos
            bloqueio = self._demo_blocked_reason(o)
            if bloqueio:
                return {'ok': False, 'error': bloqueio}
            return self._execute_demo(scanner, o)
        return self.execute(scanner, o['pair'], o['buy_exchange'],
                            o['sell_exchange'], o['invest_usdt'], o['network'])

    def _home_price(self, prices, pair):
        """Preço de venda (bid) na corretora principal."""
        if not self.home_exchange:
            return None
        p = (prices.get(self.home_exchange) or {}).get(pair)
        return p if p and p.get('bid') else None

    def run_demo_now(self, scanner):
        """Força uma demo agora na melhor rota ao vivo (ignora o spread minimo).
        Usado pelo botão 'Testar agora' — garante demonstração visível."""
        snap = scanner.snapshot()
        prices = snap.get('prices', {}) or {}
        pairs = set()
        for m in prices.values():
            pairs.update(m.keys())
        best = None
        for pair in pairs:
            home = self._home_price(prices, pair)
            cands = []
            for buy_ex, m1 in prices.items():
                b = (m1.get(pair) or {}).get('ask')
                if not b:
                    continue
                if self.home_exchange:
                    if buy_ex == self.home_exchange or not home:
                        continue
                    g = (home['bid'] - b) / b * 100
                    cands.append((g, buy_ex, self.home_exchange))
                else:
                    for sell_ex, m2 in prices.items():
                        if sell_ex == buy_ex:
                            continue
                        s = (m2.get(pair) or {}).get('bid')
                        if not s or s <= b:
                            continue
                        cands.append(((s - b) / b * 100, buy_ex, sell_ex))
            for g, buy_ex, sell_ex in cands:
                if not best or g > best['gross_pct']:
                    best = {'pair': pair, 'buy_exchange': buy_ex,
                            'sell_exchange': sell_ex, 'gross_pct': g}
        if not best:
            return {'ok': False, 'error': 'sem preços das corretoras ainda'}
        o = dict(best)
        o['invest_usdt'] = self._demo_size(o)  # juros compostos: todo o saldo
        o['network'] = 'AUTO'
        o['net_pct'] = round(best['gross_pct'], 4)
        o['net_usdt'] = 0
        bloqueio = self._demo_blocked_reason(o)
        if bloqueio:
            return {'ok': False, 'error': bloqueio}
        return self._execute_demo(scanner, o)

    def _execute_demo(self, scanner, o):
        """Demo como se fosse real: compra na hora, 'transfere' e vende sozinho
        apos DEMO_SETTLE_SECONDS, usando o preco AO VIVO da venda."""
        import config as _cfg
        snap = scanner.snapshot()
        buy_side = snap['prices'].get(o['buy_exchange'], {}).get(o['pair'])
        sell_side = snap['prices'].get(o['sell_exchange'], {}).get(o['pair'])
        if not buy_side or not sell_side:
            return self._error_result(o['pair'], o['buy_exchange'], o['sell_exchange'],
                                      o['invest_usdt'], {}, 'Sem preço disponível (demo)')
        sim = simulate(o['pair'], o['buy_exchange'], buy_side['ask'],
                       o['sell_exchange'], sell_side['bid'], o['invest_usdt'], o['network'])
        started = time.time()
        buy_price = buy_side['ask']
        buy_qty = sim['quantity']
        chosen_net = next(n for n in sim['networks'] if n['network'] == sim['network'])
        tx_fee = chosen_net['withdrawal_fee_usd']

        # tempo real da arbitragem (ex: 3min de transferencia) — a venda so ocorre no fim
        settle = int(chosen_net.get('est_seconds') or getattr(_cfg, 'DEMO_SETTLE_SECONDS', 180))
        settle = max(30, min(settle, 3600))

        # capital unico: o dinheiro sai do pool e vira USDT na corretora de compra
        w_buy = self.demo_wallet_for(o['buy_exchange'])
        if float(self.demo_capital) < o['invest_usdt']:
            return {'ok': False, 'error': f"capital insuficiente: {fmt_brl(self.demo_capital)}"}
        self.demo_capital = round(self.demo_capital - o['invest_usdt'], 2)
        self.capital_in_use = {'exchange': o['buy_exchange'], 'amount': o['invest_usdt']}
        w_buy['USDT'] = round(w_buy.get('USDT', 0) + buy_qty, 6)
        if self.using_real_balance and o['buy_exchange'] in self.balances_cache:
            self.balances_cache[o['buy_exchange']]['BRL'] = round(
                max(0.0, self.balances_cache[o['buy_exchange']]['BRL'] - o['invest_usdt']), 2)

        with self.lock:
            self._demo_last = started
            self._demo_times.append(started)
            self._demo_routes[(o['buy_exchange'], o['sell_exchange'])] = started
            # guarda o spread desta operacao como referencia para as proximas
            try:
                ref = round(float(o.get('net_pct') or sim['net_pct']), 4)
            except Exception:
                ref = sim['net_pct']
            self._demo_ref = (ref, started)
            self._save_demo_state()
        stages = [{'stage': 'compra (demo)', 'exchange': o['buy_exchange'],
                   'price': round(buy_price, 8), 'qty': round(buy_qty, 8),
                   'seconds': 0}]
        # pernas da rota: o capital sai da casa, compra, viaja e o lucro volta
        casa = self.home_exchange
        if casa:
            stages.insert(0, {'stage': f'capital sai de {casa} (BRL → USDT)',
                              'exchange': casa, 'amount_brl': o['invest_usdt']})
        stages.append({'stage': f'USDT viaja {o["buy_exchange"]} → {o["sell_exchange"]}',
                       'network': sim['network'], 'fee_usd': tx_fee})
        transfer = {
            'id': self.counter + 1,
            'pair': o['pair'],
            'buy_exchange': o['buy_exchange'],
            'sell_exchange': o['sell_exchange'],
            'buy_price': buy_price,
            'buy_qty': buy_qty,
            'sell_qty': round(max(buy_qty - sim['networks'][0]['withdrawal_fee_usd'] / sell_side['bid'], 0), 8),
            'demo': True,
            'settle_at': started + settle,
            'deposit_addr': 'demo — sem transferência real',
            'deposit_tag': None,
            'network': sim['network'],
            'tx_fee': sim['networks'][0]['withdrawal_fee_usd'],
            'sim': sim,
            'sell_side': sell_side,
            'stages': stages,
            'started': started,
            'status': 'aguardando_transferencia',
            'invest_usdt': o['invest_usdt'],
        }
        with self.lock:
            self.counter += 1
            transfer['id'] = self.counter
            self.pending_transfers.append(transfer)
        print(f"[DEMO] Compra simulada {o['pair']} {o['buy_exchange']}->{o['sell_exchange']} "
              f"R${o['invest_usdt']} — vende sozinha em {settle}s")
        result = {
            'ok': True, 'id': transfer['id'], 'mode': 'demo',
            'status': 'aguardando_transferencia',
            'pair': o['pair'], 'buy_exchange': o['buy_exchange'],
            'sell_exchange': o['sell_exchange'], 'invest_usdt': o['invest_usdt'],
            'network': sim['network'], 'gross_pct': sim['gross_pct'],
            'net_usdt': sim['net_usdt'], 'net_pct': sim['net_pct'],
            'elapsed_ms': 0, 'elapsed_fmt': '0.0s',
            'est_real_seconds': sim['est_seconds'], 'stages': stages,
        }
        db.add_execution(result)
        return result

    def _execute_demo_sell(self, scanner, t):
        """Conclui a demo vendendo pelo preco ao vivo (como seria de verdade)."""
        snap = scanner.snapshot()
        cur = (snap['prices'].get(t['sell_exchange'], {}).get(t['pair']) or {})
        sell_price = cur.get('bid') or t['sell_side']['bid']
        sell_qty = min(float(t.get('sell_qty') or 0), float(t.get('buy_qty') or 0))
        elapsed_ms = int((time.time() - t['started']) * 1000)
        invest = t['invest_usdt']
        gross_brl = sell_qty * sell_price
        net = round(gross_brl - invest, 2)
        net_pct = round(net / invest * 100, 4) if invest else 0
        t['stages'].append({'stage': 'venda (demo)', 'exchange': t['sell_exchange'],
                            'price': round(sell_price, 8), 'qty': round(sell_qty, 8),
                            'seconds': round(time.time() - t['started'], 1)})
        casa = self.home_exchange
        if casa and casa != t['sell_exchange']:
            t['stages'].append({'stage': f'lucro volta para {casa} (BRL)',
                                'exchange': casa})
        # dinheiro volta (com lucro/prejuizo) para o capital que esta girando
        w_buy = self.demo_wallet_for(t['buy_exchange'])
        w_sell = self.demo_wallet_for(t['sell_exchange'])
        w_sell['USDT'] = round(max(0.0, w_sell.get('USDT', 0) - sell_qty), 6)
        volta = gross_brl * (1 - sim_fee_sell(t))
        self.demo_capital = round(self.demo_capital + volta, 2)
        self.capital_in_use = None
        if self.using_real_balance:
            if t['buy_exchange'] in self.balances_cache:
                self.balances_cache[t['buy_exchange']]['BRL'] = round(
                    self.balances_cache[t['buy_exchange']]['BRL'] + volta, 2)
            self.real_total_brl = round(self.real_total_brl + (volta - invest), 2)
        result = {
            'ok': True, 'id': t['id'], 'mode': 'demo', 'status': 'concluido',
            'pair': t['pair'], 'buy_exchange': t['buy_exchange'],
            'sell_exchange': t['sell_exchange'], 'invest_usdt': invest,
            'network': t['network'],
            'gross_pct': round((sell_price - t['buy_price']) / t['buy_price'] * 100, 4),
            'net_usdt': net, 'net_pct': net_pct,
            'elapsed_ms': elapsed_ms, 'elapsed_fmt': f"{elapsed_ms / 1000:.1f}s",
            'est_real_seconds': t['sim']['est_seconds'], 'stages': t['stages'],
        }
        db.add_execution(result)
        with self.lock:
            if t in self.pending_transfers:
                self.pending_transfers.remove(t)
        print(f"[DEMO] CONCLUIDA! {'Lucro' if net >= 0 else 'Prejuizo'}: R${net:.2f} ({net_pct}%)")

    def _execute_paper(self, pair, buy_exchange, sell_exchange, invest_usdt, sim, buy_side, sell_side):
        started = time.time()
        stages = []

        stages.append({'stage': 'compra', 'exchange': buy_exchange,
                       'price': round(buy_side['ask'], 8),
                       'qty': round(sim['quantity'], 8)})

        chosen_net = next(n for n in sim['networks'] if n['network'] == sim['network'])
        wq = round(chosen_net['withdrawal_fee_usd'] / sell_side['bid'], 8)
        stages.append({'stage': 'transferencia', 'rede': sim['network'],
                       'fee_usd': chosen_net['withdrawal_fee_usd'],
                       'est_minutes': chosen_net['est_seconds'] // 60,
                       'qty_burned': wq})

        sell_qty = sim['quantity'] - wq
        stages.append({'stage': 'venda', 'exchange': sell_exchange,
                       'price': round(sell_side['bid'], 8),
                       'qty': round(sell_qty, 8)})

        elapsed_ms = int((time.time() - started) * 1000)

        with self.lock:
            self.counter += 1
            exec_id = self.counter

        result = {
            'ok': True,
            'id': exec_id,
            'mode': 'paper',
            'pair': pair,
            'buy_exchange': buy_exchange,
            'sell_exchange': sell_exchange,
            'invest_usdt': invest_usdt,
            'network': sim['network'],
            'gross_pct': sim['gross_pct'],
            'net_usdt': sim['net_usdt'],
            'net_pct': sim['net_pct'],
            'elapsed_ms': elapsed_ms,
            'elapsed_fmt': f"{elapsed_ms / 1000:.2f}s",
            'est_real_seconds': sim['est_seconds'],
            'stages': stages,
        }
        db.add_execution(result)
        return result

    def _execute_semi_auto(self, scanner, pair, buy_exchange, sell_exchange, invest_usdt, sim, buy_side, sell_side):
        started = time.time()
        stages = []

        # ETAPA 1: Conectar na exchange de compra
        try:
            buy_ex = self._get_exchange(buy_exchange)
        except Exception as e:
            return self._error_result(pair, buy_exchange, sell_exchange, invest_usdt, sim, f'Erro ao conectar {buy_exchange}: {str(e)[:100]}')

        # ETAPA 2: Verificar saldo
        try:
            bal = buy_ex.fetch_balance()
            free_brl = float(bal.get('free', {}).get('BRL', 0) or 0)
            if free_brl < invest_usdt * 0.98:
                return self._error_result(pair, buy_exchange, sell_exchange, invest_usdt, sim,
                    f'Saldo BRL insuficiente: R${free_brl:.2f} (precisa R${invest_usdt:.2f})')
            print(f"[EXEC] Saldo {buy_exchange}: R${free_brl:.2f}")
        except Exception as e:
            return self._error_result(pair, buy_exchange, sell_exchange, invest_usdt, sim,
                f'Erro ao verificar saldo: {str(e)[:100]}')

        # ETAPA 3: Comprar USDT na exchange de compra
        try:
            print(f"[EXEC] Comprando USDT em {buy_exchange}...")
            buy_order = buy_ex.create_market_buy_order(pair, sim['quantity'], {'quoteOrderQty': invest_usdt})
            buy_price = float(buy_order.get('average', buy_side['ask']))
            buy_qty = float(buy_order.get('filled', sim['quantity']))
            print(f"[EXEC] Comprado: {buy_qty:.6f} USDT a R${buy_price:.4f}")
            stages.append({'stage': 'compra', 'exchange': buy_exchange,
                           'price': round(buy_price, 8), 'qty': round(buy_qty, 8),
                           'order_id': str(buy_order.get('id', '')),
                           'seconds': round(time.time() - started, 3)})
        except Exception as e:
            return self._error_result(pair, buy_exchange, sell_exchange, invest_usdt, sim,
                f'Erro ao comprar em {buy_exchange}: {str(e)[:150]}')

        # ETAPA 4: Buscar endereço de depósito na exchange de venda
        # (pede na rede da operação — endereço errado = perda do valor)
        try:
            sell_ex = self._get_exchange(sell_exchange)
            addr = None
            try:
                addr = sell_ex.fetch_deposit_address('USDT', {'network': network_name})
            except Exception:
                addr = sell_ex.fetch_deposit_address('USDT')
            deposit_addr = (addr or {}).get('address', '')
            deposit_tag = (addr or {}).get('tag')
            network_name = sim['network']
            print(f"[EXEC] Endereço {sell_exchange}: {deposit_addr} (rede: {network_name})")
        except Exception as e:
            return self._error_result(pair, buy_exchange, sell_exchange, invest_usdt, sim,
                f'Erro ao buscar endereço: {str(e)[:100]}')

        # ETAPA 5: Registrar transferência pendente
        chosen_net = next(n for n in sim['networks'] if n['network'] == sim['network'])
        tx_fee = chosen_net['withdrawal_fee_usd']

        transfer = {
            'id': self.counter + 1,
            'pair': pair,
            'buy_exchange': buy_exchange,
            'sell_exchange': sell_exchange,
            'buy_price': buy_price,
            'buy_qty': buy_qty,
            # vende SÓ o que foi transferido (nunca o saldo antigo da conta)
            'sell_qty': round(max(buy_qty - tx_fee / sell_side['bid'], 0), 8),
            'deposit_addr': deposit_addr,
            'deposit_tag': deposit_tag,
            'network': network_name,
            'tx_fee': tx_fee,
            'sim': sim,
            'sell_side': sell_side,
            'stages': stages,
            'started': started,
            'status': 'aguardando_transferencia',
            'invest_usdt': invest_usdt,
        }

        with self.lock:
            self.counter += 1
            transfer['id'] = self.counter
            self.pending_transfers.append(transfer)

        print(f"[EXEC] ✅ Compra concluída! Aguardando transferência manual.")
        print(f"[EXEC] 📋 TRANSFERENCIA NECESSARIA:")
        print(f"[EXEC]    De: {buy_exchange}")
        print(f"[EXEC]    Para: {sell_exchange}")
        print(f"[EXEC]    Quantidade: {buy_qty:.6f} USDT")
        print(f"[EXEC]    Rede: {network_name}")
        print(f"[EXEC]    Endereço: {deposit_addr}")
        if deposit_tag:
            print(f"[EXEC]    Tag/Memo: {deposit_tag}")
        print(f"[EXEC] ⏳ Aguardando depósito em {sell_exchange}...")

        result = {
            'ok': True,
            'id': transfer['id'],
            'mode': 'real',
            'status': 'aguardando_transferencia',
            'pair': pair,
            'buy_exchange': buy_exchange,
            'sell_exchange': sell_exchange,
            'invest_usdt': invest_usdt,
            'network': network_name,
            'gross_pct': sim['gross_pct'],
            'net_usdt': sim['net_usdt'],
            'net_pct': sim['net_pct'],
            'elapsed_ms': int((time.time() - started) * 1000),
            'elapsed_fmt': f"{(time.time() - started):.1f}s",
            'est_real_seconds': sim['est_seconds'],
            'stages': stages,
            'transfer': {
                'qty': round(buy_qty, 6),
                'network': network_name,
                'deposit_address': deposit_addr,
                'deposit_tag': deposit_tag,
                'from': buy_exchange,
                'to': sell_exchange,
                'tx_fee_usd': tx_fee,
            },
        }
        db.add_execution(result)
        return result

    def check_deposits(self, scanner):
        with self.lock:
            pending = list(self.pending_transfers)

        for t in pending:
            # DEMO: vende sozinha quando chega a hora, pelo preço ao vivo
            if t.get('demo'):
                try:
                    if time.time() >= t.get('settle_at', 0):
                        self._execute_demo_sell(scanner, t)
                except Exception as e:
                    print(f"[DEMO] ⚠️ Erro ao concluir: {str(e)[:100]}")
                continue

            if t['status'] != 'aguardando_transferencia':
                continue

            try:
                sell_ex = self._get_exchange(t['sell_exchange'])
                bal = sell_ex.fetch_balance()
                usdt_free = float(bal.get('free', {}).get('USDT', 0) or 0)

                expected_min = t['buy_qty'] - t['tx_fee'] / t['sell_side']['bid'] - 0.1

                if usdt_free >= expected_min:
                    print(f"[EXEC] ✅ Depósito confirmado em {t['sell_exchange']}! ({usdt_free:.6f} USDT)")
                    self._execute_sell_after_deposit(t, sell_ex, usdt_free)
                else:
                    print(f"[EXEC] ⏳ Aguardando... {t['sell_exchange']} USDT: {usdt_free:.6f} (esperado: {expected_min:.6f})")

            except Exception as e:
                print(f"[EXEC] ⚠️ Erro ao verificar depósito: {str(e)[:100]}")

    def _execute_sell_after_deposit(self, transfer, sell_ex, available_usdt):
        t = transfer
        t['status'] = 'vendendo'

        try:
            # vende no máximo o que a operação transferiu (protege saldo antigo)
            sell_qty = min(float(available_usdt), float(t.get('sell_qty') or available_usdt))
            print(f"[EXEC] Vendendo {sell_qty:.6f} USDT em {t['sell_exchange']}...")

            sell_order = sell_ex.create_market_sell_order(t['pair'], sell_qty)
            sell_price = float(sell_order.get('average', t['sell_side']['bid']))
            sold_qty = float(sell_order.get('filled', sell_qty))

            print(f"[EXEC] ✅ Vendido: {sold_qty:.6f} USDT a R${sell_price:.4f}")

            elapsed_ms = int((time.time() - t['started']) * 1000)
            invest = t['invest_usdt']
            gross_brl = sold_qty * sell_price
            net_usdt = gross_brl - invest
            net_pct = round(net_usdt / invest * 100, 4)

            t['stages'].append({'stage': 'venda', 'exchange': t['sell_exchange'],
                                'price': round(sell_price, 8), 'qty': round(sold_qty, 8),
                                'order_id': str(sell_order.get('id', '')),
                                'seconds': round(time.time() - t['started'], 3)})

            result = {
                'ok': True,
                'id': t['id'],
                'mode': 'real',
                'status': 'concluido',
                'pair': t['pair'],
                'buy_exchange': t['buy_exchange'],
                'sell_exchange': t['sell_exchange'],
                'invest_usdt': invest,
                'network': t['network'],
                'gross_pct': round((sell_price - t['buy_price']) / t['buy_price'] * 100, 4),
                'net_usdt': round(net_usdt, 2),
                'net_pct': net_pct,
                'elapsed_ms': elapsed_ms,
                'elapsed_fmt': f"{elapsed_ms / 1000:.1f}s",
                'est_real_seconds': t['sim']['est_seconds'],
                'stages': t['stages'],
            }
            db.add_execution(result)

            with self.lock:
                if t in self.pending_transfers:
                    self.pending_transfers.remove(t)

            print(f"[EXEC] 🎉 OPERAÇÃO CONCLUÍDA! Lucro: R${net_usdt:.2f} ({net_pct}%)")

        except Exception as e:
            print(f"[EXEC] ❌ Erro ao vender: {str(e)[:150]}")
            t['status'] = 'erro_venda'

    def get_pending(self):
        now = time.time()
        with self.lock:
            return [{
                'id': t['id'],
                'pair': t['pair'],
                'from': t['buy_exchange'],
                'to': t['sell_exchange'],
                'qty': round(t['buy_qty'], 6),
                'network': t['network'],
                'deposit_address': t['deposit_addr'],
                'deposit_tag': t.get('deposit_tag'),
                'tx_fee_usd': t['tx_fee'],
                'status': t['status'],
                'demo': bool(t.get('demo')),
                'seconds_left': max(0, int(t.get('settle_at', 0) - now)) if t.get('demo') else None,
                'invest_usdt': t.get('invest_usdt', 0),
            } for t in self.pending_transfers]

    def _error_result(self, pair, buy_exchange, sell_exchange, invest_usdt, sim, error_msg):
        with self.lock:
            self.counter += 1
            exec_id = self.counter
        result = {
            'ok': False,
            'id': exec_id,
            'mode': self.mode,
            'pair': pair,
            'buy_exchange': buy_exchange,
            'sell_exchange': sell_exchange,
            'invest_usdt': invest_usdt,
            'network': sim.get('network', 'AUTO'),
            'gross_pct': 0,
            'net_usdt': 0,
            'net_pct': 0,
            'elapsed_ms': 0,
            'elapsed_fmt': '0.00s',
            'est_real_seconds': 0,
            'error': error_msg,
            'stages': [{'stage': 'erro', 'error': error_msg}],
        }
        db.add_execution(result)
        return result


executor = Executor()
