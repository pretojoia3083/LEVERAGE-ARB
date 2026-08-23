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

    net_ids = list(config.NETWORKS) if network == 'AUTO' else [network]
    results = []
    for nid in net_ids:
        info = config.NETWORKS.get(nid, {'fee_usd': 1.0, 'minutes': 5})
        withdraw_qty = info['fee_usd'] / sell_price
        q2 = qty - withdraw_qty
        gross = q2 * sell_price
        final = gross * (1 - fee_sell)
        net = final - invest
        est = config.BUY_SECONDS + info['minutes'] * 60 + config.SELL_SECONDS
        results.append({
            'network': nid,
            'withdrawal_fee_usd': info['fee_usd'],
            'net_usdt': round(net, 2),
            'net_pct': round(net / invest * 100, 4),
            'est_seconds': est,
        })

    results.sort(key=lambda r: r['net_usdt'], reverse=True)
    chosen = results[0]

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

    def load_exchanges(self):
        from concurrent.futures import ThreadPoolExecutor, as_completed

        targets = [e for e in config.EXCHANGES if e != 'mercadobitcoin']
        deadline = time.time() + 150

        def _load(eid):
            try:
                opts = {
                    'enableRateLimit': True,
                    'timeout': 20000,
                    'options': {'defaultType': 'spot'},
                }
                if eid in ('binance', 'htx'):
                    opts['options']['fetchMarkets'] = ['spot']
                if eid == 'bitget' and config.BITGET_API_KEY:
                    opts['apiKey'] = config.BITGET_API_KEY
                    opts['secret'] = config.BITGET_SECRET_KEY
                    if config.BITGET_PASSPHRASE:
                        opts['password'] = config.BITGET_PASSPHRASE
                ex = getattr(ccxt, eid)(opts)
                ex.load_markets()
                return eid, ex
            except Exception:
                return eid, None

        loaded = {}
        pool = ThreadPoolExecutor(max_workers=3)
        fut_to_eid = {pool.submit(_load, eid): eid for eid in targets}
        remaining = []
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

    def snapshot(self):
        with self.lock:
            return {
                'connected': self.connected,
                'last_scan': self.last_scan,
                'scan_seconds': self.scan_seconds,
                'exchanges_ok': sorted(self.exchanges.keys()),
                'errors': dict(self.errors),
                'prices': self.prices,
                'opportunities': self.opportunities[:config.TOP_LIMIT],
                'total_opportunities': len(self.opportunities),
                'best': self.opportunities[0] if self.opportunities else None,
            }

    def scan(self):
        t0 = time.time()
        self.ensure_exchanges()
        prices = {}

        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _fetch(eid, ex):
            try:
                wanted = [p for p in config.PAIRS if p in getattr(ex, 'markets', {}) or not getattr(ex, 'markets', None)]
                if not wanted:
                    return eid, None, None
                tickers = ex.fetch_tickers(wanted)
                m = {}
                for pair in wanted:
                    t = tickers.get(pair)
                    if t and t.get('ask') and t.get('bid') and t['ask'] > 0 and t['bid'] > 0:
                        m[pair] = {'ask': t['ask'], 'bid': t['bid']}
                return eid, m, None
            except Exception as e:
                return eid, None, str(e)[:120]

        items = [(eid, ex) for eid, ex in self.exchanges.items()
                 if not getattr(ex, 'markets', None)
                 or any(p in ex.markets for p in config.PAIRS)]

        fut_map = {}
        pool = ThreadPoolExecutor(max_workers=6)
        try:
            for eid, ex in items:
                fut_map[pool.submit(_fetch, eid, ex)] = eid
            try:
                for fut in as_completed(fut_map, timeout=30):
                    eid = fut_map[fut]
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

        mb = self._fetch_mb()
        if mb:
            prices['mercadobitcoin'] = mb

        opps = []
        for pair in config.PAIRS:
            asks = [(eid, m[pair]['ask']) for eid, m in prices.items() if pair in m]
            bids = [(eid, m[pair]['bid']) for eid, m in prices.items() if pair in m]
            if len(asks) < 2 or len(bids) < 2:
                continue
            buy_ex, ask = min(asks, key=lambda x: x[1])
            sell_ex, bid = max(bids, key=lambda x: x[1])
            if buy_ex == sell_ex:
                continue
            sim = simulate(pair, buy_ex, ask, sell_ex, bid, config.INVESTMENT_USDT, 'AUTO')
            sim['pair'] = pair
            sim['buy_exchange'] = buy_ex
            sim['sell_exchange'] = sell_ex
            opps.append(sim)

        opps.sort(key=lambda x: x['net_pct'], reverse=True)

        with self.lock:
            self.prices = prices
            self.opportunities = opps
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
