import os
import threading
import time

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
import db
import dex
from engine import Scanner, simulate
from executor import executor

load_dotenv()

app = FastAPI(title="LEVERAGE ARB")

scanner = Scanner()

AUTO_TRADE = False
LAST_OPPS = []


@app.on_event("startup")
def startup():
    def bootstrap():
        global LAST_OPPS, AUTO_TRADE
        # valor, spread, modo e auto salvos continuam valendo após reiniciar/atualizar
        try:
            inv = db.get_setting('invest_usdt')
            if inv and float(inv) >= 10:
                config.INVESTMENT_USDT = float(inv)
            executor.set_capital_base(config.INVESTMENT_USDT)
            spr = db.get_setting('min_spread')
            if spr is not None and 0 <= float(spr) <= 5:
                config.MIN_SPREAD_PCT = float(spr)
            md = db.get_setting('mode')
            if md in ('paper', 'demo', 'real'):
                executor.set_mode(md)
            hm = db.get_setting('home_exchange')
            if hm:
                executor.set_home(hm)
            ac = db.get_setting('demo_all_capital')
            if ac is not None:
                config.DEMO_ALL_CAPITAL = ac == '1'
            _load_keys_from_db()
            at = db.get_setting('auto_trade')
            AUTO_TRADE = (at == '1')
            print(f"[LEVERAGE ARB] config salva: invest R${config.INVESTMENT_USDT} · spread {config.MIN_SPREAD_PCT}% · modo {executor.mode} · auto {'ON' if AUTO_TRADE else 'OFF'}")
            if executor.mode == 'real' and AUTO_TRADE:
                print("[LEVERAGE ARB] ⚠️ modo REAL com auto ON restaurado — confira operações em aberto")
        except Exception as e:
            print(f"[LEVERAGE ARB] config padrao ({e})")
        n = scanner.load_exchanges()
        print(f"[LEVERAGE ARB] {n} corretoras conectadas")
        while True:
            try:
                opps = scanner.scan()
                LAST_OPPS = opps
                for o in scanner.pick_auto_sims(opps):
                    db.add_simulation({
                        'trigger': 'auto',
                        'pair': o['pair'],
                        'buy_exchange': o['buy_exchange'],
                        'sell_exchange': o['sell_exchange'],
                        'buy_price': o['buy_price'],
                        'sell_price': o['sell_price'],
                        'gross_pct': o['gross_pct'],
                        'invest_usdt': o['invest_usdt'],
                        'net_usdt': o['net_usdt'],
                        'net_pct': o['net_pct'],
                        'network': o['network'],
                        'est_seconds': o['est_seconds'],
                    })
                    print(f"[SIM] {o['pair']} {o['buy_exchange']}->{o['sell_exchange']} "
                          f"+{o['net_pct']}% via {o['network']}")

                if AUTO_TRADE and opps:
                    best = opps[0]
                    min_pct = config.MIN_SPREAD_PCT
                    if best['net_pct'] >= min_pct and best['net_usdt'] >= config.AUTO_SIM_DOLLAR_MIN:
                        if executor.mode == 'demo':
                            r = executor.execute_auto(scanner, best)
                            if r.get('ok'):
                                print(f"[DEMO-AUTO] Demo iniciada {best['pair']} "
                                      f"{best['buy_exchange']}->{best['sell_exchange']} +{best['net_pct']}%")
                        else:
                            print(f"[AUTO] Executando {best['pair']} {best['buy_exchange']}->{best['sell_exchange']} +{best['net_pct']}% ({executor.mode})")
                            executor.execute(
                                scanner, best['pair'],
                                best['buy_exchange'], best['sell_exchange'],
                                best['invest_usdt'], best['network'],
                            )

                if executor.mode in ('real', 'demo') or executor.get_pending():
                    executor.check_deposits(scanner)
                # saldo real sempre (throttled ~1min dentro do refresh)
                executor.refresh_real_balances(scanner)
            except Exception as e:
                print(f"[ERRO] scan: {e}")
            time.sleep(config.SCAN_INTERVAL)

    threading.Thread(target=bootstrap, daemon=True).start()
    print("[LEVERAGE ARB] scanner iniciado")


class SimRequest(BaseModel):
    pair: str
    buy_exchange: str
    sell_exchange: str
    invest_usdt: float = config.INVESTMENT_USDT
    network: str = 'AUTO'


