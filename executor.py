import os
import threading
import time

import ccxt

import config
import db
from engine import simulate


class Executor:
    def __init__(self):
        self.lock = threading.Lock()
        self.counter = 0
        self.mode = 'paper'  # 'paper' ou 'real'
        self.pending_transfers = []

    def set_mode(self, mode):
        if mode not in ('paper', 'demo', 'real'):
            mode = 'paper'
        self.mode = mode
        print(f"[EXEC] Modo alterado para: {mode}")

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
            return self._execute_demo(scanner, o)
        return self.execute(scanner, o['pair'], o['buy_exchange'],
                            o['sell_exchange'], o['invest_usdt'], o['network'])

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
        stages = [{'stage': 'compra (demo)', 'exchange': o['buy_exchange'],
                   'price': round(buy_price, 8), 'qty': round(buy_qty, 8),
                   'seconds': 0}]
        transfer = {
            'id': self.counter + 1,
            'pair': o['pair'],
            'buy_exchange': o['buy_exchange'],
            'sell_exchange': o['sell_exchange'],
            'buy_price': buy_price,
            'buy_qty': buy_qty,
            'sell_qty': round(max(buy_qty - sim['networks'][0]['withdrawal_fee_usd'] / sell_side['bid'], 0), 8),
            'demo': True,
            'settle_at': started + getattr(_cfg, 'DEMO_SETTLE_SECONDS', 45),
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
              f"R${o['invest_usdt']} — vende sozinha em {getattr(_cfg, 'DEMO_SETTLE_SECONDS', 45)}s")
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
