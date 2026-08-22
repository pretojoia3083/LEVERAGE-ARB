import threading
import time

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
import db
from engine import Scanner, simulate
from executor import executor

app = FastAPI(title="LEVERAGE ARB")

scanner = Scanner()


@app.on_event("startup")
def startup():
    def bootstrap():
        n = scanner.load_exchanges()
        print(f"[LEVERAGE ARB] {n} corretoras conectadas")
        while True:
            try:
                opps = scanner.scan()
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
    return snap


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


app.mount("/", StaticFiles(directory="static", html=True), name="static")