@app.get("/")
def home():
    return FileResponse("static/index.html")


@app.get("/app.js")
def serve_app_js():
    # sem cache: garante que o navegador sempre usa o JS atual
    return FileResponse("static/app.js", media_type="application/javascript",
                        headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.get("/style.css")
def serve_style_css():
    return FileResponse("static/style.css", media_type="text/css",
                        headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.get("/api/health")
def health():
    # endpoint leve p/ UptimeRobot manter o Render acordado 24/7
    return {'ok': True, 'ts': time.time()}


@app.get("/api/db-info")
def db_info():
    try:
        import importlib.util
        return {
            'engine': 'Postgres' if db.USE_PG else 'SQLite',
            'has_url': bool(db.DATABASE_URL),
            'psycopg': bool(importlib.util.find_spec('psycopg')),
            'sims_24h': db.stats(24).get('total_simulations', 0),
            'invest_salvo': db.get_setting('invest_usdt'),
            'spread_salvo': db.get_setting('min_spread'),
        }
    except Exception as e:
        return {'erro': str(e)[:200]}


@app.get("/api/spread")
def get_spread():
    return {'min_spread': config.MIN_SPREAD_PCT, 'options': config.SPREAD_OPTIONS}


class SpreadRequest(BaseModel):
    min_spread: float


@app.post("/api/spread")
def set_spread(req: SpreadRequest):
    v = float(req.min_spread)
    if v not in config.SPREAD_OPTIONS and v not in [float(x) for x in config.SPREAD_OPTIONS]:
        # aceita qualquer valor entre 0 e 5 mesmo fora dos presets
        if not (0 <= v <= 5):
            return {'error': 'spread invalido'}
    config.MIN_SPREAD_PCT = v
    try:
        db.set_setting('min_spread', v)
    except Exception:
        pass
    print(f"[SPREAD] minimo agora: {v}%")
    return {'ok': True, 'min_spread': v}


@app.get("/api/investment")
def get_investment():
    return {'invest_usdt': config.INVESTMENT_USDT}


class InvestmentRequest(BaseModel):
    invest_usdt: float


@app.post("/api/investment")
def set_investment(req: InvestmentRequest):
    v = float(req.invest_usdt)
    if v < 10 or v > 1000000:
        return {'error': 'valor invalido (10 a 1000000)'}
    config.INVESTMENT_USDT = v
    try:
        db.set_setting('invest_usdt', v)
    except Exception:
        pass
    # o valor configurado e tambem o capital inicial da demo
    executor.set_capital_base(v)
    print(f"[INVEST] agora: {v} USDT")
    return {'ok': True, 'invest_usdt': v}


@app.get("/api/dex")
def get_dex():
    try:
        return dex.snapshot()
    except Exception as e:
        return {'rows': [], 'error': str(e)[:150]}


@app.post("/api/demo/run")
def demo_run():
    try:
        return executor.run_demo_now(scanner)
    except Exception as e:
        return {'ok': False, 'error': str(e)[:150]}


@app.get("/api/home")
def get_home():
    return {'home': config.HOME_EXCHANGE, 'auto': 'auto' in ('', config.HOME_EXCHANGE)}


class HomeRequest(BaseModel):
    home: str


@app.post("/api/home")
def set_home(req: HomeRequest):
    executor.set_home(req.home)
    return {'ok': True, 'home': config.HOME_EXCHANGE}


@app.get("/api/all-capital")
def get_all_capital():
    return {'all_capital': bool(getattr(config, 'DEMO_ALL_CAPITAL', True))}


class AllCapitalRequest(BaseModel):
    value: bool


@app.post("/api/all-capital")
def set_all_capital(req: AllCapitalRequest):
    config.DEMO_ALL_CAPITAL = bool(req.value)
    try:
        db.set_setting('demo_all_capital', '1' if config.DEMO_ALL_CAPITAL else '0')
    except Exception:
        pass
    print(f"[DEMO] usar todo o saldo: {'SIM' if config.DEMO_ALL_CAPITAL else 'NAO'}")
    return {'ok': True, 'all_capital': config.DEMO_ALL_CAPITAL}


@app.get("/api/demo/status")
def demo_status():
    try:
        s = executor.demo_status(scanner)
        try:
            # so operacoes DEMO (nao mistura paper/real no resultado da demo)
            d = db.daily_stats(mode='demo')
            s['lucro_hoje'] = d['dia']['net']
            if not s.get('usando_saldo_real'):
                # saldo da demo = capital inicial + lucro de hoje
                s['capital_hoje'] = round(float(executor.capital_base) + float(d['dia']['net']), 2)
        except Exception:
            pass
        return s
    except Exception as e:
        return {'erro': str(e)[:150]}


@app.get("/api/dashboard")
def dashboard():
    snap = scanner.snapshot()
    snap['investment'] = config.INVESTMENT_USDT
    snap['auto_trade'] = AUTO_TRADE
    snap['mode'] = executor.mode
    snap['min_spread'] = config.MIN_SPREAD_PCT
    snap['spread_options'] = config.SPREAD_OPTIONS
    snap['pending_transfers'] = executor.get_pending()
    # lucro AO VIVO de cada operação aberta (como se vendesse agora pelo preço atual)
    for t in snap['pending_transfers']:
        try:
            live_bid = (snap['prices'].get(t['to'], {}).get(t['pair']) or {}).get('bid')
            inv = float(t.get('invest_usdt') or 0)
            if live_bid and inv:
                live_net = round(float(t['qty']) * float(live_bid) - inv, 2)
                t['live_net'] = live_net
                t['live_pct'] = round(live_net / inv * 100, 4)
                t['live_price'] = live_bid
        except Exception:
            pass
    stats = db.stats()
    snap['total_simulations'] = stats.get('total_simulations', 0)
    snap['total_executions'] = stats.get('total_executions', 0)
    snap['balances'] = {}
    return snap


@app.get("/api/auto")
def get_auto():
    return {'auto_trade': AUTO_TRADE, 'mode': executor.mode}


@app.post("/api/auto")
def set_auto():
    global AUTO_TRADE
    AUTO_TRADE = not AUTO_TRADE
    try:
        db.set_setting('auto_trade', '1' if AUTO_TRADE else '0')
    except Exception:
        pass
    print(f"[AUTO] {'LIGADO' if AUTO_TRADE else 'DESLIGADO'}")
    return {'auto_trade': AUTO_TRADE, 'mode': executor.mode}


@app.get("/api/mode")
def get_mode():
    return {'mode': executor.mode}


class ModeRequest(BaseModel):
    mode: str | None = None


@app.post("/api/mode")
def set_mode(req: ModeRequest | None = None):
    order = ['paper', 'demo', 'real']
    cur = executor.mode if executor.mode in order else 'paper'
    if req and req.mode in order:
        new_mode = req.mode
    else:
        new_mode = order[(order.index(cur) + 1) % len(order)]
    executor.set_mode(new_mode)
    try:
        db.set_setting('mode', new_mode)
    except Exception:
        pass
    print(f"[MODE] Alterado para: {new_mode}")
    return {'mode': new_mode}


@app.get("/api/pending")
def get_pending():
    return {'data': executor.get_pending()}


@app.post("/api/balances/refresh")
def refresh_balances():
    executor._last_bal = 0  # força
    executor.refresh_real_balances(scanner, min_interval=0)
    return {'ok': True, 'capital': executor.demo_capital,
            'saldos': executor.balances_cache,
            'erros': getattr(executor, 'balances_errors', {})}


@app.get("/api/balances")
def get_balances():
    try:
        b = scanner.fetch_balances()
        return b
    except Exception as e:
        return {'error': str(e)}


@app.post("/api/simulate")
def do_simulate(req: SimRequest):
    prices = scanner.snapshot()['prices']
    buy_side = prices.get(req.buy_exchange, {}).get(req.pair)
    sell_side = prices.get(req.sell_exchange, {}).get(req.pair)
    if not buy_side or not sell_side:
        return {'error': 'Sem preço atual para essa combinação. Tente novamente em instantes.'}
    result = simulate(
        req.pair,
        req.buy_exchange, buy_side['ask'],
        req.sell_exchange, sell_side['bid'],
        req.invest_usdt, req.network,
    )
    if result['net_pct'] >= config.AUTO_SIM_THRESHOLD and result['net_usdt'] >= config.AUTO_SIM_DOLLAR_MIN:
        db.add_simulation({
            'trigger': 'manual',
            'pair': req.pair,
            'buy_exchange': req.buy_exchange,
            'sell_exchange': req.sell_exchange,
            'buy_price': result['buy_price'],
            'sell_price': result['sell_price'],
            'gross_pct': result['gross_pct'],
            'invest_usdt': result['invest_usdt'],
            'net_usdt': result['net_usdt'],
            'net_pct': result['net_pct'],
            'network': result['network'],
            'est_seconds': result['est_seconds'],
        })
    return result


@app.get("/api/simulations")
def simulations(limit: int = 200):
    return {'data': db.recent_simulations(limit)}


@app.delete("/api/simulations")
def clear_simulations():
    db.clear()
    return {'ok': True}


@app.get("/api/stats")
def stats():
    s = db.stats(24)
    s['investment'] = config.INVESTMENT_USDT
    s.update(db.execution_stats())
    try:
        # resultado do dia separado por modo: demo nao mistura com paper/real
        s['daily'] = db.daily_stats()
        s['daily_demo'] = db.daily_stats(mode='demo')
        s['daily_real'] = db.daily_stats(mode='real')
    except Exception as e:
        s['daily'] = {'erro': str(e)[:120]}
    return s


class ExecRequest(SimRequest):
    pass


@app.post("/api/execute")
def do_execute(req: ExecRequest):
    result = executor.execute(
        scanner, req.pair, req.buy_exchange, req.sell_exchange,
        req.invest_usdt, req.network,
    )
    return result


@app.get("/api/executions")
def executions(limit: int = 100):
    return {'data': db.recent_executions(limit)}


EXCHANGE_FIELDS = {
    'binance':  {'label': 'Binance',  'fields': ['API_KEY', 'SECRET_KEY']},
    'bitget':   {'label': 'Bitget',   'fields': ['API_KEY', 'SECRET_KEY', 'PASSPHRASE']},
    'okx':      {'label': 'OKX',      'fields': ['API_KEY', 'SECRET_KEY', 'PASSPHRASE']},
    'bybit':    {'label': 'Bybit',    'fields': ['API_KEY', 'SECRET_KEY']},
    'mexc':     {'label': 'MEXC',     'fields': ['API_KEY', 'SECRET_KEY']},
    'kucoin':   {'label': 'KuCoin',   'fields': ['API_KEY', 'SECRET_KEY', 'PASSPHRASE']},
    'gate':     {'label': 'Gate.io',  'fields': ['API_KEY', 'SECRET_KEY']},
    'mercadobitcoin': {'label': 'MercadoBitcoin', 'fields': ['API_KEY', 'SECRET_KEY']},
}


def _env_key(eid, field):
    return f'{eid.upper()}_{field}'


def _load_keys_from_db():
    """Recupera as chaves salvas pela tela de Configuracao.
    Sem isso, a key salva no .env local se perde no Render (disco efemero)."""
    try:
        prefix = '_'.join(sorted(EXCHANGE_FIELDS.keys()))  # apenas para manter ordem estável
    except Exception:
        prefix = ''
    carregadas = []
    for eid, info in EXCHANGE_FIELDS.items():
        for f in info['fields']:
            key = _env_key(eid, f)
            if os.environ.get(key):
                continue
            val = db.get_setting(f'key_{key}')
            if val:
                os.environ[key] = val
                carregadas.append(key)
    if carregadas:
        print(f"[CONFIG] chaves carregadas do banco: {', '.join(carregadas)}")
    return carregadas


def _save_key_db(eid, field, value):
    db.set_setting(f'key_{_env_key(eid, field)}', value)


def _clear_key_db(eid, field):
    try:
        c = db._conn()
        sql = "DELETE FROM app_settings WHERE key = ?" if db.USE_PG else "DELETE FROM app_settings WHERE key = ?"
        c.execute(sql, (f'key_{_env_key(eid, field)}',))
        c.commit()
        c.close()
    except Exception:
        pass


@app.get("/api/api-status")
def api_status():
    """Situacao de cada API: chave, preco publico e saldo autenticado."""
    import time as _t
    snap = scanner.snapshot()
    prices = snap.get('prices', {}) or {}
    errors = snap.get('errors', {}) or {}
    out = {}
    for eid, info in EXCHANGE_FIELDS.items():
        tem_chave = False
        for f in info['fields']:
            k = _env_key(eid, f)
            if os.environ.get(k) or db.get_setting(f'key_{k}'):
                tem_chave = True
                break
        p = (prices.get(eid) or {}).get('USDT/BRL')
        out[eid] = {
            'label': info['label'],
            'chave': tem_chave,
            'preco': bool(p),
            'ask': p.get('ask') if p else None,
            'bid': p.get('bid') if p else None,
            'erro': errors.get(eid, ''),
        }
    return out


@app.post("/api/api-test")
def api_test(exchange: str):
    """Testa de verdade: preco publico + saldo autenticado de UMA corretora."""
    import time as _t
    eid = (exchange or '').strip().lower()
    if eid not in EXCHANGE_FIELDS:
        return {'ok': False, 'erro': 'corretora desconhecida'}
    started = _t.time()
    res = {'exchange': eid, 'label': EXCHANGE_FIELDS[eid]['label'], 'preco': False, 'saldo': False}

    # 1) preco publico
    try:
        t0 = _t.time()
        info = scanner.fetch_balance_one(eid)
        if isinstance(info, dict) and not info.get('error'):
            res['saldo'] = True
            moedas = {k: v['total'] for k, v in (info.get('coins') or {}).items()}
            res['moedas'] = moedas
            if not moedas:
                res['aviso'] = 'conta sem saldo — API funciona ✅'
            res['ms_saldo'] = int((_t.time() - t0) * 1000)
        else:
            res['erro_saldo'] = (info or {}).get('error', 'sem resposta')
    except Exception as e:
        res['erro_saldo'] = f'{type(e).__name__}: {str(e)[:120]}'

    # 2) preco (do ultimo scan, sem custo extra)
    snap = scanner.snapshot()
    p = (snap.get('prices', {}).get(eid) or {}).get('USDT/BRL')
    if p:
        res['preco'] = True
        res['ask'] = p.get('ask')
        res['bid'] = p.get('bid')

    res['ms_total'] = int((_t.time() - started) * 1000)
    res['ok'] = bool(res['preco'] or res['saldo'])
    return res


@app.get("/api/settings")
def get_settings():
    result = {}
    for eid, info in EXCHANGE_FIELDS.items():
        result[eid] = {'label': info['label'], 'configured': False, 'fields': {}}
        for f in info['fields']:
            val = os.environ.get(_env_key(eid, f), '')
            if not val:
                val = db.get_setting(f'key_{_env_key(eid, f)}') or ''
            result[eid]['fields'][f] = val
            if val:
                result[eid]['configured'] = True
    return result


class SettingsRequest(BaseModel):
    exchange: str
    fields: dict


@app.post("/api/settings")
def save_settings(req: SettingsRequest):
    eid = req.exchange
    if eid not in EXCHANGE_FIELDS:
        return {'error': f'Corretora {eid} desconhecida'}

    env_path = os.path.join(os.path.dirname(__file__), '.env')
    lines = []
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

    for field, value in req.fields.items():
        key = _env_key(eid, field)
        env_line = f'{key}={value}\n'
        found = False
        for i, line in enumerate(lines):
            if line.strip().startswith(f'{key}='):
                lines[i] = env_line
                found = True
                break
        if not found:
            lines.append(env_line)
        os.environ[key] = value
        _save_key_db(eid, field, value)

    with open(env_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)

    try:
        scanner.load_exchanges()
    except Exception:
        pass

    return {'ok': True, 'exchange': eid, 'message': f'{EXCHANGE_FIELDS[eid]["label"]} salva e conectada!'}


@app.delete("/api/settings")
def clear_settings(exchange: str):
    eid = exchange
    if eid not in EXCHANGE_FIELDS:
        return {'error': 'Corretora desconhecida'}

    env_path = os.path.join(os.path.dirname(__file__), '.env')
    lines = []
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

    new_lines = []
    for line in lines:
        keep = True
        for f in EXCHANGE_FIELDS[eid]['fields']:
            if line.strip().startswith(f'{eid.upper()}_{f}='):
                keep = False
                break
        if keep:
            new_lines.append(line)

    with open(env_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)

    for f in EXCHANGE_FIELDS[eid]['fields']:
        key = _env_key(eid, f)
        os.environ.pop(key, None)
        _clear_key_db(eid, f)

    return {'ok': True}


app.mount("/", StaticFiles(directory="static", html=True), name="static")
