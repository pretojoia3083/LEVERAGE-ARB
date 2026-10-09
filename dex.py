"""Monitor DEX (leitura): cotacoes USDT <-> BRZ na KyberSwap por rede.

Sem carteira: so consulta preco (route preview) e compara com o CEX.
Cache de 60s para nao estourar rate limit.
"""
import threading
import time

import requests

# USDT por rede (enderecos oficiais)
USDT = {
    'polygon':  '0xc2132D05D31c914a87C6611C10748AEb04B58e8F',
    'arbitrum': '0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9',
    'base':     '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913',
    'ethereum': '0xdAC17F958D2ee523a2206206994597C13D831ec7',
}

# BRZ (stablecoin 1:1 BRL) por rede — enderecos validados via route 200
BRZ = {
    'polygon':  '0x4ed141110f6eeeaba9a1df36d8c26f684d2475dc',
    'arbitrum': '0xA8940698FdA5A07AbAEf4A5ccDf2f1Bb525B47A2',
    'base':     '0xe9185ee218cae427af7b9764a011bb89fea761b4',
    'ethereum': '0x420412e765bfa6d85aaac94b4f7b708c89be2e2b',
}

CHAINS = ['polygon', 'arbitrum', 'base', 'ethereum']
AMOUNT_USDT = 1000  # base de comparacao

_cache = {'ts': 0, 'data': []}
_lock = threading.Lock()
TTL = 60


def _route(chain, token_in, token_out, amount_in):
    url = f'https://aggregator-api.kyberswap.com/{chain}/api/v1/routes'
    r = requests.get(url, params={
        'tokenIn': token_in,
        'tokenOut': token_out,
        'amountIn': str(amount_in),
        'saveGas': '0',
    }, timeout=8)
    d = r.json()
    rs = (d.get('data') or {}).get('routeSummary')
    if not rs:
        return None
    return rs


def refresh(force=False):
    with _lock:
        if not force and time.time() - _cache['ts'] < TTL and _cache['data']:
            return _cache['data']

    rows = []
    for chain in CHAINS:
        try:
            usdt = USDT[chain]
            brz = BRZ[chain]
            # 1000 USDT -> BRZ (USDT tem 6 decimais; no ethereum tambem 6)
            fwd = _route(chain, usdt, brz, AMOUNT_USDT * 10**6)
            # volta: BRZ recebido -> USDT (BRZ tem 18 decimais)
            back = None
            fwd_out = 0
            if fwd:
                fwd_out = int(fwd.get('amountOut', 0) or 0)
                if fwd_out > 0:
                    back = _route(chain, brz, usdt, fwd_out)
            back_out = int((back or {}).get('amountOut', 0) or 0)
            back_usdt = back_out / 10**6 if back_out else 0
            rows.append({
                'chain': chain,
                'usdt_in': AMOUNT_USDT,
                'brz_out': round(fwd_out / 10**18, 2) if fwd_out else 0,
                'brz_price_usdt': round(AMOUNT_USDT / (fwd_out / 10**18), 6) if fwd_out else 0,
                'roundtrip_usdt': round(back_usdt, 2),
                'roundtrip_pnl': round(back_usdt - AMOUNT_USDT, 2),
                'ok': bool(fwd),
            })
        except Exception as e:
            rows.append({'chain': chain, 'ok': False, 'error': str(e)[:100]})

    with _lock:
        _cache['ts'] = time.time()
        _cache['data'] = rows
    return rows


def snapshot():
    with _lock:
        data = list(_cache['data'])
        ts = _cache['ts']
    if not data or time.time() - ts > TTL:
        def _bg():
            try:
                refresh()
            except Exception:
                pass
        threading.Thread(target=_bg, daemon=True).start()
    return {'updated_ts': ts, 'rows': data, 'ttl': TTL}
