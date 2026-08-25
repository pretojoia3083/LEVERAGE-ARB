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
    'bitget':  0.0008,
    'kucoin':  0.0010,
    'okx':     0.0008,
    'gate':    0.0009,
    'mexc':    0.0000,
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
        'ARBITRUM': 0.10, 'TRC20': 1.50, 'ERC20': 3.50,
    },
    'bybit': {
        'BEP20': 1.00, 'SOL': 1.00, 'POLYGON': 1.00,
        'ARBITRUM': 1.00, 'TRC20': 1.60, 'ERC20': 5.00,
    },
    'bitget': {
        'BEP20': 0.15, 'SOL': 1.00, 'POLYGON': 1.00,
        'ARBITRUM': 1.00, 'TRC20': 1.50, 'ERC20': 3.00,
    },
    'okx': {
        'BEP20': 0.10, 'SOL': 0.10, 'POLYGON': 0.10,
        'ARBITRUM': 0.10, 'TRC20': 1.00, 'ERC20': 3.00,
    },
    'mexc': {
        'BEP20': 0.00, 'SOL': 0.00, 'POLYGON': 0.00,
        'ARBITRUM': 0.00, 'TRC20': 1.00, 'ERC20': 3.00,
    },
    'mercadobitcoin': {
        'BEP20': 0.80, 'SOL': 0.80, 'POLYGON': 0.80,
        'ARBITRUM': 0.80, 'TRC20': 2.00, 'ERC20': 5.00,
    },
}

BUY_SECONDS = 2
SELL_SECONDS = 2
