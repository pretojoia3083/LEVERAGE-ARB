import ccxt
import config

print(f"{'corretora':<16} {'USDT/BRL':<12} {'preco':<12} detalhe")
print('-' * 70)
for eid in config.EXCHANGES:
    nome = eid
    try:
        ex = getattr(ccxt, nome)({'enableRateLimit': True, 'timeout': 25000})
        ex.load_markets()
        tem = ex.has.get('USDT/BRL') if hasattr(ex, 'has') else None
        # procura o par de qualquer jeito (as vezes has[] vem errado)
        achou = 'USDT/BRL' in ex.markets
        if not achou:
            # aceita variantes
            for m in ex.markets:
                if m.upper().replace('/', '').startswith('USDTBRL'):
                    achou = True
                    break
        preco = '-'
        if achou:
            t = ex.fetch_ticker('USDT/BRL')
            preco = f"{t['last']:.4f}" if t and t.get('last') else 'sem preço'
        print(f"{nome:<16} {('SIM' if achou else 'NAO'):<12} {preco:<12} {len(ex.markets)} pares")
    except Exception as e:
        print(f"{nome:<16} {'ERRO':<12} {'-':<12} {str(e)[:44]}")
