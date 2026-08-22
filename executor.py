import threading
import time

import db
from engine import simulate


class Executor:
    def __init__(self):
        self.lock = threading.Lock()
        self.counter = 0

    def execute(self, scanner, pair, buy_exchange, sell_exchange, invest_usdt, network='AUTO'):
        snap = scanner.snapshot()
        buy_side = snap['prices'].get(buy_exchange, {}).get(pair)
        sell_side = snap['prices'].get(sell_exchange, {}).get(pair)

        if not buy_side or not sell_side:
            # Ainda assim registra para controle/monitoramento
            result = {
                'ok': False,
                'mode': 'paper',
                'pair': pair,
                'buy_exchange': buy_exchange,
                'sell_exchange': sell_exchange,
                'invest_usdt': invest_usdt,
                'network': network,
                'gross_pct': 0,
                'net_usdt': 0,
                'net_pct': 0,
                'elapsed_ms': 0,
                'elapsed_fmt': '0.00s',
                'est_real_seconds': 0,
                'stages': [{'stage': 'erro', 'exchange': buy_exchange, 'price': '--', 'qty': 0, 'seconds': 0, 'rede': '--', 'fee_usd': 0, 'est_minutes': 0, 'qty_burned': 0}],
            }
            db.add_execution(result)
            return result

        sim = simulate(pair, buy_exchange, buy_side['ask'],
                       sell_exchange, sell_side['bid'], invest_usdt, network)

        started = time.time()
        stages = []

        stages.append({'stage': 'compra', 'exchange': buy_exchange,
                       'price': round(buy_side['ask'], 8),
                       'qty': round(sim['quantity'], 8),
                       'seconds': round(time.time() - started, 3)})
        after_buy = time.time()

        chosen_net = next(n for n in sim['networks'] if n['network'] == sim['network'])
        wq = round(chosen_net['withdrawal_fee_usd'] / sell_side['bid'], 8)
        stages.append({'stage': 'transferencia', 'rede': sim['network'],
                       'fee_usd': chosen_net['withdrawal_fee_usd'],
                       'est_minutes': chosen_net['est_seconds'] // 60,
                       'qty_burned': wq,
                       'seconds': round(time.time() - after_buy, 3)})
        after_tx = time.time()

        sell_qty = sim['quantity'] - wq
        stages.append({'stage': 'venda', 'exchange': sell_exchange,
                       'price': round(sell_side['bid'], 8),
                       'qty': round(sell_qty, 8),
                       'seconds': round(time.time() - after_tx, 3)})

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


executor = Executor()
