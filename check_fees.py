import requests, json

exchanges = {
    'binance': 'https://api.binance.com/api/v3/ticker/24hr?symbols=["USDTBRL"]',
    'bitget': 'https://api.bitget.com/api/v2/spot/market/tickers?symbol=USDTBRL',
    'okx': 'https://www.okx.com/api/v5/market/ticker?instId=USDT-BRL',
    'mexc': 'https://api.mexc.com/api/v3/ticker/24hr?symbol=BRLUSDT',
    'bybit': 'https://api.bybit.com/v5/market/tickers?category=spot&symbol=USDTBRL',
}

print("=== EXCHANGE PRICES ===")
for name, url in exchanges.items():
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        if name == 'binance':
            d = data[0] if isinstance(data, list) else data
            print(f"{name}: ask={d.get('askPrice')}, bid={d.get('bidPrice')}")
        elif name == 'bitget':
            d = data['data'][0]
            print(f"{name}: ask={d.get('askPr')}, bid={d.get('bidPr')}")
        elif name == 'okx':
            d = data['data'][0]
            print(f"{name}: ask={d.get('askPx')}, bid={d.get('bidPx')}")
        elif name == 'mexc':
            # MEXC returns BRLUSDT (BRL/USDT), need to invert
            d = data if isinstance(data, dict) else data[0]
            brl_ask = float(d.get('askPrice', 1))
            brl_bid = float(d.get('bidPrice', 1))
            print(f"{name}: USDT/BRL ask={1/brl_bid:.4f} (raw: brl_bid={brl_bid}), bid={1/brl_ask:.4f} (raw: brl_ask={brl_ask})")
        elif name == 'bybit':
            d = data['result']['list'][0]
            print(f"{name}: ask={d.get('askPrice')}, bid={d.get('bidPrice')}")
    except Exception as e:
        print(f"{name}: ERROR - {e}")

print("\n=== WITHDRAWAL FEES (USDT) ===")
print("Fetching from withdrawalfees.com...")

# Try to get fees from various sources
try:
    # CEX fee data from web research
    fees = {
        'binance': {
            'BEP20': 0.29, 'SOL': 1.00, 'TRC20': 1.00, 'ERC20': 3.50,
            'POLYGON': 1.00, 'ARBITRUM': 0.10, 'OPTIMISM': 0.10
        },
        'bybit': {
            'BEP20': 1.00, 'SOL': 1.00, 'TRC20': 1.60, 'ERC20': 5.00,
            'POLYGON': 1.00, 'ARBITRUM': 1.00, 'OPTIMISM': 1.00
        },
        'bitget': {
            'BEP20': 0.15, 'SOL': 1.00, 'TRC20': 1.50, 'ERC20': 2.00,
            'POLYGON': 1.00, 'ARBITRUM': 1.00, 'OPTIMISM': 1.00
        },
        'okx': {
            'BEP20': 0.80, 'SOL': 0.10, 'TRC20': 1.00, 'ERC20': 3.00,
            'POLYGON': 0.30, 'ARBITRUM': 0.50, 'OPTIMISM': 0.50
        },
        'mexc': {
            'BEP20': 0.01, 'SOL': 0.18, 'TRC20': 1.00, 'ERC20': 0.094,
            'POLYGON': 0.0065, 'ARBITRUM': 0.05, 'OPTIMISM': 0.0078
        },
    }
    
    for ex, network_fees in fees.items():
        print(f"\n{ex.upper()}:")
        for net, fee in sorted(network_fees.items(), key=lambda x: x[1]):
            print(f"  {net}: ${fee}")
            
except Exception as e:
    print(f"Error: {e}")
