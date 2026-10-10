import threading
import time
from datetime import datetime

import ccxt

import config


def fmt_time(seconds):
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    rest = seconds % 60
    return f"{minutes}min {rest:02d}s"


def simulate(pair, buy_exchange, buy_price, sell_exchange, sell_price, invest, network='AUTO'):
    asset = pair.split('/')[0]
    fee_buy = config.TAKER_FEES.get(buy_exchange, 0.001)
    fee_sell = config.TAKER_FEES.get(sell_exchange, 0.001)

    qty = invest / buy_price * (1 - fee_buy)
    gross_pct = (sell_price - buy_price) / buy_price * 100

    ex_withdraw = config.WITHDRAWAL_FEES.get(buy_exchange, {})

    net_ids = list(config.NETWORKS) if network == 'AUTO' else [network]
    results = []
    for nid in net_ids:
        info = config.NETWORKS.get(nid, {'fee_usd': 1.0, 'minutes': 5})
        fee_usd = ex_withdraw.get(nid, info['fee_usd'])
        withdraw_qty = fee_usd / sell_price
        q2 = qty - withdraw_qty
        gross = q2 * sell_price
        final = gross * (1 - fee_sell)
        net = final - invest
        est = config.BUY_SECONDS + info['minutes'] * 60 + config.SELL_SECONDS
        results.append({
            'network': nid,
            'withdrawal_fee_usd': fee_usd,
            'net_usdt': round(net, 2),
            'net_pct': round(net / invest * 100, 4),
            'est_seconds': est,
        })

    results.sort(key=lambda r: r['net_usdt'], reverse=True)
    chosen = results[0]

    # Preferencia BEP20/Polygon: se uma rede prioritaria ficar proxima da melhor
    # (diferenca menor que $0.10 ou 0.01%), usa a prioritaria (mais barata/rapida)
    try:
        prio = getattr(config, 'NETWORK_PRIORITY', [])
        if prio:
            order = {nid: i for i, nid in enumerate(prio)}
            best_net = chosen['net_usdt']
            cands = [r for r in results
                     if order.get(r['network'], 99) < order.get(chosen['network'], 99)
                     and (best_net - r['net_usdt']) <= max(0.10, invest * 0.0001)]
            if cands:
                cands.sort(key=lambda r: order.get(r['network'], 99))
                chosen = cands[0]
    except Exception:
        pass

    return {
        'asset': asset,
        'invest_usdt': invest,
        'buy_price': buy_price,
        'sell_price': sell_price,
        'gross_pct': round(gross_pct, 4),
        'quantity': qty,
        'taker_buy': fee_buy,
        'taker_sell': fee_sell,
        'network': chosen['network'],
        'net_usdt': chosen['net_usdt'],
        'net_pct': chosen['net_pct'],
        'est_seconds': chosen['est_seconds'],
        'est_time_fmt': fmt_time(chosen['est_seconds']),
        'networks': results,
    }


