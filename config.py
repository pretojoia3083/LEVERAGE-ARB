import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BITGET_API_KEY = os.environ.get('BITGET_API_KEY', '')
BITGET_SECRET_KEY = os.environ.get('BITGET_SECRET_KEY', '')
BITGET_PASSPHRASE = os.environ.get('BITGET_PASSPHRASE', '')
BINANCE_API_KEY = os.environ.get('BINANCE_API_KEY', '')
BINANCE_SECRET_KEY = os.environ.get('BINANCE_SECRET_KEY', '')

INVESTMENT_USDT = 50.0
MIN_NET_PCT = 0.0
AUTO_SIM_THRESHOLD = 0.10
AUTO_SIM_DOLLAR_MIN = 1.0
AUTO_SIM_COOLDOWN = 60
SCAN_INTERVAL = 5
TOP_LIMIT = 50

# Spread minimo exibido nas oportunidades (escolhido no menu: 0.10 / 0.50 / 1.0 / 2.0)
SPREAD_OPTIONS = [0.10, 0.50, 1.0, 2.0]
MIN_SPREAD_PCT = float(os.environ.get('MIN_SPREAD_PCT', '0.10'))

# Redes preferidas (BEP20 + Polygon primeiro, resto como reserva)
NETWORK_PRIORITY = ['BEP20', 'POLYGON', 'ARBITRUM', 'SOL', 'TRC20', 'ERC20']

IS_CLOUD = os.environ.get('RENDER') is not None

EXCHANGES = [
    'binance', 'bybit', 'bitget', 'okx', 'gate', 'mexc',
    'kucoin', 'kraken',
] if IS_CLOUD else [
    'binance', 'bybit', 'bitget', 'kucoin',
    'okx', 'gate', 'mexc', 'htx', 'kraken',
    'mercadobitcoin',
    'bitso',
]

TAKER_FEES = {
    'binance': 0.0010,
    'bybit':   0.0010,
    'bitget':  0.0010,
    'kucoin':  0.0010,
    'okx':     0.0010,
    'gate':    0.0009,
    'mexc':    0.0005,
    'htx':     0.0020,
    'kraken':  0.0026,
    'mercadobitcoin': 0.0050,
    'bitso': 0.0050,
}

PAIRS = [
    'USDT/BRL',
]

NETWORKS = {
    'BEP20':    {'fee_usd': 0.30, 'minutes': 3},
    'SOL':      {'fee_usd': 0.30, 'minutes': 1},
    'POLYGON':  {'fee_usd': 0.10, 'minutes': 3},
    'ARBITRUM': {'fee_usd': 0.15, 'minutes': 3},
    'TRC20':    {'fee_usd': 1.50, 'minutes': 2},
    'ERC20':    {'fee_usd': 3.50, 'minutes': 15},
}

WITHDRAWAL_FEES = {
    'binance': {
        'BEP20': 0.01, 'SOL': 0.30, 'POLYGON': 0.07,
        'ARBITRUM': 0.10, 'TRC20': 1.50, 'ERC20': 0.40,
    },
    'bybit': {
        'BEP20': 1.00, 'SOL': 1.00, 'POLYGON': 0.07,
        'ARBITRUM': 1.00, 'TRC20': 1.60, 'ERC20': 5.00,
    },
    'bitget': {
        'BEP20': 0.15, 'SOL': 1.00, 'POLYGON': 0.07,
        'ARBITRUM': 0.05, 'TRC20': 1.50, 'ERC20': 2.00,
    },
    'okx': {
        'BEP20': 0.05, 'SOL': 0.34, 'POLYGON': 0.012,
        'ARBITRUM': 0.0034, 'TRC20': 1.00, 'ERC20': 0.43,
    },
    'mexc': {
        'BEP20': 0.01, 'SOL': 0.18, 'POLYGON': 0.0065,
        'ARBITRUM': 0.05, 'TRC20': 1.00, 'ERC20': 0.094,
    },
    'mercadobitcoin': {
        'BEP20': 1.50, 'SOL': 2.00, 'POLYGON': 2.00,
        'ARBITRUM': 2.00, 'TRC20': 3.00, 'ERC20': 10.00,
    },
}

BUY_SECONDS = 2
SELL_SECONDS = 2
