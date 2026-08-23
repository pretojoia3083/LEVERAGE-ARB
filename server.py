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
        global LAST_OPPS
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
                    min_pct = 0.30 if executor.mode == 'real' else config.AUTO_SIM_THRESHOLD
                    if best['net_pct'] >= min_pct and best['net_usdt'] > 0:
                        print(f"[AUTO] Executando {best['pair']} {best['buy_exchange']}->{best['sell_exchange']} +{best['net_pct']}% ({executor.mode})")
                        executor.execute(
                            scanner, best['pair'],
                            best['buy_exchange'], best['sell_exchange'],
                            best['invest_usdt'], best['network'],
                        )

                if executor.mode == 'real':
                    executor.check_deposits(scanner)
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


@app.get("/api/dashboard")
def dashboard():
    snap = scanner.snapshot()
    snap['investment'] = config.INVESTMENT_USDT
    snap['auto_trade'] = AUTO_TRADE
    snap['mode'] = executor.mode
    snap['pending_transfers'] = executor.get_pending()
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
    print(f"[AUTO] {'LIGADO' if AUTO_TRADE else 'DESLIGADO'}")
    return {'auto_trade': AUTO_TRADE, 'mode': executor.mode}


@app.get("/api/mode")
def get_mode():
    return {'mode': executor.mode}


@app.post("/api/mode")
def set_mode():
    new_mode = 'real' if executor.mode == 'paper' else 'paper'
    executor.set_mode(new_mode)
    print(f"[MODE] Alterado para: {new_mode}")
    return {'mode': new_mode}


@app.get("/api/pending")
def get_pending():
    return {'data': executor.get_pending()}


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


@app.get("/api/settings")
def get_settings():
    result = {}
    for eid, info in EXCHANGE_FIELDS.items():
        result[eid] = {'label': info['label'], 'configured': False, 'fields': {}}
        for f in info['fields']:
            val = os.environ.get(_env_key(eid, f), '')
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

    with open(env_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)

    return {'ok': True, 'exchange': eid, 'message': f'{EXCHANGE_FIELDS[eid]["label"]} salva! Reinicie para conectar.'}


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

    return {'ok': True}


app.mount("/", StaticFiles(directory="static", html=True), name="static")