class Scanner:
    def __init__(self):
        self.lock = threading.Lock()
        self.exchanges = {}
        self.prices = {}
        self.opportunities = []
        self.connected = False
        self.last_scan = None
        self.scan_seconds = None
        self.errors = {}
        self._last_sim = {}
        self.near_miss = []

    def load_exchanges(self):
        from concurrent.futures import ThreadPoolExecutor, as_completed

        targets = [e for e in config.EXCHANGES if e != 'mercadobitcoin']
        is_cloud = config.IS_CLOUD
        deadline = time.time() + (240 if is_cloud else 150)

        def _load(eid):
            try:
                import os
                opts = {
                    'enableRateLimit': True,
                    # timeout generoso: carregar lista de pares (load_markets) é lento
                    # em corretoras grandes (binance/okx) e precisa de tempo
                    'timeout': 30000 if not is_cloud else 60000,
                    'options': {'defaultType': 'spot', 'recvWindow': 60000},
                }
                if eid == 'binance':
                    opts['options']['fetchMarkets'] = ['spot']

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
                if eid in ('binance', 'bybit'):
                    try:
                        ex.load_markets()
                    except Exception:
                        pair = 'USDT/BRL'
                        ex.markets = {pair: {'id': 'USDTBRL', 'symbol': pair, 'base': 'USDT', 'quote': 'BRL', 'active': True, 'type': 'spot'}}
                        ex.markets_by_id = {'USDTBRL': ex.markets[pair]}
                else:
                    try:
                        ex.load_markets()
                    except Exception as e:
                        # A MEXC (e outras) rejeita o catalogo inteiro quando a
                        # chave esta errada: "API-key format invalid". Mas para
                        # PRECO PUBLICO a chave nao e necessaria. Recarrega sem
                        # credencial e devolve a chave depois - assim o scanner
                        # volta a funcionar e o erro real aparece so na hora de
                        # consultar saldo/negociar, que e onde a chave importa.
                        if not api_key:
                            raise
                        print(f"[LEVERAGE ARB] {eid} recusou a chave ao carregar "
                              f"({str(e)[:60]}) - tentando so preco publico")
                        sem_chave = getattr(ccxt, eid)({
                            k: v for k, v in opts.items()
                            if k not in ('apiKey', 'secret', 'password')})
                        sem_chave.load_markets()
                        sem_chave.apiKey = api_key
                        sem_chave.secret = secret
                        if passphrase:
                            sem_chave.password = passphrase
                        ex = sem_chave
                return eid, ex
            except Exception as e:
                # falha silenciosa aqui deixa a corretora sumir da tela sem
                # explicar o motivo - o log e a unica pista que existe
                print(f"[LEVERAGE ARB] {eid} nao carregou: {str(e)[:110]}")
                return eid, None

        loaded = {}
        remaining = []

        if is_cloud:
            for eid in targets:
                if time.time() > deadline:
                    remaining.append(eid)
                    continue
                eid_ok, ex = _load(eid)
                if ex is not None:
                    loaded[eid_ok] = ex
                    print(f"[LEVERAGE ARB] {eid_ok} conectado")
                else:
                    remaining.append(eid)
                    print(f"[LEVERAGE ARB] {eid} falhou")
            if len(loaded) < 3:
                for eid in remaining[:]:
                    if time.time() > deadline:
                        break
                    try:
                        opts = {
                            'enableRateLimit': True,
                            'timeout': 60000,
                            'options': {'defaultType': 'spot'},
                        }
                        if eid == 'binance' and config.BINANCE_API_KEY:
                            opts['apiKey'] = config.BINANCE_API_KEY
                            opts['secret'] = config.BINANCE_SECRET_KEY
                        ex = getattr(ccxt, eid)(opts)
                        loaded[eid] = ex
                        remaining.remove(eid)
                        print(f"[LEVERAGE ARB] {eid} conectado (retry)")
                    except Exception:
                        print(f"[LEVERAGE ARB] {eid} retry falhou")
        else:
            pool = ThreadPoolExecutor(max_workers=3)
            fut_to_eid = {pool.submit(_load, eid): eid for eid in targets}
            try:
                for fut in as_completed(fut_to_eid):
                    eid = fut_to_eid[fut]
                    try:
                        _, ex = fut.result()
                    except Exception:
                        ex = None
                    if ex is not None:
                        loaded[eid] = ex
                    else:
                        remaining.append(eid)
            except TimeoutError:
                for fut, eid in fut_to_eid.items():
                    if not fut.done():
                        remaining.append(eid)
            finally:
                pool.shutdown(wait=False, cancel_futures=True)

        self.exchanges.update(loaded)
        for eid in loaded:
            self.errors.pop(eid, None)
        for eid in remaining:
            self.errors[eid] = self.errors.get(eid, 'nao respondeu a tempo')
        return len(self.exchanges)

    def ensure_exchanges(self):
        if getattr(self, '_reloading', False):
            return
        expected = len(config.EXCHANGES) - 1
        if len(self.exchanges) >= expected:
            return
        now = time.time()
        if now - getattr(self, '_last_reload', 0) < 300:
            return
        self._last_reload = now

        def _reload():
            self._reloading = True
            try:
                self.load_exchanges()
            except Exception:
                pass
            finally:
                self._reloading = False

        threading.Thread(target=_reload, daemon=True).start()

    def _fetch_mb(self):
        try:
            import requests
            mb_map = {p.replace('/', '-'): p for p in config.PAIRS}
            r = requests.get(
                'https://api.mercadobitcoin.net/api/v4/tickers',
                params={'symbols': ','.join(mb_map.keys())},
                timeout=10,
            )
            m = {}
            for t in r.json():
                uni = mb_map.get(t.get('pair'))
                ask = float(t.get('sell') or 0)
                bid = float(t.get('buy') or 0)
                if uni and ask > 0 and bid > 0:
                    m[uni] = {'ask': ask, 'bid': bid}
            if m:
                return m
        except Exception as e:
            with self.lock:
                self.errors['mercadobitcoin'] = str(e)[:120]
        return None

    def _fetch_direct(self, eid, ex):
        pair = 'USDT/BRL'
        try:
            if eid == 'binance':
                # Espelho publico oficial (contorna bloqueio 451 em IP de datacenter)
                import requests as _req
                try:
                    r = _req.get('https://data-api.binance.vision/api/v3/ticker/24hr',
                                 params={'symbol': 'USDTBRL'}, timeout=10)
                    d = r.json()
                    bid = float(d.get('bidPrice', 0))
                    ask = float(d.get('askPrice', 0))
                    if ask > 0 and bid > 0:
                        return {pair: {'ask': ask, 'bid': bid,
                                       'volume': float(d.get('quoteVolume', 0) or 0)}}
                except Exception:
                    pass
                d = ex.publicGetTickerPrice({'symbol': 'USDTBRL'})
                price = float(d.get('price', 0))
                if price > 0:
                    spread = price * 0.0005
                    return {pair: {'ask': price + spread, 'bid': price - spread}}
                with self.lock:
                    self.errors[eid] = f'binance api: {str(d)[:100]}'
            elif eid == 'bybit':
                d = ex.publicGetV5MarketTickers({'category': 'spot', 'symbol': 'USDTBRL'})
                items = d.get('result', {}).get('list', [])
                if items:
                    t = items[0]
                    ask = float(t.get('ask1Price', 0))
                    bid = float(t.get('bid1Price', 0))
                    if ask > 0 and bid > 0:
                        return {pair: {'ask': ask, 'bid': bid}}
                with self.lock:
                    self.errors[eid] = f'bybit api: {str(d)[:100]}'
            elif eid == 'mexc':
                import requests as _req
                r = _req.get('https://api.mexc.com/api/v3/ticker/24hr',
                             params={'symbol': 'BRLUSDT'}, timeout=10,
                             headers={'User-Agent': 'Mozilla/5.0'})
                d = r.json()
                brl_ask = float(d.get('askPrice', 0))
                brl_bid = float(d.get('bidPrice', 0))
                if brl_ask > 0 and brl_bid > 0:
                    usdt_ask = 1.0 / brl_bid
                    usdt_bid = 1.0 / brl_ask
                    return {pair: {'ask': round(usdt_ask, 4), 'bid': round(usdt_bid, 4)}}
                with self.lock:
                    self.errors[eid] = f'mexc api: {str(d)[:100]}'
            else:
                return None
        except Exception as e:
            with self.lock:
                self.errors[eid] = f'{eid} direct error: {str(e)[:100]}'
        return None

    def snapshot(self):
        with self.lock:
            all_prices = {}
            for eid in self.exchanges:
                if eid in self.prices:
                    all_prices[eid] = self.prices[eid]
                else:
                    all_prices[eid] = {}
            if 'mercadobitcoin' in self.prices:
                all_prices['mercadobitcoin'] = self.prices['mercadobitcoin']
            return {
                'connected': self.connected,
                'last_scan': self.last_scan,
                'scan_seconds': self.scan_seconds,
                'exchanges_ok': sorted(self.exchanges.keys()),
                'errors': dict(self.errors),
                'prices': all_prices,
                'opportunities': self.opportunities[:config.TOP_LIMIT],
                'near_miss': list(self.near_miss),
                'total_opportunities': len(self.opportunities),
                'best': self.opportunities[0] if self.opportunities else None,
            }

    def scan(self):
        t0 = time.time()
        self.ensure_exchanges()
        prices = {}

        with self.lock:
            self.errors.clear()

        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _fetch(eid, ex):
            m = {}
            # timeout curto só na leitura de preço: falhar rápido é melhor que
            # travar o scan inteiro (uma corretora lenta não pode derrubar as outras)
            timeout_original = getattr(ex, 'timeout', None)
            try:
                ex.timeout = 8000
            except Exception:
                pass
            for pair in config.PAIRS:
                try:
                    t = ex.fetch_ticker(pair)
                    if t and t.get('ask') and t.get('bid') and t['ask'] > 0 and t['bid'] > 0:
                        vol = t.get('quoteVolume') or t.get('baseVolume') or 0
                        try:
                            vol = float(vol or 0)
                        except Exception:
                            vol = 0
                        m[pair] = {'ask': t['ask'], 'bid': t['bid'], 'volume': vol}
                except Exception:
                    pass
                # A mesma moeda pode vir publicationada ao contrario: varias
                # corretoras listam BRL/USDT em vez de USDT/BRL. E o mesmo
                # mercado, so invertido — entao invertemos o preco em vez de
                # descartar a corretora.
                if pair not in m:
                    inverso = '/'.join(reversed(pair.split('/')))  # USDT/BRL -> BRL/USDT
                    try:
                        t = ex.fetch_ticker(inverso)
                        if t and t.get('ask') and t.get('bid') and t['ask'] > 0 and t['bid'] > 0:
                            m[pair] = {'ask': 1.0 / t['bid'],      # compro USDT pago o bid do BRL
                                       'bid': 1.0 / t['ask'],
                                       'volume': 0,
                                       'invertido': inverso}
                    except Exception:
                        pass
            if not m:
                direct = self._fetch_direct(eid, ex)
                if direct:
                    m = direct
            if timeout_original is not None:
                try:
                    ex.timeout = timeout_original
                except Exception:
                    pass
            if not m:
                if eid not in self.errors:
                    with self.lock:
                        self.errors[eid] = f'{eid} USDT/BRL not available'
                return eid, None, None
            return eid, m, None

        items = list(self.exchanges.items())

        fut_map = {}
        pool = ThreadPoolExecutor(max_workers=8)
        collected = set()
        try:
            for eid, ex in items:
                fut_map[pool.submit(_fetch, eid, ex)] = eid
            try:
                for fut in as_completed(fut_map, timeout=45):
                    eid = fut_map[fut]
                    collected.add(eid)
                    try:
                        _, m, err = fut.result()
                    except Exception:
                        continue
                    if err:
                        self.errors[eid] = err
                    elif m:
                        prices[eid] = m
            except TimeoutError:
                pass
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

        # coltagem final:-results que terminaram depois do tempo do as_completed
        # (sem isso, corretoras rápidas como a Binance se perdem por causa de uma lenta)
        for fut, eid in fut_map.items():
            if eid in collected:
                continue
            try:
                if not fut.done(timeout=0.1):
                    continue
                _, m, err = fut.result()
            except Exception:
                continue
            if err:
                self.errors.setdefault(eid, err)
            elif m:
                prices[eid] = m

        mb = self._fetch_mb()
        if mb:
            prices['mercadobitcoin'] = mb

        opps = []
        near = []
        min_spread = getattr(config, 'MIN_SPREAD_PCT', 0.10)
        try:
            min_spread = float(min_spread)
        except Exception:
            min_spread = 0.10
        for pair in config.PAIRS:
            exs = [eid for eid, m in prices.items() if pair in m]
            if len(exs) < 2:
                continue
            for buy_ex in exs:
                for sell_ex in exs:
                    if buy_ex == sell_ex:
                        continue
                    ask = prices[buy_ex][pair]['ask']
                    bid = prices[sell_ex][pair]['bid']
                    if not ask or not bid or bid <= ask:
                        continue
                    sim = simulate(pair, buy_ex, ask, sell_ex, bid, config.INVESTMENT_USDT, 'AUTO')
                    sim['pair'] = pair
                    sim['buy_exchange'] = buy_ex
                    sim['sell_exchange'] = sell_ex
                    if sim['net_pct'] >= min_spread and sim['net_usdt'] > 0:
                        opps.append(sim)
                    else:
                        near.append(sim)

        opps.sort(key=lambda x: x['net_pct'], reverse=True)
        opps = opps[:config.TOP_LIMIT]
        # rotas mais próximas de lucrar (mostra o que falta)
        near.sort(key=lambda x: x['net_pct'], reverse=True)
        near = near[:5]

        with self.lock:
            self.prices = prices
            self.opportunities = opps
            self.near_miss = near
            self.connected = True
            self.last_scan = datetime.utcnow().isoformat() + 'Z'
            self.scan_seconds = round(time.time() - t0, 2)
        return opps

    def pick_auto_sims(self, opps):
        now = time.time()
        picked = []
        for o in opps:
            if o['net_pct'] < config.AUTO_SIM_THRESHOLD:
                break
            key = (o['pair'], o['buy_exchange'], o['sell_exchange'], o['network'])
            last = self._last_sim.get(key, 0)
            if now - last < config.AUTO_SIM_COOLDOWN:
                continue
            self._last_sim[key] = now
            picked.append(o)
        return picked

    def _coins_from_balance(self, b):
        coins = {}
        for coin in ['BRL', 'USDT', 'BTC', 'ETH', 'SOL', 'USDC']:
            free = float((b.get('free') or {}).get(coin, 0) or 0)
            used = float((b.get('used') or {}).get(coin, 0) or 0)
            total = free + used
            if total > 0:
                coins[coin] = {'free': round(free, 8), 'used': round(used, 8),
                               'total': round(total, 8)}
        return coins

    def fetch_balance_one(self, eid):
        """Saldo de UMA corretora (rapido) — usado no teste de API."""
        import os as _os
        if eid == 'mercadobitcoin':
            return self._fetch_mb_balance()
        ex = self.exchanges.get(eid)
        if ex is None:
            return {'error': 'corretora nao conectada'}
        if not ex.apiKey:
            return {'error': 'sem API key'}
        try:
            b = ex.fetch_balance()
            return {'ok': True, 'coins': self._coins_from_balance(b)}
        except Exception as e:
            return {'error': f'{type(e).__name__}: {str(e)[:120]}'}

    def _fetch_mb_balance(self):
        import hmac, hashlib, time as _t, os as _os, requests as _req
        mb_key = _os.environ.get('MERCADOBITCOIN_API_KEY', '')
        mb_secret = _os.environ.get('MERCADOBITCOIN_SECRET_KEY', '')
        if not (mb_key and mb_secret):
            return {'error': 'sem API key/secret'}
        try:
            ts = str(int(_t.time()))
            msg = f'{mb_key}{ts}'
            sign = hmac.new(mb_secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
            r = _req.get('https://api.mercadobitcoin.net/api/v4/my-balance/',
                         headers={'API-Key': mb_key, 'API-Sign': sign, 'Timestamp': ts},
                         timeout=12)
            data = r.json()
            coins = {}
            for item in data.get('balances', []):
                coin = item.get('currency', '')
                free = float(item.get('available', 0) or 0)
                locked = float(item.get('locked', 0) or 0)
                if free + locked > 0:
                    coins[coin] = {'free': round(free, 8), 'used': round(locked, 8),
                                   'total': round(free + locked, 8)}
            return {'ok': True, 'coins': coins}
        except Exception as e:
            return {'error': f'{type(e).__name__}: {str(e)[:120]}'}

    def fetch_balances(self):
        balances = {}
        for eid, ex in self.exchanges.items():
            try:
                if not ex.apiKey:
                    balances[eid] = {'error': 'sem API key'}
                    continue
                b = ex.fetch_balance()
                coins = {}
                for coin in ['USDT', 'BRL', 'BTC', 'ETH', 'SOL', 'USDC']:
                    free = float(b.get('free', {}).get(coin, 0) or 0)
                    used = float(b.get('used', {}).get(coin, 0) or 0)
                    total = free + used
                    if total > 0:
                        coins[coin] = {'free': round(free, 8), 'used': round(used, 8), 'total': round(total, 8)}
                if coins:
                    balances[eid] = {'ok': True, 'coins': coins}
                else:
                    balances[eid] = {'ok': True, 'coins': {}, 'note': 'conta vazia'}
            except Exception as e:
                balances[eid] = {'error': str(e)[:120]}

        import os
        mb_key = os.environ.get('MERCADOBITCOIN_API_KEY', '')
        mb_secret = os.environ.get('MERCADOBITCOIN_SECRET_KEY', '')
        if mb_key and mb_secret:
            try:
                import hmac, hashlib, time as _t, requests as _req
                ts = str(int(_t.time()))
                msg = f'{mb_key}{ts}'
                sign = hmac.new(mb_secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
                r = _req.get(
                    'https://api.mercadobitcoin.net/api/v4/my-balance/',
                    headers={
                        'API-Key': mb_key,
                        'API-Sign': sign,
                        'Timestamp': ts,
                    },
                    timeout=10,
                )
                data = r.json()
                coins = {}
                for item in data.get('balances', []):
                    coin = item.get('currency', '')
                    free = float(item.get('available', 0))
                    locked = float(item.get('locked', 0))
                    total = free + locked
                    if total > 0:
                        coins[coin] = {'free': round(free, 8), 'used': round(locked, 8), 'total': round(total, 8)}
                balances['mercadobitcoin'] = {'ok': True, 'coins': coins} if coins else {'ok': True, 'coins': {}, 'note': 'conta vazia'}
            except Exception as e:
                balances['mercadobitcoin'] = {'error': str(e)[:120]}
        else:
            balances['mercadobitcoin'] = {'error': 'sem API key/secret'}

        return balances
